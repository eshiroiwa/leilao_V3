"""Heurística de classificação do parecer e geração de warnings.

Mantemos as regras AQUI (e não no service) para que sejam fáceis de
entender e ajustar. Tudo é configurável via constantes no topo.

Fluxo:
    1. ROI realista (ANUALIZADO) define um *base verdict*.
    2. Cada fator de risco aplica um *downgrade* (1 nível abaixo).
    3. PISO: o mesmo ROI também limita o quão baixo o verdict pode cair —
       um imóvel com ROI anualizado 50% nunca vira "INVIAVEL" só por warnings.

Por que o ROI **anualizado**: um "50% bruto" em 6 meses (≈ 125% a.a.) é
incomparável com "50% bruto" em 60 meses (≈ 8,4% a.a.). O verdict precisa
operar numa base comparável; CDI/Selic só fazem sentido na base anual.
Quando ``holding_months = 12`` (default), o annualized = bruto, então o
comportamento histórico é preservado para a UX padrão.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.agents.opportunity.assumptions import VerdictType


# =============================================================================
# Faixas de ROI líquido (cenário REALISTA) que classificam a oportunidade
# =============================================================================
# `EXCELLENT` é um threshold "intocável": acima dele NENHUM warning rebaixa o
# verdict. A ideia é que retorno líquido tão alto compensa qualquer fricção
# operacional razoável que o imóvel possa ter (ocupação, reforma extensa, etc.).
ROI_EXCELLENT_THRESHOLD = 0.50  # ≥ 50% líquido sobre capital — excelente, intocável
ROI_GREAT_THRESHOLD = 0.40       # ≥ 40% líquido sobre capital — boa oportunidade base
ROI_OK_THRESHOLD = 0.20          # entre 20% e 40% — boa com ressalvas base
ROI_NEUTRAL_THRESHOLD = 0.05     # entre 5% e 20% — neutro
                                 # < 5% = inviável


# =============================================================================
# Helpers
# =============================================================================
_VERDICT_CHAIN: list[VerdictType] = [
    "BOA_OPORTUNIDADE",
    "BOA_COM_RESSALVAS",
    "NEUTRO",
    "INVIAVEL",
]


def _classify_by_roi(net_roi_pct: float) -> VerdictType:
    if net_roi_pct >= ROI_GREAT_THRESHOLD:
        return "BOA_OPORTUNIDADE"
    if net_roi_pct >= ROI_OK_THRESHOLD:
        return "BOA_COM_RESSALVAS"
    if net_roi_pct >= ROI_NEUTRAL_THRESHOLD:
        return "NEUTRO"
    return "INVIAVEL"


def _downgrade(v: VerdictType) -> VerdictType:
    """Empurra o parecer um nível para baixo (penalidade por warnings graves)."""
    if v not in _VERDICT_CHAIN:
        return v
    idx = _VERDICT_CHAIN.index(v)
    return _VERDICT_CHAIN[min(idx + 1, len(_VERDICT_CHAIN) - 1)]


def _floor_for_roi(roi_for_verdict_pct: float) -> VerdictType:
    """Verdict mínimo permitido dado o ROI usado na classificação — o "piso".

    A regra é "ROI alto é difícil de invalidar":

      * ≥ 50% → piso = BOA_OPORTUNIDADE (excelente, intocável).
      * ≥ 40% → piso = BOA_COM_RESSALVAS (cai 1 nível no máximo).
      * ≥ 20% → piso = NEUTRO.
      * < 20% → sem piso (pode chegar a INVIAVEL).
    """
    if roi_for_verdict_pct >= ROI_EXCELLENT_THRESHOLD:
        return "BOA_OPORTUNIDADE"
    if roi_for_verdict_pct >= ROI_GREAT_THRESHOLD:
        return "BOA_COM_RESSALVAS"
    if roi_for_verdict_pct >= ROI_OK_THRESHOLD:
        return "NEUTRO"
    return "INVIAVEL"


def _better_of(a: VerdictType, b: VerdictType) -> VerdictType:
    """Retorna o verdict "melhor" (mais à esquerda na chain)."""
    if a not in _VERDICT_CHAIN:
        return b
    if b not in _VERDICT_CHAIN:
        return a
    return _VERDICT_CHAIN[min(_VERDICT_CHAIN.index(a), _VERDICT_CHAIN.index(b))]


# =============================================================================
# Geração de warnings
# =============================================================================
def build_warnings(
    *,
    occupancy_status: str | None,
    has_liens_or_debts: bool,
    valuation_confidence: str | None,
    n_comparables: int | None,
    buyer_type: str,
    pessimista_net_profit: float,
    auctioneer_fee_source: str,
    itbi_source: str,
    renovation_level: str | None = None,
    renovation_cost: float | None = None,
    renovation_area_source: str | None = None,
    pj_regime: str = "presumido",
    realista_annualized_roi: float | None = None,
    cdi_annual: float | None = None,
) -> list[str]:
    """Lista heurística de avisos a serem mostrados no UI.

    Cada string é uma frase curta e acionável em PT-BR.
    """
    warnings: list[str] = []

    # Ocupação — informativo, não crítico (comum em leilões).
    occ = (occupancy_status or "").strip().lower()
    if occ == "ocupado":
        warnings.append(
            "Imóvel ocupado (comum em leilões). O default de 'outros custos' "
            "já inclui desocupação; ajuste se for necessário ação judicial."
        )
    elif occ in {"", "unknown", "desconhecido"}:
        warnings.append(
            "Status de ocupação não confirmado — verificar antes de dar o lance."
        )

    # Ônus / dívidas
    if has_liens_or_debts:
        warnings.append(
            "Edital indica ônus/dívidas: confirme se serão sub-rogados no preço (Lei 14.711/2023)."
        )

    # Confiabilidade da valuation
    if valuation_confidence in {"LOW", "INSUFFICIENT"}:
        warnings.append(
            "Avaliação de mercado com confiança baixa — refazer CMA antes de decidir."
        )
    if n_comparables is not None and n_comparables < 5:
        warnings.append(
            f"Apenas {n_comparables} comparáveis encontrados — ampliar busca para reduzir incerteza."
        )

    # Cenário pessimista no vermelho
    if pessimista_net_profit < 0:
        warnings.append(
            "Cenário pessimista é deficitário — só prossiga se aceitar essa cauda de risco."
        )

    # Custo de oportunidade — ROI anualizado realista vs CDI atual.
    # Só geramos warning se tivermos AMBOS os valores (CDI pode falhar).
    if (
        cdi_annual is not None
        and realista_annualized_roi is not None
        and realista_annualized_roi < cdi_annual
    ):
        warnings.append(
            f"ROI anualizado realista ({realista_annualized_roi * 100:.1f}% a.a.) "
            f"abaixo do CDI atual (~{cdi_annual * 100:.1f}% a.a.) — renda fixa "
            f"rende mais sem o trabalho de leilão+reforma+revenda."
        )

    # PJ — destaque que é estimativa (mensagem específica por regime)
    if buyer_type == "PJ":
        if pj_regime == "real":
            warnings.append(
                "Imposto PJ Lucro Real é uma ESTIMATIVA simplificada "
                "(IRPJ+CSLL ~24% sobre lucro + PIS/COFINS ~9,25% sobre venda, "
                "SEM créditos de PIS/COFINS). Em deals isolados o regime "
                "Presumido costuma ser mais vantajoso. Consulte seu contador."
            )
        else:
            warnings.append(
                "Imposto PJ é uma ESTIMATIVA simplificada (Lucro Presumido ≈ 6,5% sobre venda). "
                "Consulte seu contador para o cálculo exato do seu regime."
            )

    # Premissas usadas (transparência)
    if auctioneer_fee_source == "default":
        warnings.append(
            "Comissão do leiloeiro (5%) é o default — confira no edital se é menor."
        )
    elif auctioneer_fee_source == "no_auctioneer":
        warnings.append(
            "Imóvel sem leiloeiro designado — assumimos 0% de comissão. "
            "Se o edital indicar um leiloeiro, ajuste manualmente."
        )
    if itbi_source == "default":
        warnings.append(
            "Alíquota de ITBI é estimada (3%) — confira a tabela do município."
        )

    # Reforma sem área construída disponível: custo saiu 0 mesmo com
    # nível selecionado. Pode ser intencional (terreno) ou bug de cadastro
    # (apartamento sem ``area_built_m2``). Sinaliza pro usuário.
    if (
        renovation_level not in (None, "none")
        and (renovation_cost is None or renovation_cost <= 0)
        and renovation_area_source != "no_construction"
    ):
        warnings.append(
            "Nível de reforma selecionado, mas o imóvel não tem área "
            "construída cadastrada — custo de reforma considerado 0. "
            "Confirme a área construída no edital antes de decidir."
        )

    return warnings


# =============================================================================
# Verdict final
# =============================================================================
@dataclass(frozen=True, slots=True)
class VerdictDecision:
    """Saída do classificador — verdict + transparência sobre como chegou lá."""

    verdict: VerdictType
    base_verdict: VerdictType   # antes dos downgrades
    factors: list[str]          # frases curtas que reduziram o verdict
    floor: VerdictType          # piso aplicado (informativo)


def classify_verdict(
    *,
    roi_for_verdict_pct: float,
    pessimista_net_profit: float,
    has_critical_warnings: bool,
) -> VerdictDecision:
    """Combina ROI (anualizado, do cenário realista) + alertas em um parecer.

    Estratégia (mais permissiva que a anterior):
      1. ROI define o ``base_verdict`` E um piso.
      2. Para cada fator de risco aplicamos um downgrade (1 nível).
      3. O resultado nunca cai abaixo do piso permitido pelo ROI:
         um imóvel com ROI anualizado de 50% NUNCA vira INVIAVEL só porque
         há um warning crítico — ele permanece "BOA_COM_RESSALVAS" no pior
         caso.

    ``roi_for_verdict_pct`` deve ser o ROI **anualizado** do cenário
    realista — é a métrica comparável entre holdings curtos e longos.
    Para holding=12 meses (default da UI) coincide com o ROI bruto, então
    o comportamento prévio é preservado nesse caso.

    Os fatores são retornados explicitamente para que o UI possa explicar
    "por que este parecer", e não só mostrar a label final.
    """
    base = _classify_by_roi(roi_for_verdict_pct)
    floor = _floor_for_roi(roi_for_verdict_pct)

    factors: list[str] = []
    if pessimista_net_profit < 0:
        factors.append("Cenário pessimista é deficitário")
    if has_critical_warnings:
        factors.append("Riscos financeiros relevantes (ônus declarados ou CMA fraca)")

    final = base
    for _ in factors:
        final = _downgrade(final)
    # Aplica o piso baseado no ROI: o resultado nunca cai abaixo dele.
    final = _better_of(final, floor)

    return VerdictDecision(
        verdict=final,
        base_verdict=base,
        factors=factors,
        floor=floor,
    )


def has_critical_warnings(warnings: Sequence[str]) -> bool:
    """Detecta warnings que devem causar downgrade automático do parecer.

    SOMENTE riscos FINANCEIROS são considerados críticos — ou seja, coisas
    que podem fazer o investidor perder dinheiro fora do que já foi
    contabilizado nos custos:

      * ``confiança baixa``  — CMA fraca: o "preço de venda" é incerto.
      * ``ônus/dívidas``     — dívidas não declaradas/não sub-rogadas.

    Imóvel OCUPADO **não** é crítico: é o cenário comum em leilões e os
    custos de desocupação já entram no campo "outros custos" (default
    elevado quando a property está marcada como ocupada). Aparece na lista
    de warnings só como informação operacional.
    """
    keywords = (
        "confiança baixa",
        "ônus/dívidas",
    )
    return any(any(k in w for k in keywords) for w in warnings)
