"""AGENTE 4 — orquestrador.

Fluxo geral:

1. ``get_or_create_deep_analysis`` → trata cache (TTL 7 dias) e cria a row
   ``status='pending'`` se for o caso. Retorna a row e um "deve_executar?".
2. ``enqueue_deep_analysis`` → ponto de entrada para o ``BackgroundTasks``
   do FastAPI. Atualiza status para ``running``, executa o pipeline,
   grava resultado e seta ``completed`` ou ``failed``.
3. ``run_deep_analysis_inline`` → utilizada por testes e por *force-run*
   sem persistência (debug).

Não usamos LangGraph aqui — o pipeline é I/O-bound com fan-out paralelo,
e ``asyncio.gather`` é mais simples e mais rápido.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.agents.deep.nodes.amenities import fetch_amenities
from app.agents.deep.nodes.demographics import fetch_demographics
from app.agents.deep.nodes.neighborhood_stats import (
    compute_flipping_potential,
    compute_liquidity,
)
from app.agents.deep.nodes.outlier import compute_outlier
from app.agents.deep.nodes.price_trend import compute_price_trend
from app.agents.deep.nodes.prior_auction import fetch_prior_auction_signals
from app.agents.deep.nodes.synthesize import synthesize
from app.agents.deep.nodes.urban_risks import fetch_urban_risks
from app.agents.deep.schemas import (
    AmenitiesResult,
    DemographicsResult,
    FlippingResult,
    LiquidityResult,
    OutlierResult,
    PriceTrendResult,
    PriorAuctionResult,
    SourceDocument,
    SynthesisOutput,
    UrbanRisksResult,
)
from app.core.logging import get_logger
from app.services.firecrawl_service import FirecrawlService, get_firecrawl_service
from app.services.google_maps_service import (
    GoogleMapsService,
    get_google_maps_service,
)
from app.services.supabase_service import SupabaseService, get_supabase_service

logger = get_logger(__name__)

CACHE_TTL = timedelta(days=7)
"""Quanto tempo uma análise ``completed`` é considerada fresca."""

NEIGHBORHOOD_RADIUS_M = 2_000
"""Raio para buscar listings vizinhos."""

STALE_RUNNING_TIMEOUT = timedelta(minutes=10)
"""Análise ``running`` há mais que isso é considerada presa (server crash)."""


# =============================================================================
# Cache + criação da row pending
# =============================================================================
def get_or_create_deep_analysis(
    *,
    supabase: SupabaseService,
    property_id: str,
    opportunity_analysis_id: str | None,
    force_refresh: bool,
) -> tuple[dict[str, Any], bool]:
    """Implementa o cache de 7 dias.

    Retorna ``(row, should_run)``. Quando ``should_run=False``, ``row`` é
    a análise cacheada que já está completa e fresca.
    """
    if not force_refresh:
        cached = supabase.get_latest_completed_deep_analysis(property_id)
        if cached:
            created_at_str = cached.get("created_at")
            try:
                created_at = datetime.fromisoformat(
                    str(created_at_str).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                created_at = None
            if created_at:
                age = datetime.now(timezone.utc) - created_at
                if age < CACHE_TTL:
                    logger.info(
                        "deep.cache.hit",
                        property_id=property_id,
                        analysis_id=cached.get("id"),
                        age_days=age.days,
                    )
                    return cached, False

    # Sem cache válido → cria row pending.
    pending = supabase.insert_deep_analysis_pending(
        {
            "property_id": property_id,
            "opportunity_analysis_id": opportunity_analysis_id,
        }
    )
    logger.info(
        "deep.run.created_pending",
        property_id=property_id,
        analysis_id=pending["id"],
    )
    return pending, True


# =============================================================================
# Núcleo do pipeline (sem persistência)
# =============================================================================
async def run_deep_analysis_inline(
    *,
    supabase: SupabaseService,
    firecrawl: FirecrawlService,
    gmaps: GoogleMapsService,
    property_id: str,
) -> dict[str, Any]:
    """Executa o pipeline ponta-a-ponta SEM persistir. Retorna um dict
    pronto para ser usado como ``UPDATE`` na row ``deep_analyses``.

    Levanta ``ValueError`` se a property não existir, ou se faltarem
    coordenadas (sem lat/lng não dá pra fazer nada útil)."""
    started = time.perf_counter()

    prop = supabase.get_property_by_id(property_id)
    if not prop:
        raise ValueError(f"property_id={property_id} não encontrado")

    lat = prop.get("latitude")
    lng = prop.get("longitude")
    if lat is None or lng is None:
        raise ValueError(
            "Imóvel sem coordenadas geocodificadas — execute o Agente 1 antes."
        )
    lat = float(lat)
    lng = float(lng)

    city = (prop.get("city") or "").strip()
    state = (prop.get("state") or "").strip()
    neighborhood = prop.get("neighborhood")
    target_area = prop.get("area_total_m2")
    target_price = (
        prop.get("estimated_price")
        or prop.get("minimum_bid_first")
        or prop.get("minimum_bid_second")
    )

    # ----- 1. Carrega vizinhos do banco (puro, rápido) ---------------------
    neighbors = supabase.find_listings_near(
        lat=lat,
        lng=lng,
        radius_m=NEIGHBORHOOD_RADIUS_M,
        property_type=prop.get("property_type"),
        limit=300,
    )
    logger.info(
        "deep.neighbors.loaded",
        property_id=property_id,
        n=len(neighbors),
    )

    # ----- 2. Nós PUROS (sem rede) — rodam síncronos -----------------------
    outlier: OutlierResult = compute_outlier(
        target_area_m2=float(target_area) if target_area else None,
        target_price=float(target_price) if target_price else None,
        neighbors=neighbors,
    )
    flipping: FlippingResult = compute_flipping_potential(
        neighbors=neighbors,
        target_price=float(target_price) if target_price else None,
    )
    price_trend: PriceTrendResult = compute_price_trend(neighbors)

    # ----- 3. Nós com I/O — rodam em paralelo ------------------------------
    address_full = (
        f"{prop.get('street', '')} {prop.get('number', '')} "
        f"{neighborhood or ''} {city} {state}"
    ).strip()

    demographics_task = fetch_demographics(
        firecrawl=firecrawl, city=city, state=state
    )
    amenities_task = fetch_amenities(gmaps=gmaps, lat=lat, lng=lng)
    urban_risks_task = fetch_urban_risks(
        firecrawl=firecrawl,
        neighborhood=neighborhood,
        city=city,
        state=state,
    )
    prior_auction_task = fetch_prior_auction_signals(
        firecrawl=firecrawl,
        address_full=address_full,
        matricula=prop.get("registry_number") or prop.get("matricula"),
    )

    # asyncio.gather + return_exceptions para que UM nó com falha NÃO
    # derrube o pipeline inteiro.
    results = await asyncio.gather(
        demographics_task,
        amenities_task,
        urban_risks_task,
        prior_auction_task,
        return_exceptions=True,
    )

    def _ok(r: Any, default: Any) -> Any:
        if isinstance(r, Exception):
            logger.error("deep.subnode.exception", error=str(r))
            return default
        return r

    demographics_pair = _ok(
        results[0], (DemographicsResult(confidence="LOW"), [])
    )
    amenities = _ok(results[1], AmenitiesResult())
    urban_risks_pair = _ok(results[2], (UrbanRisksResult(), []))
    prior_auction_pair = _ok(results[3], (PriorAuctionResult(), []))

    demographics, demo_docs = demographics_pair
    urban_risks, risk_docs = urban_risks_pair
    prior_auction, auction_docs = prior_auction_pair

    # ----- 4. Liquidez depende da população (calculado AGORA) --------------
    liquidity: LiquidityResult = compute_liquidity(
        neighbors=neighbors,
        city_population=demographics.city_population,
    )

    # ----- 5. Síntese (LLM) ------------------------------------------------
    property_summary = {
        "property_id": property_id,
        "city": city,
        "state": state,
        "neighborhood": neighborhood,
        "property_type": prop.get("property_type"),
        "area_total_m2": prop.get("area_total_m2"),
        "bedrooms": prop.get("bedrooms"),
        "occupancy_status": prop.get("occupancy_status"),
        "minimum_bid_first": prop.get("minimum_bid_first"),
        "minimum_bid_second": prop.get("minimum_bid_second"),
    }

    synthesis: SynthesisOutput = await synthesize(
        property_summary=property_summary,
        demographics=demographics,
        liquidity=liquidity,
        outlier=outlier,
        flipping=flipping,
        price_trend=price_trend,
        amenities=amenities,
        urban_risks=urban_risks,
        prior_auction=prior_auction,
    )

    # ----- 6. Monta payload de UPDATE --------------------------------------
    sources: list[SourceDocument] = [*demo_docs, *risk_docs, *auction_docs]
    duration_ms = int((time.perf_counter() - started) * 1000)
    # 4 fontes externas (search + scrape) ≈ 4-6 calls; síntese + 2 extrações ≈ 3 LLM calls.
    fc_calls = len(sources)
    llm_calls = 1  # síntese
    if demographics.city_population is not None:
        llm_calls += 1
    if urban_risks.items:
        llm_calls += 1

    return {
        # Demografia / liquidez
        "city_population": demographics.city_population,
        "city_population_year": demographics.city_population_year,
        "city_population_source": demographics.source,
        "liquidity_score": liquidity.score,
        "liquidity_confidence": liquidity.confidence,
        "liquidity_evidence": liquidity.evidence,
        # Outlier
        "is_outlier_size": outlier.is_outlier_size,
        "is_outlier_price": outlier.is_outlier_price,
        "size_zscore": outlier.size_zscore,
        "price_zscore": outlier.price_zscore,
        "outlier_evidence": outlier.evidence,
        # Flipping
        "neighborhood_price_max": flipping.neighborhood_price_max,
        "neighborhood_price_p90": flipping.neighborhood_price_p90,
        "neighborhood_ppm2_p90": flipping.neighborhood_ppm2_p90,
        "flipping_potential_score": flipping.score,
        "flipping_evidence": flipping.evidence,
        # Trend
        "price_trend_12m_pct": price_trend.trend_pct_12m,
        "price_trend_confidence": price_trend.confidence,
        "price_trend_evidence": price_trend.evidence,
        # Amenities
        "nearest_metro_m": amenities.nearest_metro_m,
        "nearest_school_m": amenities.nearest_school_m,
        "nearest_hospital_m": amenities.nearest_hospital_m,
        "amenities_evidence": amenities.evidence,
        # Urban risks
        "urban_risks": [r.model_dump() for r in urban_risks.items],
        # Prior auction
        "prior_auction_count": prior_auction.count,
        "prior_auction_evidence": prior_auction.evidence,
        # Synthesis
        "overall_score": synthesis.overall_score,
        "summary_text": synthesis.summary_text,
        "red_flags": synthesis.red_flags,
        "green_flags": synthesis.green_flags,
        "recommendations": synthesis.recommendations,
        # Auditoria
        "source_documents": [s.model_dump(mode="json") for s in sources],
        "duration_ms": duration_ms,
        "firecrawl_calls": fc_calls,
        "llm_calls": llm_calls,
        # Estimativa pessimista de custo (~$0.005 por LLM call + ~$0.005 por fc).
        "cost_estimate_usd": round(0.005 * (fc_calls + llm_calls), 4),
    }


# =============================================================================
# Entrypoint para BackgroundTasks (FastAPI)
# =============================================================================
def enqueue_deep_analysis(analysis_id: str) -> None:
    """Roda o pipeline para a row ``analysis_id`` e atualiza seu status.

    Esta função NÃO levanta exceções — captura tudo e seta
    ``status='failed'`` com a mensagem de erro. É chamada pelo
    ``BackgroundTasks.add_task`` (que NÃO trata exceções por padrão).
    """
    supabase = get_supabase_service()
    firecrawl = get_firecrawl_service()
    gmaps = get_google_maps_service()

    started_at_iso = datetime.now(timezone.utc).isoformat()
    try:
        supabase.update_deep_analysis(
            analysis_id, {"status": "running", "started_at": started_at_iso}
        )
    except Exception as exc:
        logger.error(
            "deep.status.update_failed",
            analysis_id=analysis_id,
            error=str(exc),
        )
        return

    row = supabase.get_deep_analysis(analysis_id)
    if not row:
        logger.error("deep.row.missing", analysis_id=analysis_id)
        return
    property_id = row["property_id"]

    try:
        update_payload = asyncio.run(
            run_deep_analysis_inline(
                supabase=supabase,
                firecrawl=firecrawl,
                gmaps=gmaps,
                property_id=property_id,
            )
        )
    except Exception as exc:
        logger.exception("deep.pipeline.failed", analysis_id=analysis_id)
        try:
            supabase.update_deep_analysis(
                analysis_id,
                {
                    "status": "failed",
                    "error_message": str(exc)[:500],
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            logger.exception("deep.status.failed_write_failed")
        return

    update_payload.update(
        {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    try:
        supabase.update_deep_analysis(analysis_id, update_payload)
        logger.info(
            "deep.pipeline.completed",
            analysis_id=analysis_id,
            duration_ms=update_payload.get("duration_ms"),
        )
    except Exception:
        logger.exception(
            "deep.persist.failed", analysis_id=analysis_id
        )


# =============================================================================
# Helper: detectar análises "presas" como running por > 10 min e marcar failed.
# Chamado preguiçosamente por endpoints de leitura (cheap & idempotente).
# =============================================================================
def reap_stale_running(supabase: SupabaseService, property_id: str) -> None:
    rows = supabase.list_deep_analyses(property_id, limit=20)
    cutoff = datetime.now(timezone.utc) - STALE_RUNNING_TIMEOUT
    for r in rows:
        if r.get("status") != "running":
            continue
        started_at_str = r.get("started_at")
        if not started_at_str:
            continue
        try:
            started_at = datetime.fromisoformat(
                str(started_at_str).replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            continue
        if started_at < cutoff:
            try:
                supabase.update_deep_analysis(
                    r["id"],
                    {
                        "status": "failed",
                        "error_message": "Job presa em 'running' há > 10min (server provavelmente reiniciou).",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception:
                logger.exception("deep.reap.update_failed", analysis_id=r["id"])
