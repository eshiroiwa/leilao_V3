"""Nó CONDITION ASSESSMENT — análise visual do ENTORNO.

Captura um pacote de imagens geocodificadas (aérea + 4 Street Views +
foto do edital quando disponível), persiste em Supabase Storage e
delega ao :class:`VisionService` (GPT-4o multimodal) a leitura do
entorno (padrão do bairro, comparação com vizinhos, piscinas próximas,
sugestão de reforma, risk flags ambientais).

NÃO sobrescreve o ``renovation_level`` do Agente 3 — output puramente
informativo.

Falha silenciosa em cada etapa: sem cobertura SV pula SV, falha de
upload pula aquela URL, Vision retornando None devolve placeholder com
``confidence=LOW``. O pipeline nunca quebra por causa desse nó.

Custo: ~$0.08-0.10 por análise (5 Static APIs + 6 imagens GPT-4o).
"""

from __future__ import annotations

import httpx

from app.agents.deep.schemas import ConditionAssessmentResult
from app.core.logging import get_logger
from app.services.google_maps_service import GoogleMapsService
from app.services.supabase_service import SupabaseService
from app.services.vision_service import VisionService

logger = get_logger(__name__)

# Headings padrão dos 4 Street Views — frente / esquerda / oposto / direita.
SV_HEADINGS: tuple[tuple[str, int], ...] = (
    ("sv_front", 0),
    ("sv_left", 90),
    ("sv_back", 180),
    ("sv_right", 270),
)

CONDITION_COST_USD = 0.10
"""Estimativa: 4 SV ($0.028) + 1 aérea ($0.002) + 6 imgs Vision GPT-4o (~$0.07)."""


def _download_listing_image(url: str) -> bytes | None:
    """Baixa a foto do edital (URL externa pública) para reupload no Storage."""
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPError as exc:
        logger.warning(
            "condition.listing.download_failed", url=url, error=str(exc)
        )
        return None


def assess_condition(
    *,
    property_id: str,
    analysis_id: str | None,
    lat: float,
    lng: float,
    image_url: str | None,
    vision: VisionService,
    gmaps: GoogleMapsService,
    supabase: SupabaseService,
) -> ConditionAssessmentResult:
    """Captura entorno + envia ao Vision + persiste imagens no Storage."""
    slots: list[tuple[str, bytes]] = []

    # 1. Vista aérea (sempre tentamos — barata, $0.002).
    aerial = gmaps.static_satellite(lat, lng)
    if aerial:
        slots.append(("aerial", aerial))

    # 2. Street Views — pré-checa cobertura via Metadata (grátis).
    meta = gmaps.streetview_metadata(lat, lng)
    sv_status = (meta or {}).get("status")
    if sv_status == "OK":
        for slot, heading in SV_HEADINGS:
            img = gmaps.streetview_image(lat, lng, heading=heading)
            if img:
                slots.append((slot, img))
    else:
        logger.info(
            "condition.streetview.skipped",
            status=sv_status or "NO_METADATA",
            lat=lat,
            lng=lng,
        )

    # 3. Foto do edital (re-hospedada para reproducibilidade).
    if image_url:
        listing_bytes = _download_listing_image(image_url)
        if listing_bytes:
            slots.append(("listing", listing_bytes))

    if not slots:
        return ConditionAssessmentResult(
            confidence="LOW",
            notes="nenhuma imagem disponível (sem cobertura SV + sem foto edital).",
        )

    # 4. Persiste cada imagem em Storage e coleta URLs públicas.
    # Pula upload em execuções inline/debug (sem analysis_id) — o pipeline
    # ainda roda o Vision para inspeção, só não persiste as URLs.
    image_urls: list[str] = []
    if analysis_id:
        for slot, content in slots:
            public = supabase.upload_deep_image(
                property_id=property_id,
                analysis_id=analysis_id,
                slot=slot,
                content=content,
            )
            if public:
                image_urls.append(public)

    # 5. Chama Vision com todas as imagens (bytes — converte internamente
    # para base64 data URLs, já que as URLs do Google embutem a API key).
    payload = vision.assess([(slot, content) for slot, content in slots])
    if payload is None:
        return ConditionAssessmentResult(
            image_urls=image_urls,
            confidence="LOW",
            notes="Vision LLM falhou ou devolveu payload inválido.",
            cost_estimate_usd=CONDITION_COST_USD,
        )

    result = ConditionAssessmentResult(
        neighborhood_pattern=payload.neighborhood_pattern,
        property_vs_neighbors=payload.property_vs_neighbors,
        pool_observed_nearby=payload.pool_observed_nearby,
        suggested_renovation_level=payload.suggested_renovation_level,
        risk_flags=list(payload.risk_flags),
        image_urls=image_urls,
        notes=payload.notes,
        confidence=payload.confidence,
        cost_estimate_usd=CONDITION_COST_USD,
    )
    logger.info(
        "deep.condition_assessment.done",
        n_images=len(slots),
        n_uploaded=len(image_urls),
        neighborhood_pattern=result.neighborhood_pattern,
        property_vs_neighbors=result.property_vs_neighbors,
        pool_observed_nearby=result.pool_observed_nearby,
        suggested_renovation=result.suggested_renovation_level,
        n_risk_flags=len(result.risk_flags),
        confidence=result.confidence,
    )
    return result


__all__ = ["assess_condition"]
