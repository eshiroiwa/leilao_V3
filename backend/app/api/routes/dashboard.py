"""Endpoint agregador da home — dashboard.

Combina dados de ``properties``, ``valuations`` e
``opportunity_analyses`` numa única resposta para alimentar o
dashboard do frontend (KPIs + calendário + top oportunidades +
próximos leilões) sem que o cliente precise fazer N+1 chamadas.

Estratégia: pequenos selects paralelizados via threadpool e
agregação em Python — simples e suficiente para volumes da ordem
de centenas de imóveis. Se a base crescer significativamente,
trocar por uma view materializada ou função RPC no Postgres.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.services.supabase_service import SupabaseError, get_supabase_service

logger = get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Verdicts ranqueados (melhor → pior) para ordenar o "top oportunidades".
_VERDICT_RANK: dict[str, int] = {
    "BOA_OPORTUNIDADE": 0,
    "BOA_COM_RESSALVAS": 1,
    "NEUTRO": 2,
    "INDETERMINADO": 3,
    "INVIAVEL": 4,
}

_GOOD_VERDICTS = {"BOA_OPORTUNIDADE", "BOA_COM_RESSALVAS"}


def _coerce_iso(s: Any) -> str | None:
    """Aceita string ISO e devolve string ISO normalizada (com TZ).

    Os dados vêm do Supabase como string ``YYYY-MM-DDTHH:MM:SS+00:00``
    ou ``YYYY-MM-DD``. Devolve ``None`` se inválido.
    """
    if not isinstance(s, str) or not s:
        return None
    try:
        # ``fromisoformat`` aceita os dois formatos a partir do Python 3.11.
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def _parse_date(s: Any) -> datetime | None:
    iso = _coerce_iso(s)
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _property_summary(p: dict[str, Any]) -> dict[str, Any]:
    """Subconjunto de campos do imóvel suficiente para os cards do dashboard."""
    return {
        "property_id": p.get("id"),
        "title": p.get("title"),
        "image_url": p.get("image_url"),
        "city": p.get("city"),
        "state": p.get("state"),
        "property_type": p.get("property_type"),
        "minimum_bid_first": p.get("minimum_bid_first"),
        "minimum_bid_second": p.get("minimum_bid_second"),
        "appraisal_value": p.get("appraisal_value"),
    }


@router.get(
    "",
    summary="Agregação de dados para o dashboard inicial",
    response_model=dict[str, Any],
)
async def get_dashboard(
    upcoming_window_days: int = Query(30, ge=1, le=365),
    top_opportunities: int = Query(6, ge=1, le=20),
    upcoming_limit: int = Query(8, ge=1, le=50),
    calendar_window_days: int = Query(180, ge=30, le=730),
) -> dict[str, Any]:
    sb = get_supabase_service()

    try:
        properties, valuated_ids, opps = await asyncio.gather(
            run_in_threadpool(sb.list_properties, limit=200),
            run_in_threadpool(sb.list_property_ids_with_valuations),
            run_in_threadpool(sb.list_recent_opportunity_analyses, limit=200),
        )
    except SupabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    # ------------------------------------------------------------------ #
    # Indexes auxiliares
    # ------------------------------------------------------------------ #
    by_id: dict[str, dict[str, Any]] = {p["id"]: p for p in properties if p.get("id")}

    # Mantém apenas a opportunity_analysis mais recente por property
    # (a lista já vem ordenada por created_at desc do supabase_service).
    latest_opp_by_property: dict[str, dict[str, Any]] = {}
    for o in opps:
        pid = o.get("property_id")
        if pid and pid not in latest_opp_by_property:
            latest_opp_by_property[pid] = o

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=upcoming_window_days)
    calendar_end = now + timedelta(days=calendar_window_days)
    calendar_start = now - timedelta(days=calendar_window_days)

    # ------------------------------------------------------------------ #
    # Calendário e próximos leilões
    # ------------------------------------------------------------------ #
    calendar_events: list[dict[str, Any]] = []
    for p in properties:
        first_iso = _coerce_iso(p.get("first_auction_at"))
        second_iso = _coerce_iso(p.get("second_auction_at"))

        for kind, iso, value in (
            ("first", first_iso, p.get("minimum_bid_first")),
            ("second", second_iso, p.get("minimum_bid_second")),
        ):
            if not iso:
                continue
            dt = _parse_date(iso)
            if not dt or dt < calendar_start or dt > calendar_end:
                continue
            calendar_events.append(
                {
                    "date": iso,
                    "kind": kind,  # 'first' | 'second'
                    "value": value,
                    **_property_summary(p),
                }
            )

    # Próximos leilões (apenas futuro, ordenados ascendente)
    upcoming = sorted(
        [e for e in calendar_events if (_parse_date(e["date"]) or now) >= now],
        key=lambda e: _parse_date(e["date"]) or now,
    )[:upcoming_limit]

    # ------------------------------------------------------------------ #
    # Top oportunidades — ordena por (verdict_rank asc, ROI realista desc)
    # ------------------------------------------------------------------ #
    candidates: list[dict[str, Any]] = []
    for pid, opp in latest_opp_by_property.items():
        prop = by_id.get(pid)
        if not prop:
            continue
        verdict = opp.get("verdict") or "INDETERMINADO"
        scenarios = opp.get("scenarios") or {}
        realista = scenarios.get("realista") or {}
        net_roi = realista.get("net_roi_pct")
        net_profit = realista.get("net_profit")
        candidates.append(
            {
                **_property_summary(prop),
                "opportunity_id": opp.get("id"),
                "verdict": verdict,
                "net_roi_pct": net_roi,
                "net_profit": net_profit,
                "bid_amount": opp.get("bid_amount"),
                "created_at": opp.get("created_at"),
            }
        )

    candidates.sort(
        key=lambda c: (
            _VERDICT_RANK.get(c["verdict"], 99),
            -(c["net_roi_pct"] if isinstance(c["net_roi_pct"], int | float) else -1e9),
        )
    )
    top_opps = candidates[:top_opportunities]

    # ------------------------------------------------------------------ #
    # Totais (KPIs)
    # ------------------------------------------------------------------ #
    upcoming_30d = sum(
        1
        for p in properties
        if (
            (dt := _parse_date(p.get("first_auction_at"))) is not None
            and now <= dt <= window_end
        )
        or (
            (dt := _parse_date(p.get("second_auction_at"))) is not None
            and now <= dt <= window_end
        )
    )
    with_geocoding = sum(
        1
        for p in properties
        if p.get("latitude") is not None and p.get("longitude") is not None
    )
    pending_valuation = sum(
        1 for p in properties if p.get("id") not in valuated_ids
    )
    pending_opportunity = sum(
        1 for p in properties if p.get("id") not in latest_opp_by_property
    )
    good_opportunities = sum(
        1 for c in candidates if c["verdict"] in _GOOD_VERDICTS
    )

    totals = {
        "properties": len(properties),
        "with_geocoding": with_geocoding,
        "upcoming_30d": upcoming_30d,
        "pending_valuation": pending_valuation,
        "pending_opportunity": pending_opportunity,
        "good_opportunities": good_opportunities,
    }

    return {
        "totals": totals,
        "calendar": calendar_events,
        "top_opportunities": top_opps,
        "upcoming_auctions": upcoming,
        "generated_at": now.isoformat(),
    }
