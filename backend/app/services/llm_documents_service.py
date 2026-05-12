"""Análise consolidada de documentos via LLM (OpenAI gpt-4o).

Recebe N documentos já extraídos (texto e/ou imagens) e devolve um
``DocumentAnalysisReport`` com:

* ``liens``: ônus identificados, com ``source_document_id``;
* ``risks``: riscos jurídicos/registrais agrupados por severidade;
* ``critical_findings``: bandeira agregada para destacar na UI;
* ``recommendations``: ações sugeridas.

Custo:
* PDFs com texto digital → só tokens-text (~$0.005-0.02 por doc).
* PDFs escaneados / imagens → Vision em ``detail=high``
  (~$0.013/imagem); cap de ``MAX_PAGES_TOTAL=30`` páginas/imagens.

Falha silenciosa: rede / quota / output inválido → devolve ``None``.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Final
from uuid import UUID

from langchain_openai import ChatOpenAI

from app.agents.documents.schemas import (
    DOC_TYPE_LABELS,
    DocumentAnalysisLLMPayload,
    DocumentAnalysisReport,
    DocumentRef,
    DocumentType,
)
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Cap duro para evitar explosão de custo quando o usuário seleciona muitos
# docs escaneados. Acima disso, truncamos e marcamos `notes` no report.
MAX_PAGES_TOTAL: Final[int] = 30

# Custo aproximado (USD) — só para estimativa devolvida no report.
COST_PER_IMAGE_HIGH: Final[float] = 0.013
COST_PER_TEXT_DOC: Final[float] = 0.005


@dataclass
class ExtractedDoc:
    """Documento já materializado (texto e/ou imagens) pronto para a LLM."""

    document_id: UUID
    doc_type: DocumentType
    label: str
    text: str = ""
    images: list[bytes] = field(default_factory=list)


_DOCUMENTS_REPORT_SYSTEM_PROMPT: Final[str] = (
    "Você é um perito brasileiro em leilões judiciais e extrajudiciais de"
    " imóveis. Recebe um conjunto de DOCUMENTOS (matrícula, edital, laudo,"
    " peças processuais ou outros) referentes a UM ÚNICO IMÓVEL e devolve"
    " um RELATÓRIO CONSOLIDADO em JSON com ônus, riscos jurídicos e"
    " recomendações para o arrematante."
    "\n\n"
    "REGRAS:"
    "\n - Cada item identificado deve referenciar via ``source_document_id``"
    " (ou ``source_document_ids`` para riscos transversais) o(s) UUID(s) do(s)"
    " documento(s) onde foi encontrado — use exatamente o UUID listado no"
    " cabeçalho ``<doc id=\"...\">``."
    "\n - ``liens``: apenas ônus ATIVOS (descarte averbações canceladas,"
    " baixadas, levantadas ou anuladas por averbação posterior). Tipo segue:"
    " hipoteca | penhora | usufruto | alienacao_fiduciaria | servidao |"
    " indisponibilidade | outro."
    "\n - ``risks``: cada risco tem severity (LOW/MEDIUM/HIGH/CRITICAL) e"
    " category (onus | processo_ativo | irregularidade_registral |"
    " vicio_edital | ocupacao | tributario | outro). CRITICAL para coisas"
    " que invalidam a arrematação (anulatória ativa, indisponibilidade,"
    " vício insanável de edital). HIGH para débitos relevantes ou ocupação."
    " MEDIUM/LOW para alertas operacionais."
    "\n - ``critical_findings=true`` somente quando houver ≥1 risk com"
    " severity=CRITICAL. ``critical_findings_summary`` é uma lista curta"
    " (até 5 frases) com os pontos críticos em PT-BR."
    "\n - ``recommendations``: até 10 ações concretas para o arrematante"
    " (ex.: 'Solicitar certidão atualizada do CRI antes de arrematar',"
    " 'Confirmar quitação de IPTU dos últimos 5 exercícios')."
    "\n - ``confidence``: HIGH quando os documentos são claros e suficientes;"
    " MEDIUM quando há ambiguidade ou faltam fontes; LOW quando os documentos"
    " estão ilegíveis ou desconexos do imóvel."
    "\n - Não invente informações que não estão nos documentos fornecidos."
    "\n - PT-BR em todos os campos livres, frases curtas e acionáveis."
)


_DOCUMENTS_REPORT_USER_HEADER: Final[str] = (
    "Conjunto de documentos para análise consolidada. Cada bloco está"
    " marcado com seu UUID e tipo. Documentos com texto extraído aparecem"
    " entre tags <doc>; documentos enviados como imagens estão logo após"
    " (com legendas de página). Devolva o JSON estruturado conforme as"
    " instruções."
)


def _encode_image_b64(content: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _doc_label(doc: ExtractedDoc) -> str:
    return doc.label or DOC_TYPE_LABELS.get(doc.doc_type, doc.doc_type)


def _build_content_blocks(
    docs: list[ExtractedDoc], *, max_pages_total: int
) -> tuple[list[dict], int, int, bool]:
    """Monta os content blocks multipart e retorna (blocks, n_images_used,
    n_text_docs, truncated)."""
    blocks: list[dict] = [{"type": "text", "text": _DOCUMENTS_REPORT_USER_HEADER}]
    images_used = 0
    text_docs = 0
    truncated = False

    for doc in docs:
        header = (
            f'\n<doc id="{doc.document_id}" type="{doc.doc_type}"'
            f' label="{_doc_label(doc)}">'
        )
        if doc.text:
            text_docs += 1
            footer = "</doc>"
            blocks.append(
                {
                    "type": "text",
                    "text": f"{header}\n{doc.text}\n{footer}",
                }
            )
        else:
            # Cabeçalho textual antes do bloco de imagens — ancoram o
            # ``document_id`` no contexto do LLM.
            blocks.append(
                {
                    "type": "text",
                    "text": (
                        f'{header}\n(documento fornecido como imagens, '
                        f"sem texto digital extraível)"
                    ),
                }
            )
        for i, png in enumerate(doc.images, start=1):
            if images_used >= max_pages_total:
                truncated = True
                break
            blocks.append(
                {"type": "text", "text": f'  [doc {doc.document_id} · página {i}]'}
            )
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _encode_image_b64(png, mime="image/png"),
                        "detail": "high",
                    },
                }
            )
            images_used += 1
        if not doc.text:
            blocks.append({"type": "text", "text": "</doc>"})
        if truncated:
            break
    return blocks, images_used, text_docs, truncated


class DocumentsAnalysisService:
    """Wrapper de gpt-4o para a análise consolidada de documentos."""

    def __init__(self, *, api_key: str, model: str = "gpt-4o") -> None:
        self._llm = ChatOpenAI(
            api_key=api_key, model=model, temperature=0
        ).with_structured_output(DocumentAnalysisLLMPayload)
        self._model = model

    def analyze(
        self,
        docs: list[ExtractedDoc],
        *,
        max_pages_total: int = MAX_PAGES_TOTAL,
    ) -> DocumentAnalysisReport | None:
        if not docs:
            return None

        blocks, n_images, n_text_docs, truncated = _build_content_blocks(
            docs, max_pages_total=max_pages_total
        )

        try:
            logger.info(
                "llm_documents.analyze.start",
                n_docs=len(docs),
                n_images=n_images,
                n_text_docs=n_text_docs,
                truncated=truncated,
                model=self._model,
            )
            payload = self._llm.invoke(
                [
                    {"role": "system", "content": _DOCUMENTS_REPORT_SYSTEM_PROMPT},
                    {"role": "user", "content": blocks},
                ]
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_documents.analyze.failed", error=str(exc))
            return None

        if not isinstance(payload, DocumentAnalysisLLMPayload):
            logger.warning(
                "llm_documents.analyze.unexpected_payload",
                type=type(payload).__name__,
            )
            return None

        cost = round(
            n_images * COST_PER_IMAGE_HIGH + n_text_docs * COST_PER_TEXT_DOC,
            4,
        )
        notes = payload.notes
        if truncated:
            trunc_note = (
                f"Análise truncada em {max_pages_total} imagens — "
                "documentos restantes não foram avaliados visualmente."
            )
            notes = f"{notes}\n{trunc_note}" if notes else trunc_note

        return DocumentAnalysisReport(
            documents_analyzed=[
                DocumentRef(
                    document_id=d.document_id,
                    doc_type=d.doc_type,
                    label=_doc_label(d),
                )
                for d in docs
            ],
            liens=payload.liens,
            risks=payload.risks,
            critical_findings=payload.critical_findings,
            critical_findings_summary=payload.critical_findings_summary,
            recommendations=payload.recommendations,
            confidence=payload.confidence,
            cost_usd=cost,
            extracted_at=datetime.now(timezone.utc),
            model=self._model,
            notes=notes,
        )


@lru_cache(maxsize=1)
def get_documents_analysis_service() -> DocumentsAnalysisService:
    settings = get_settings()
    return DocumentsAnalysisService(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
    )


__all__ = [
    "COST_PER_IMAGE_HIGH",
    "COST_PER_TEXT_DOC",
    "DocumentsAnalysisService",
    "ExtractedDoc",
    "MAX_PAGES_TOTAL",
    "get_documents_analysis_service",
]
