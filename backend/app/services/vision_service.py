"""Vision LLM (OpenAI GPT-4o multimodal) sobre o ENTORNO do imóvel.

Recebe um pacote de imagens geocodificadas — Street View dos vizinhos
imediatos + vista aérea (satellite) + foto do edital (quando houver) —
e devolve uma leitura do entorno: padrão construtivo do bairro,
comparação do imóvel com vizinhos, presença de piscinas próximas,
sugestão de nível de reforma e risk flags do entorno.

Por que o entorno e não o interior: a foto do edital quase sempre é
fachada genérica e dá sinal pobre. Street View dos vizinhos imediatos
+ aérea informam o padrão do bairro de forma muito mais confiável.

O nível de reforma sugerido NÃO substitui a escolha do usuário no
Agente 3 — entra só como sinal complementar.

Custo: ~$0.08-0.10 por análise (6 imagens GPT-4o em ``detail=high`` +
tokens de texto). Falha silenciosa: erro de rede / quota → retorna None.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Final, Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.logging import get_logger

# Tipos locais — evitam circular import com agents.deep.schemas.
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
NeighborhoodPattern = Literal["uniforme", "misto", "precario"]
PropertyVsNeighbors = Literal["acima", "igual", "abaixo"]
SuggestedRenovationLevel = Literal[
    "none", "cosmetic", "light", "basic", "moderate", "full", "premium"
]

# Slots que o caller envia. A ordem CANÔNICA do prompt fica abaixo —
# a aérea é apresentada por ÚLTIMO porque é a fonte primária para contar
# piscinas e julgar padrão de quadra, e a última imagem do prompt recebe
# mais peso atencional em LLMs multimodais.
SLOT_LABELS: Final[dict[str, str]] = {
    "listing": "Foto do edital (fachada do imóvel, quando disponível)",
    "sv_front": "Street View — frente do imóvel-alvo",
    "sv_left": "Street View — vizinho à esquerda (heading 90°)",
    "sv_right": "Street View — vizinho à direita (heading 270°)",
    "sv_back": "Street View — outro lado da rua (heading 180°)",
    "aerial": (
        "Vista aérea (satélite) — PIN VERMELHO marca o lote do imóvel-alvo."
        " FONTE PRIMÁRIA para contar piscinas em terrenos vizinhos e ler o"
        " padrão de quadra."
    ),
}

# Ordem canônica das imagens no prompt — a chave fica antes do valor em dict
# Python 3.7+, então iteramos por ``SLOT_LABELS`` na ordem definida acima.
_SLOT_ORDER: Final[tuple[str, ...]] = tuple(SLOT_LABELS.keys())

logger = get_logger(__name__)


class VisionServiceError(RuntimeError):
    """Falha ao chamar o modelo multimodal."""


# Estrutura forçada de retorno do LLM — Pydantic + structured output.
class NeighborhoodVisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    neighborhood_pattern: NeighborhoodPattern | None = Field(
        default=None,
        description=(
            "Padrão construtivo predominante das casas observadas: "
            "'uniforme' (todas similares em estilo/porte/idade), "
            "'misto' (mistura de padrões — alto e médio convivendo), "
            "'precario' (casas humildes, autoconstrução, sem padronização)."
        ),
    )
    property_vs_neighbors: PropertyVsNeighbors | None = Field(
        default=None,
        description=(
            "O imóvel-alvo em comparação com os vizinhos imediatos: "
            "'acima' (visivelmente melhor/maior que a média da rua), "
            "'igual' (compatível), "
            "'abaixo' (visivelmente pior/menor)."
        ),
    )
    pool_observed_nearby: bool | None = Field(
        default=None,
        description=(
            "Há piscinas visíveis nos lotes adjacentes ao PIN VERMELHO na"
            " vista aérea (raio aproximado de 100m do imóvel-alvo)? Conte"
            " explicitamente — qualquer retângulo/oval azul nos quintais"
            " conta como piscina. ``True`` se ≥1 piscina visível, ``False``"
            " se zero. ``None`` apenas quando a aérea estiver borrada ou"
            " obstruída por nuvens."
        ),
    )
    suggested_renovation_level: SuggestedRenovationLevel | None = Field(
        default=None,
        description=(
            "Sugestão de nível de reforma compatível com o padrão observado,"
            " em ordem crescente de custo:"
            " 'none' (nenhuma) / 'cosmetic' (R$150/m²) / 'light' (R$300/m²)"
            " / 'basic' (R$500/m²) / 'moderate' (R$1.000/m²)"
            " / 'full' (R$1.500/m²) / 'premium' (R$2.500/m²)."
        ),
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Lista curta de RISCOS DO ENTORNO observados (não do interior do"
            " imóvel). Frases curtas, acionáveis. Ex.: 'rua sem asfalto',"
            " 'lixo acumulado na calçada', 'casa abandonada ao lado',"
            " 'área comercial ruidosa no entorno', 'sinais de inundação'."
        ),
        max_length=10,
    )
    notes: str | None = Field(
        default=None,
        max_length=600,
        description="Observações livres do modelo (até 600 chars).",
    )
    confidence: Confidence = Field(
        default="LOW",
        description=(
            "Confiança na leitura do ENTORNO. HIGH = Street View + aérea"
            " conclusivos; MEDIUM = só uma fonte boa; LOW = imagens"
            " inconclusivas ou sem cobertura."
        ),
    )


_SYSTEM_PROMPT: Final[str] = (
    "Você é um perito em avaliação de imóveis para leilão. Recebe um pacote"
    " de imagens DO ENTORNO de um imóvel (foto do edital, Street View dos"
    " vizinhos imediatos e — por último — vista aérea com PIN VERMELHO no"
    " imóvel-alvo) e devolve em JSON: padrão construtivo do bairro,"
    " comparação do imóvel com os vizinhos, contagem de piscinas próximas,"
    " sugestão de nível de reforma e risk flags do ENTORNO."
    "\n"
    "REGRAS:"
    "\n - Avalie o ENTORNO, não o interior. As fotos não mostram o miolo"
    " do imóvel; não especule sobre hidráulica/elétrica/acabamento interno."
    "\n - Piscinas: olhe APENAS a vista aérea (a foto com PIN VERMELHO)."
    " Conte retângulos/ovais azuis nos quintais vizinhos num raio de ~100m"
    " do pin. Mesmo 1 piscina já é ``pool_observed_nearby=true``. Não"
    " confunda telhados azulados, lonas ou caixas d'água com piscinas."
    "\n - Itens em ``risk_flags`` devem ser visíveis nas imagens (rua,"
    " calçada, terreno, casas vizinhas). NÃO inventar."
    "\n - Se as imagens forem inconclusivas (sem cobertura SV, aérea borrada),"
    " devolva tudo null com confidence=LOW."
    "\n - Em PT-BR, frases curtas e acionáveis."
)


def _encode_image(content: bytes, mime: str = "image/jpeg") -> str:
    """Converte bytes em data URL base64 (formato aceito pelo OpenAI Vision)."""
    b64 = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{b64}"


class VisionService:
    """Wrapper ao GPT-4o multimodal para avaliação visual do entorno."""

    def __init__(self, *, api_key: str, model: str = "gpt-4o") -> None:
        # ``temperature=0`` deixa o output mais determinístico — bom para
        # auditoria entre re-execuções.
        self._llm = ChatOpenAI(
            api_key=api_key, model=model, temperature=0
        ).with_structured_output(NeighborhoodVisionPayload)
        self._model = model

    def assess(
        self, images: list[tuple[str, bytes | str]]
    ) -> NeighborhoodVisionPayload | None:
        """Avalia o pacote de imagens e devolve o payload cru.

        ``images`` é uma lista de ``(slot, content)`` onde ``content`` é:
        - ``bytes``: bytes binários (imagens do Static APIs com chave embutida)
        - ``str``: URL pública (foto do edital — passada direto sem download)

        NÃO levanta — em qualquer falha devolve ``None``.
        """
        if not images:
            return None

        # Reordena ``images`` pela ordem canônica de ``_SLOT_ORDER`` — a aérea
        # vai por último (maior peso atencional para a tarefa de contar piscinas).
        ordered = sorted(
            images,
            key=lambda item: (
                _SLOT_ORDER.index(item[0]) if item[0] in _SLOT_ORDER else 99
            ),
        )

        # Monta o conteúdo multipart: 1 texto descritivo + N image_url blocks.
        # Cada bloco é precedido por um text com a legenda do slot, para o
        # modelo saber qual imagem é qual. ``detail=high`` é obrigatório para
        # detectar piscinas e padrões de telhado em zoom=19/20.
        content_blocks: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"Pacote com {len(ordered)} imagens do entorno"
                    " (foto edital / Street View / aérea, nessa ordem)."
                    " Avalie e devolva o JSON estruturado conforme as"
                    " instruções."
                ),
            }
        ]
        for slot, payload in ordered:
            label = SLOT_LABELS.get(slot, slot)
            content_blocks.append({"type": "text", "text": f"[{slot}] {label}"})
            if isinstance(payload, bytes):
                url = _encode_image(payload)
            else:
                url = payload
            content_blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": url, "detail": "high"},
                }
            )

        try:
            logger.info(
                "vision.assess.start",
                n_images=len(ordered),
                slots=[s for s, _ in ordered],
                detail="high",
                model=self._model,
            )
            payload = self._llm.invoke(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": content_blocks},
                ]
            )
        except Exception as exc:  # noqa: BLE001 — categórico para o caller
            logger.warning("vision.assess.failed", error=str(exc))
            return None

        return payload if isinstance(payload, NeighborhoodVisionPayload) else None


@lru_cache(maxsize=1)
def get_vision_service() -> VisionService:
    settings = get_settings()
    return VisionService(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
    )


__all__ = [
    "NeighborhoodVisionPayload",
    "VisionService",
    "VisionServiceError",
    "get_vision_service",
]
