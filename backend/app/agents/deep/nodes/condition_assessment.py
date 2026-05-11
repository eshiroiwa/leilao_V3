"""Nó CONDITION ASSESSMENT — análise visual da foto do edital.

Delega ao :class:`VisionService` (GPT-4o multimodal) a inferência do
estado de conservação aparente e a sugestão de nível de reforma. NÃO
sobrescreve o ``renovation_level`` informado pelo usuário no Agente 3 —
o output deste nó é puramente informativo (red flags + sugestão).

Falha silenciosa: erro de rede, quota ou imagem inválida → devolve um
``ConditionAssessmentResult`` com tudo None (o Deep continua sem este
sinal). Custo: ~US$ 0,03 por imagem (GPT-4o).
"""

from __future__ import annotations

from app.agents.deep.schemas import ConditionAssessmentResult
from app.core.logging import get_logger
from app.services.vision_service import VisionService

logger = get_logger(__name__)


def assess_condition(
    *,
    image_url: str | None,
    vision: VisionService,
) -> ConditionAssessmentResult:
    """Roda o Vision sobre ``image_url`` e devolve o resultado normalizado.

    ``image_url`` vazio / None → retorna placeholder com confidence LOW
    e notes explicativo, sem chamar o LLM. Falha do LLM (timeout, quota,
    JSON malformado) → placeholder com nota de erro.
    """
    if not image_url:
        return ConditionAssessmentResult(
            image_url=None, confidence="LOW",
            notes="property sem image_url — Vision não executado.",
        )
    payload = vision.assess(image_url)
    if payload is None:
        return ConditionAssessmentResult(
            image_url=image_url, confidence="LOW",
            notes="Vision LLM falhou ou devolveu payload inválido.",
        )
    result = ConditionAssessmentResult(
        conservation_level=payload.conservation_level,
        suggested_renovation_level=payload.suggested_renovation_level,
        risk_flags=list(payload.risk_flags),
        image_url=image_url,
        notes=payload.notes,
        confidence=payload.confidence,
        cost_estimate_usd=0.03,
    )
    logger.info(
        "deep.condition_assessment.done",
        image_url=image_url,
        conservation=result.conservation_level,
        suggested_renovation=result.suggested_renovation_level,
        n_risk_flags=len(result.risk_flags),
        confidence=result.confidence,
    )
    return result


__all__ = ["assess_condition"]
