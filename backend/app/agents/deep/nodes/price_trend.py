"""Nó PRICE TREND — variação de preço/m² nos últimos 12 meses (proxy).

Limitação intelectualmente honesta: nossos listings têm ``scraped_at``,
não ``listed_at`` ou histórico de preço. O proxy mais próximo é dividir
a amostra em "primeiro semestre" vs "segundo semestre" da janela coletada
e medir a diferença de medianas.

* Se a janela coletada for < 6 meses → confiança LOW e devolvemos null.
* Se houver < 8 listings em cada bucket → confiança LOW.
* Caso contrário, MEDIUM. Nunca declaramos HIGH aqui — é proxy, não série
  histórica de transações.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any

from app.agents.deep.schemas import PriceTrendResult

MIN_PER_BUCKET = 8
MIN_WINDOW_DAYS = 180


def _ppm2(row: dict[str, Any]) -> float | None:
    p = row.get("listed_price")
    a = row.get("area_total_m2")
    if not p or not a or float(a) <= 0:
        return None
    return float(p) / float(a)


def _scraped_at(row: dict[str, Any]) -> datetime | None:
    raw = row.get("scraped_at") or row.get("created_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def compute_price_trend(neighbors: list[dict[str, Any]]) -> PriceTrendResult:
    """Diferença % entre a mediana de ppm² dos buckets recente vs antigo."""
    enriched: list[tuple[datetime, float]] = []
    for r in neighbors:
        dt = _scraped_at(r)
        ppm2 = _ppm2(r)
        if dt and ppm2:
            enriched.append((dt, ppm2))

    if len(enriched) < MIN_PER_BUCKET * 2:
        return PriceTrendResult(
            confidence="LOW",
            evidence={
                "n_with_date_and_price": len(enriched),
                "min_required": MIN_PER_BUCKET * 2,
                "reason": "amostra_insuficiente",
            },
        )

    enriched.sort(key=lambda x: x[0])
    oldest = enriched[0][0]
    newest = enriched[-1][0]
    window_days = (newest - oldest).total_seconds() / 86_400.0
    if window_days < MIN_WINDOW_DAYS:
        return PriceTrendResult(
            confidence="LOW",
            evidence={
                "window_days": round(window_days, 1),
                "min_window_days": MIN_WINDOW_DAYS,
                "reason": "janela_curta",
            },
        )

    midpoint = oldest + (newest - oldest) / 2
    older = [v for (dt, v) in enriched if dt < midpoint]
    newer = [v for (dt, v) in enriched if dt >= midpoint]

    if len(older) < MIN_PER_BUCKET or len(newer) < MIN_PER_BUCKET:
        return PriceTrendResult(
            confidence="LOW",
            evidence={
                "older_count": len(older),
                "newer_count": len(newer),
                "min_per_bucket": MIN_PER_BUCKET,
                "reason": "buckets_desbalanceados",
            },
        )

    older_med = median(older)
    newer_med = median(newer)
    if older_med == 0:
        trend_pct = None
    else:
        trend_pct = (newer_med / older_med - 1.0) * 100.0

    # Anualiza para "12 meses" — multiplica pela razão (365 / window_days).
    annualized = (
        (trend_pct or 0.0) * (365.0 / window_days) if trend_pct is not None else None
    )

    return PriceTrendResult(
        trend_pct_12m=round(annualized, 2) if annualized is not None else None,
        confidence="MEDIUM",
        evidence={
            "older_bucket_n": len(older),
            "newer_bucket_n": len(newer),
            "older_ppm2_median": round(older_med, 2),
            "newer_ppm2_median": round(newer_med, 2),
            "window_days": round(window_days, 1),
            "raw_pct_in_window": round(trend_pct, 2) if trend_pct is not None else None,
        },
    )
