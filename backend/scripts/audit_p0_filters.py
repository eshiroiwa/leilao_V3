"""Auditoria do impacto dos filtros P0 (auto-self + hard area filter).

Para cada propriedade com CMA salva, simula a aplicação dos filtros novos
sobre os comparables JÁ SCORADOS no banco e mostra:

  * quantos comparáveis seriam re-rejeitados como ``auto_self``;
  * quantos seriam re-rejeitados pelo hard filter de área (strict);
  * quantos sobrariam usados (vs hoje).

Não altera nada no banco — só lê e relata. Útil para decidir se a CMA
de um imóvel específico precisa ser re-rodada.

Uso:
    python -m scripts.audit_p0_filters [--property-id <uuid>]

Sem ``--property-id``, audita TODAS as propriedades com pelo menos uma
``valuation`` salva (ordenadas pela mais recente).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from app.agents.comparables.scoring import (
    area_outside_tolerance,
    is_likely_target_self,
)
from app.agents.comparables.type_config import get_type_config
from app.services.supabase_service import get_supabase_service


def _audit_property(sb, property_id: str) -> dict | None:
    """Audita uma propriedade. Devolve um dict-resumo ou None se vazio."""
    target = sb.get_property_by_id(property_id)
    if not target:
        return None

    # Pega a valuation mais recente.
    val_resp = (
        sb._client.table("valuations")
        .select("id, estimated_price, ppm2_estimated, confidence, created_at")
        .eq("property_id", property_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not val_resp.data:
        return None
    val = val_resp.data[0]

    # Pega comparables com join nos listings.
    rows_resp = (
        sb._client.table("valuation_comparables")
        .select(
            "listing_id, used, weight, similarity_score, distance_m, "
            "rejection_reason, "
            "listings!inner(id, listed_price, area_total_m2, area_useful_m2, "
            "latitude, longitude, property_type, condo_name, source_url, "
            "city, neighborhood)"
        )
        .eq("valuation_id", val["id"])
        .execute()
    )
    rows = rows_resp.data or []
    if not rows:
        return None

    eff_type, type_config = get_type_config(target)

    n_total = len(rows)
    n_used_now = sum(1 for r in rows if r.get("used"))
    new_self_rejects: list[dict] = []
    new_area_rejects: list[dict] = []
    re_breakdown: Counter[str] = Counter()

    for r in rows:
        listing = r.get("listings") or {}
        is_self = is_likely_target_self(target, listing, config=type_config)
        if is_self:
            new_self_rejects.append(
                {
                    "listing_id": listing.get("id"),
                    "url": listing.get("source_url"),
                    "price": listing.get("listed_price"),
                    "currently_used": r.get("used"),
                }
            )
            re_breakdown["auto_self"] += 1
            continue
        oob = area_outside_tolerance(target, listing, config=type_config)
        if oob:
            new_area_rejects.append(
                {
                    "listing_id": listing.get("id"),
                    "url": listing.get("source_url"),
                    "reason": oob,
                    "currently_used": r.get("used"),
                }
            )
            re_breakdown["area_oob"] += 1

    # n_used_after = n_used_now - todos os used que cairiam em auto_self ou area_oob
    n_lost = sum(
        1
        for r in (new_self_rejects + new_area_rejects)
        if r.get("currently_used")
    )

    return {
        "property_id": property_id,
        "valuation_id": val["id"],
        "city": target.get("city"),
        "state": target.get("state"),
        "property_type": target.get("property_type"),
        "effective_type": eff_type,
        "area_field": type_config.area_field,
        "area_hard_max_pct": type_config.area_hard_max,
        "n_comparables_total": n_total,
        "n_used_now": n_used_now,
        "n_used_after_filters": n_used_now - n_lost,
        "n_lost_used": n_lost,
        "n_self_rejected": len(new_self_rejects),
        "n_area_rejected": len(new_area_rejects),
        "self_rejected_examples": new_self_rejects[:3],
        "area_rejected_examples": new_area_rejects[:3],
    }


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument(
        "--property-id",
        help="UUID da property a auditar. Se omitido, audita todas as mais recentes.",
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Quantas properties auditar."
    )
    args = parser.parse_args()

    sb = get_supabase_service()

    if args.property_id:
        ids = [args.property_id]
    else:
        resp = (
            sb._client.table("valuations")
            .select("property_id")
            .order("created_at", desc=True)
            .limit(args.limit)
            .execute()
        )
        seen: set[str] = set()
        ids = []
        for r in resp.data or []:
            pid = r["property_id"]
            if pid not in seen:
                seen.add(pid)
                ids.append(pid)

    print(f"# Auditoria P0 — {len(ids)} propriedade(s)\n")

    total_lost = 0
    total_now = 0
    impacted_props = 0
    for pid in ids:
        result = _audit_property(sb, pid)
        if not result:
            continue
        total_now += result["n_used_now"]
        total_lost += result["n_lost_used"]
        if result["n_lost_used"] > 0:
            impacted_props += 1

        marker = "⚠ " if result["n_lost_used"] > 0 else "  "
        print(
            f"{marker}{pid[:8]}.. "
            f"[{result['property_type']:<11}/{result['effective_type']:<17}] "
            f"{result['city']}/{result['state']} | "
            f"used: {result['n_used_now']} → {result['n_used_after_filters']} "
            f"(self={result['n_self_rejected']}, "
            f"area={result['n_area_rejected']}, "
            f"area_field={result['area_field']})"
        )
        for ex in result["self_rejected_examples"]:
            if ex["currently_used"]:
                print(f"      AUTO-SELF: {ex['url']} (R$ {ex['price']:,.2f})")
        for ex in result["area_rejected_examples"]:
            if ex["currently_used"]:
                print(f"      AREA-OOB:  {ex['url']} ({ex['reason']})")

    print("\n# Resumo")
    print(f"  Properties impactadas: {impacted_props}/{len(ids)}")
    print(f"  Comparables 'used' antes: {total_now}")
    print(f"  Comparables 'used' depois: {total_now - total_lost}")
    pct = (100.0 * total_lost / total_now) if total_now else 0.0
    print(f"  Comparables que sairiam: {total_lost} ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
