"""Serviço de OCR estruturado de matrícula imobiliária.

Pipeline:
    PDF (bytes) → páginas PNG (via pypdfium2, puro Python sem poppler)
                → VisionService.assess_matricula(pages) → MatriculaVisionPayload
                → MatriculaOcrResult (schema do agente)

Custo aproximado: ~$0.013 × N páginas (GPT-4o high detail) → ~$0.08-0.10
para matrículas típicas de 6-8 páginas. Cobrado apenas no momento do
upload pelo usuário (não no caminho automático do agente).

Falha silenciosa: PDF corrompido / Vision fora do ar → ``MatriculaOcrResult``
com ``confidence=LOW`` e ``notes`` explicativo.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timezone
from typing import Final

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from app.agents.legal.schemas import (
    MatriculaLien,
    MatriculaOcrResult,
)
from app.core.logging import get_logger
from app.services.vision_service import VisionService

logger = get_logger(__name__)

# Limite de páginas processadas — matrículas muito longas (>8 páginas) são
# raras e processá-las inteiras pode estourar o context do Vision. A maior
# parte das informações relevantes está nas primeiras 8 páginas.
MAX_PAGES: Final[int] = 8

# Resolução de render (DPI). 200 é o equilíbrio entre legibilidade do texto
# e tamanho do PNG (≤ ~500KB por página).
RENDER_SCALE: Final[float] = 200.0 / 72.0

COST_USD_PER_PAGE: Final[float] = 0.013


class MatriculaOcrError(RuntimeError):
    """Falha no parsing/OCR da matrícula."""


def pdf_to_png_pages(pdf_bytes: bytes, *, max_pages: int = MAX_PAGES) -> list[bytes]:
    """Renderiza as primeiras ``max_pages`` páginas em PNG (bytes).

    Levanta :class:`MatriculaOcrError` se o PDF for inválido.
    """
    if not pdf_bytes:
        raise MatriculaOcrError("PDF vazio")
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        raise MatriculaOcrError(f"PDF inválido: {exc}") from exc

    pages: list[bytes] = []
    n = min(len(doc), max_pages)
    for i in range(n):
        page = doc[i]
        try:
            pil = page.render(scale=RENDER_SCALE).to_pil()
        finally:
            page.close()
        buf = io.BytesIO()
        pil.save(buf, format="PNG", optimize=True)
        pages.append(buf.getvalue())
    doc.close()
    return pages


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _normalize_cpf_cnpj(s: str | None) -> str | None:
    if not s:
        return None
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) in (11, 14):
        return digits
    return None


def extract_matricula(
    pdf_bytes: bytes,
    *,
    vision: VisionService,
    pdf_path: str | None = None,
) -> MatriculaOcrResult:
    """Extrai estrutura da matrícula do PDF.

    NÃO levanta para erros conhecidos — devolve ``MatriculaOcrResult`` com
    ``confidence=LOW`` e ``notes``. Levanta :class:`MatriculaOcrError`
    apenas quando o PDF é claramente inválido (caller deve traduzir para
    HTTP 400).
    """
    pages = pdf_to_png_pages(pdf_bytes)
    payload = vision.assess_matricula(pages)
    now = datetime.now(timezone.utc)
    if payload is None:
        return MatriculaOcrResult(
            confidence="LOW",
            notes="Vision LLM falhou ou devolveu payload inválido.",
            cost_estimate_usd=round(COST_USD_PER_PAGE * len(pages), 4),
            pdf_path=pdf_path,
            extracted_at=now,
        )

    liens = [
        MatriculaLien(
            tipo=lp.tipo,
            credor=lp.credor,
            valor_brl=lp.valor_brl,
            data_registro=_parse_iso_date(lp.data_registro),
            av_numero=lp.av_numero,
            notes=lp.notes,
        )
        for lp in payload.liens
    ]
    return MatriculaOcrResult(
        owner_name=payload.owner_name,
        owner_cpf_cnpj=_normalize_cpf_cnpj(payload.owner_cpf_cnpj),
        matricula_number=payload.matricula_number,
        registry_office=payload.registry_office,
        liens=liens,
        is_clear=len(liens) == 0,
        confidence=payload.confidence,
        notes=payload.notes,
        cost_estimate_usd=round(COST_USD_PER_PAGE * len(pages), 4),
        pdf_path=pdf_path,
        extracted_at=now,
    )


__all__ = [
    "MAX_PAGES",
    "MatriculaOcrError",
    "extract_matricula",
    "pdf_to_png_pages",
]
