"""Auditoria: estima impacto da troca de ``area_total_m2`` →
``effective_renovation_area_m2`` no custo de reforma.

Lê todos os imóveis e compara, para cada um, a área que era usada antes
(``area_total_m2`` → ``area_built_m2``) com a área que deveria ser usada
agora (decisão por ``property_type``). Reporta os casos mais distorcidos
e o total de imóveis afetados.

Uso::

    python -m scripts.audit_renovation_area
"""

from __future__ import annotations

from app.agents.opportunity import assumptions as A
from app.services.supabase_service import get_supabase_service


def _legacy_area(p: dict) -> float | None:
    """Política antiga (bug): ``area_total_m2`` → ``area_built_m2``."""
    for k in ("area_total_m2", "area_built_m2"):
        v = p.get(k)
        try:
            fv = float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            continue
        if fv > 0:
            return fv
    return None


def main() -> int:
    sb = get_supabase_service()

    rows = (
        sb._client.table("properties")
        .select(
            "id,property_type,area_built_m2,area_total_m2,city,state,title"
        )
        .execute()
        .data
        or []
    )

    print(f"Total de imóveis: {len(rows)}")
    print(f"{'─' * 80}")

    distortions: list[tuple[float, dict]] = []
    no_renovation_now: list[dict] = []
    same: int = 0

    for p in rows:
        old = _legacy_area(p)
        new, _ = A.effective_renovation_area_m2(p)

        if old is None and new is None:
            continue

        # Custo @ ``full`` (R$ 1.500/m²) para visualização.
        old_cost = (old or 0.0) * A.RENOVATION_PER_M2["full"]
        new_cost = (new or 0.0) * A.RENOVATION_PER_M2["full"]
        delta = old_cost - new_cost

        if new is None and old is not None:
            no_renovation_now.append(p)
            distortions.append((delta, p))
            continue

        if old == new:
            same += 1
            continue

        distortions.append((delta, p))

    distortions.sort(key=lambda t: t[0], reverse=True)

    print(f"Sem mudança: {same}")
    print(f"Com mudança: {len(distortions)}")
    print(
        f"  • Antes cobrava reforma e agora NÃO (terreno): {len(no_renovation_now)}"
    )
    print(f"{'─' * 80}")
    print("TOP 10 mais distorcidos (overshoot do custo no método antigo):")
    print(
        f"{'TIPO':<14} {'BUILT':>8} {'TOTAL':>8} {'OLD R$':>14} "
        f"{'NEW R$':>14} {'DELTA':>14}  CIDADE/UF"
    )
    for delta, p in distortions[:10]:
        old = _legacy_area(p) or 0.0
        new, _ = A.effective_renovation_area_m2(p)
        old_cost = old * A.RENOVATION_PER_M2["full"]
        new_cost = (new or 0.0) * A.RENOVATION_PER_M2["full"]
        ptype = (p.get("property_type") or "?")[:14]
        built = p.get("area_built_m2") or 0
        total = p.get("area_total_m2") or 0
        loc = f"{p.get('city')}/{p.get('state')}"
        print(
            f"{ptype:<14} {built:>8} {total:>8} "
            f"{old_cost:>14,.0f} {new_cost:>14,.0f} {delta:>14,.0f}  {loc}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
