"""Vision LLM (OpenAI GPT-4o multimodal) sobre fotos do edital.

Avalia estado de conservação visual do imóvel e sugere nível de reforma
COMO SINAL OPCIONAL — sem sobrescrever a escolha do usuário no Agente 3.
Detecta itens problemáticos (estrutura, hidráulica/elétrica antigas,
fachada, umidade) que viram red flags no Deep Analysis.

Por que não automatizar a substituição: foto do edital pode ser do
prédio (não do interior), de ângulo ruim, ou desatualizada. O modelo
tem viés e a estimativa não pode virar o número que entra no
``renovation_cost`` sem confirmação humana. Este nó GERA INFORMAÇÃO,
não muda cálculo.

Custo por chamada: ~US$ 0,01–0,05 por imagem (modelo GPT-4o), 1
chamada por property. Falha silenciosa: erro de rede / quota → o
nó devolve ``ConditionAssessmentResult`` com tudo None.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final, Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.logging import get_logger

# Tipos locais — evitam circular import com agents.deep.schemas (que
# importa esse service ao montar o pipeline).
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
ConservationLevel = Literal["novo", "bom", "regular", "mau", "ruina"]
SuggestedRenovationLevel = Literal["none", "basic", "moderate", "full", "premium"]

logger = get_logger(__name__)


class VisionServiceError(RuntimeError):
    """Falha ao chamar o modelo multimodal."""


# Estrutura forçada de retorno do LLM — Pydantic + structured output.
class VisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conservation_level: ConservationLevel | None = Field(
        default=None,
        description=(
            "Estado físico aparente: 'novo' (impecável, acabamento recente);"
            " 'bom' (sem reformas estruturais necessárias); 'regular'"
            " (acabamento antigo mas estrutura íntegra); 'mau' (acabamento"
            " degradado, sinais de obra retrabalho); 'ruina' (estrutura"
            " comprometida, demolição/reconstrução)."
        ),
    )
    suggested_renovation_level: SuggestedRenovationLevel | None = Field(
        default=None,
        description=(
            "Sugestão de nível de reforma compatível com o estado observado:"
            " 'none' / 'basic' (pintura/reparos) / 'moderate' (acabamentos)"
            " / 'full' (reforma estrutural) / 'premium' (alto padrão)."
        ),
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description=(
            "Lista curta de itens problemáticos OBSERVADOS na foto (não"
            " inferidos). Frases curtas, acionáveis. Ex.: 'rachadura"
            " estrutural na parede da sala', 'fiação aparente antiga',"
            " 'mancha de umidade no teto', 'fachada com gesso solto'."
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
            "Confiança do modelo na avaliação: HIGH (foto clara do interior),"
            " MEDIUM (parcialmente visível), LOW (foto da fachada apenas /"
            " baixa resolução / ângulo ruim)."
        ),
    )


_SYSTEM_PROMPT: Final[str] = (
    "Você é um perito em avaliação de imóveis para leilão. Recebe UMA foto"
    " de um imóvel anunciado no edital e devolve em JSON: o estado de"
    " conservação aparente, um nível de reforma sugerido, e uma lista"
    " curta de itens problemáticos OBSERVADOS (não inferidos)."
    "\n"
    "REGRAS:"
    "\n - Não invente: se a foto for da fachada apenas, NÃO especule sobre"
    " o interior; reduza a confidence para LOW."
    "\n - Itens em ``risk_flags`` devem ser visíveis na foto, não suposições"
    " genéricas. Exemplo aceitável: 'mancha extensa de umidade no teto'."
    " Exemplo NÃO aceitável: 'pode ter problemas na hidráulica' (não dá"
    " pra ver hidráulica numa foto)."
    "\n - Em PT-BR, frases curtas e acionáveis."
    "\n - Se a imagem não for de imóvel ou for ilegível, devolva tudo null."
)


class VisionService:
    """Wrapper ao GPT-4o multimodal para avaliação visual de imóveis."""

    def __init__(self, *, api_key: str, model: str = "gpt-4o") -> None:
        # ``temperature=0`` deixa o output mais determinístico — bom para
        # auditoria entre re-execuções.
        self._llm = ChatOpenAI(
            api_key=api_key, model=model, temperature=0
        ).with_structured_output(VisionPayload)
        self._model = model

    def assess(self, image_url: str) -> VisionPayload | None:
        """Avalia a imagem e devolve o ``VisionPayload`` cru.

        NÃO levanta — em qualquer falha (URL inválida, modelo fora do ar,
        quota), devolve ``None`` (caller usa um default seguro). Mantemos
        o serviço desacoplado dos schemas do Agente 4 para evitar circular
        import.
        """
        if not image_url or not image_url.strip():
            return None

        try:
            logger.info("vision.assess.start", image_url=image_url, model=self._model)
            payload = self._llm.invoke(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Avalie esta foto de imóvel anunciado em leilão."
                                    " Devolva o JSON estruturado conforme as instruções."
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ]
            )
        except Exception as exc:  # noqa: BLE001 — categórico para o caller
            logger.warning("vision.assess.failed", image_url=image_url, error=str(exc))
            return None

        return payload if isinstance(payload, VisionPayload) else None


@lru_cache(maxsize=1)
def get_vision_service() -> VisionService:
    settings = get_settings()
    return VisionService(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_model,
    )


__all__ = [
    "VisionPayload",
    "VisionService",
    "VisionServiceError",
    "get_vision_service",
]
