"""Sanity check da CMA contra fontes externas (FipeZAP).

Função pura sem I/O — o caller (``node_estimate_price``) busca a leitura
FipeZAP via Supabase e passa pra cá. Mantemos a lógica isolada para que
seja testável em unidade e auditável (skill "CMA sagrada — pode endurecer,
não relaxar").

Regra atual (simples, ajustável quando tivermos dados em produção):
  * Distoa  > 30% → endurece confidence em 1 nível e gera warning.
  * Distoa <=30% → comportamento inalterado (sinal de coerência, sem alarme).

NÃO promovemos confidence se a CMA bate com o FipeZAP — isso quebraria a
invariante "FipeZAP pode endurecer, não relaxar".
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.agents.comparables.pricing import Valuation

# Tolerância máxima antes de rebaixar — 30% é generoso (mercado bimodal em
# capitais regularmente bate isso entre bairros distintos), mas alvo da CMA
# fora dessa faixa em relação à mediana da cidade é sinal de viés.
DIVERGENCE_THRESHOLD: float = 0.30

# Ordem da confidence — usada para o downgrade.
_CHAIN = ("INSUFFICIENT", "LOW", "MEDIUM", "HIGH")


@dataclass(frozen=True, slots=True)
class SanityCheckResult:
    """Resultado da comparação CMA × FipeZAP."""

    valuation: Valuation
    warning: str | None
    fipezap_ppm2: float | None
    divergence_pct: float | None


def _downgrade(c: str) -> str:
    if c not in _CHAIN:
        return c
    idx = _CHAIN.index(c)
    return _CHAIN[max(idx - 1, 0)]


def compare_with_fipezap(
    valuation: Valuation,
    city_ppm2_row: dict | None,
    *,
    threshold: float = DIVERGENCE_THRESHOLD,
) -> SanityCheckResult:
    """Compara ``valuation.ppm2_estimated`` com o R$/m² médio do FipeZAP.

    ``city_ppm2_row`` é o dict retornado por
    :py:meth:`SupabaseService.get_latest_city_ppm2`. Quando ``None`` (sem
    leitura para a cidade), devolve o ``valuation`` original sem warning —
    sinal de que o sanity check está indisponível.

    A confidence só é rebaixada quando AMBOS estão presentes E a divergência
    excede ``threshold``. Nunca eleva confidence — coerência com FipeZAP é
    "ok como estava", não "melhor que estava".
    """
    if city_ppm2_row is None:
        return SanityCheckResult(
            valuation=valuation,
            warning=None,
            fipezap_ppm2=None,
            divergence_pct=None,
        )

    fipezap_ppm2 = city_ppm2_row.get("mean_ppm2_brl")
    if fipezap_ppm2 is None or fipezap_ppm2 <= 0:
        return SanityCheckResult(
            valuation=valuation,
            warning=None,
            fipezap_ppm2=None,
            divergence_pct=None,
        )

    cma_ppm2 = valuation.ppm2_estimated
    if cma_ppm2 is None or cma_ppm2 <= 0:
        # Valuation já é INSUFFICIENT (sem ppm2) — nada a comparar.
        return SanityCheckResult(
            valuation=valuation,
            warning=None,
            fipezap_ppm2=float(fipezap_ppm2),
            divergence_pct=None,
        )

    divergence = abs(cma_ppm2 - fipezap_ppm2) / fipezap_ppm2

    if divergence <= threshold:
        return SanityCheckResult(
            valuation=valuation,
            warning=None,
            fipezap_ppm2=float(fipezap_ppm2),
            divergence_pct=divergence,
        )

    # Divergência ALTA — rebaixa e avisa.
    asof = ""
    y = city_ppm2_row.get("asof_year")
    m = city_ppm2_row.get("asof_month")
    if y and m:
        asof = f" ({int(y):04d}-{int(m):02d})"

    direction = "acima" if cma_ppm2 > fipezap_ppm2 else "abaixo"
    warning = (
        f"R$/m² estimado (R$ {cma_ppm2:,.0f}) está {divergence * 100:.0f}% "
        f"{direction} da média FipeZAP da cidade (R$ {fipezap_ppm2:,.0f}{asof}). "
        "Pode indicar mistura com bairros distintos do alvo — refine condo/rua."
    )

    new_confidence = _downgrade(valuation.confidence)
    new_val = (
        valuation
        if new_confidence == valuation.confidence
        else replace(valuation, confidence=new_confidence)  # type: ignore[arg-type]
    )
    return SanityCheckResult(
        valuation=new_val,
        warning=warning,
        fipezap_ppm2=float(fipezap_ppm2),
        divergence_pct=divergence,
    )


__all__ = ["SanityCheckResult", "compare_with_fipezap", "DIVERGENCE_THRESHOLD"]
