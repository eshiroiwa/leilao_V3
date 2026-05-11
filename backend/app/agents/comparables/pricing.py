"""Estimação de preço a partir de comparáveis.

Princípio: usar **R$/m² ponderado pela similaridade**, com mediana (robusta
a outliers) e intervalo P10–P90 ponderado. Múltiplos métodos podiam ser
implementados (média geométrica, regressão), mas para amostras pequenas
(5–15 comparáveis) a mediana ponderada é a opção mais defensável.

Funções puras, sem I/O.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Literal

Confidence = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]


@dataclass(frozen=True)
class Comparable:
    """Item já filtrado e pronto para entrar no cálculo.

    ``ppm2`` = preço por m² do anúncio. Calcular ANTES de chamar pricing
    (caller é responsável por descartar comparáveis sem ``listed_price``
    ou ``area_total_m2``).

    ``same_building`` indica que este comparável é do MESMO prédio do
    imóvel-alvo (matching por ``condo_name`` normalizado). Quando há
    pelo menos 3 desses, ``estimate_price`` automaticamente usa SÓ
    eles e cravece a confidence (mesmo prédio é o melhor sinal possível).

    ``area_m2`` é a área usada como denominador do ppm2 (mesma escala do
    target). Opcional — quando preenchido, viabiliza a segmentação por
    cluster bimodal escolhendo o cluster cuja área média é mais próxima
    da área-alvo (heurística para discriminar premium vs popular).
    """

    listing_id: str
    ppm2: float
    weight: float  # tipicamente similarity × reliability
    same_building: bool = False
    area_m2: float | None = None


@dataclass(frozen=True)
class Valuation:
    """Resultado de uma estimação."""

    estimated_price: float | None
    price_lower_bound: float | None
    price_upper_bound: float | None
    ppm2_estimated: float | None
    confidence: Confidence
    method: str
    comparables_used: int


# ---------------------------------------------------------------------------
# Quantis ponderados (sem numpy/scipy — mantemos a stack leve).
# ---------------------------------------------------------------------------
def weighted_quantile(
    values: Iterable[float],
    weights: Iterable[float],
    q: float,
) -> float:
    """Quantil ponderado com convenção "centro do peso".

    Cada amostra ``(v_i, w_i)`` ocupa um intervalo de comprimento ``w_i`` na
    CDF cumulativa, e seu valor é representativo no CENTRO desse intervalo.
    Interpolamos linearmente entre centros consecutivos.

    Essa convenção tem duas propriedades importantes para nós:
      * para pesos uniformes, recupera EXATAMENTE a mediana clássica
        (median([1,2,3,4,5]) = 3.0);
      * pesos zero/negativos são silenciosamente ignorados.

    ``q`` ∈ [0, 1]. Lista vazia levanta ``ValueError``.
    """
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q deve estar em [0,1], recebido {q}")

    pairs = sorted(
        ((float(v), float(w)) for v, w in zip(values, weights) if w and w > 0),
        key=lambda x: x[0],
    )
    if not pairs:
        raise ValueError("Sem valores com peso positivo para calcular quantil.")

    total_w = sum(w for _, w in pairs)
    target = q * total_w

    # Posição "central" de cada amostra na CDF acumulada.
    centers: list[tuple[float, float]] = []
    running = 0.0
    for v, w in pairs:
        centers.append((running + w / 2.0, v))
        running += w

    # Antes do primeiro centro: devolve o primeiro valor.
    if target <= centers[0][0]:
        return centers[0][1]
    # Depois do último centro: devolve o último valor.
    if target >= centers[-1][0]:
        return centers[-1][1]
    # Interpolação linear entre centros consecutivos.
    for i in range(1, len(centers)):
        pos, val = centers[i]
        if pos >= target:
            prev_pos, prev_val = centers[i - 1]
            frac = (target - prev_pos) / (pos - prev_pos)
            return prev_val + frac * (val - prev_val)
    return centers[-1][1]  # unreachable, mas mypy gosta


def weighted_median(values: Iterable[float], weights: Iterable[float]) -> float:
    return weighted_quantile(values, weights, 0.5)


# ---------------------------------------------------------------------------
# Trim de outliers por IQR ponderado.
# ---------------------------------------------------------------------------
def trim_outliers(comps: list[Comparable], k: float = 1.5) -> list[Comparable]:
    """Remove comparáveis fora de [Q1 − k·IQR, Q3 + k·IQR] (Tukey).

    Robusto a amostras pequenas: se < 4 itens, devolve a lista original.

    Para apartamentos, o caller passa ``k=1.0`` (apartamentos de prédios
    distintos têm R$/m² descontínuo; o IQR padrão deixa premium passar).
    """
    if len(comps) < 4:
        return comps
    ppm2 = [c.ppm2 for c in comps]
    weights = [c.weight for c in comps]
    q1 = weighted_quantile(ppm2, weights, 0.25)
    q3 = weighted_quantile(ppm2, weights, 0.75)
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    kept = [c for c in comps if lo <= c.ppm2 <= hi]
    # Garante mínimo: se tivesse 4 e cortou demais, devolve original.
    return kept if len(kept) >= 3 else comps


# ---------------------------------------------------------------------------
# Detecção de bimodalidade no R$/m².
# Útil para alertar o usuário quando os comparáveis vêm de prédios com
# perfis de preço muito distintos — sinal de que ele deveria informar
# o ``condo_name`` do alvo para refinar a busca.
# ---------------------------------------------------------------------------
def detect_bimodal_ppm2(
    comps: list[Comparable], *, gap_pct: float = 0.30, min_each_side: int = 2
) -> bool:
    """True se houver um "gap" >= ``gap_pct`` entre clusters consecutivos
    de R$/m², com pelo menos ``min_each_side`` comparáveis em cada lado.

    Implementação simples: ordena por ppm2, procura o maior gap relativo
    entre vizinhos. Se o gap >= ``gap_pct`` e separa a amostra em duas
    metades de tamanho >= ``min_each_side``, é bimodal.

    Para amostras < 2 * ``min_each_side`` retorna False (sem evidência).
    """
    n = len(comps)
    if n < 2 * min_each_side:
        return False
    sorted_ppm2 = sorted(c.ppm2 for c in comps if c.ppm2 > 0)
    if len(sorted_ppm2) < 2 * min_each_side:
        return False

    # Acha o maior gap relativo entre vizinhos consecutivos.
    best_gap = 0.0
    best_idx = -1
    for i in range(1, len(sorted_ppm2)):
        prev_v = sorted_ppm2[i - 1]
        curr_v = sorted_ppm2[i]
        if prev_v <= 0:
            continue
        rel = (curr_v - prev_v) / prev_v
        if rel > best_gap:
            best_gap = rel
            best_idx = i

    if best_idx == -1 or best_gap < gap_pct:
        return False

    left = best_idx
    right = len(sorted_ppm2) - best_idx
    return left >= min_each_side and right >= min_each_side


# ---------------------------------------------------------------------------
# Segmentação por bimodalidade: separa a amostra no maior gap entre vizinhos
# consecutivos de ppm2. Útil quando a CMA mistura prédios premium e popular
# no mesmo bairro — a mediana global cai entre os clusters e não representa
# nenhum deles.
# ---------------------------------------------------------------------------
def split_bimodal_clusters(
    comps: list[Comparable],
    *,
    gap_pct: float = 0.30,
    min_each_side: int = 2,
) -> tuple[list[Comparable], list[Comparable]] | None:
    """Quando :func:`detect_bimodal_ppm2` retorna True, devolve ``(low, high)``
    — comparáveis ordenados em dois clusters separados pelo maior gap. Retorna
    ``None`` quando não há bimodalidade clara (mesmos critérios da detecção).

    Não filtra outliers — o caller pode aplicar :func:`trim_outliers` em cada
    cluster separadamente se quiser. Pesos são preservados.
    """
    if not detect_bimodal_ppm2(comps, gap_pct=gap_pct, min_each_side=min_each_side):
        return None
    sorted_comps = sorted(comps, key=lambda c: c.ppm2)
    # Acha o maior gap relativo entre vizinhos.
    best_gap = 0.0
    best_idx = -1
    for i in range(1, len(sorted_comps)):
        prev = sorted_comps[i - 1].ppm2
        curr = sorted_comps[i].ppm2
        if prev <= 0:
            continue
        rel = (curr - prev) / prev
        if rel > best_gap:
            best_gap = rel
            best_idx = i
    if best_idx == -1:
        return None
    return sorted_comps[:best_idx], sorted_comps[best_idx:]


def pick_cluster_by_area_proximity(
    cluster_low: list[Comparable],
    cluster_high: list[Comparable],
    target_area_m2: float,
) -> tuple[list[Comparable], str] | None:
    """Escolhe o cluster cuja área média (ponderada por peso) está mais
    próxima de ``target_area_m2``. Devolve ``(cluster, "low"|"high")``.

    Quando nenhum cluster tem área preenchida em quantidade suficiente
    (≥ ``min_each_side`` itens), devolve ``None`` — sinal para o caller
    cair de volta na mediana global com warning.

    Heurística: em mercados bimodais, área costuma correlacionar com
    padrão construtivo (premium tende a ter área maior). Não é garantia,
    mas é o melhor sinal disponível sem informação extra de condomínio.
    """
    def _weighted_avg_area(cluster: list[Comparable]) -> float | None:
        items = [(c.area_m2, c.weight) for c in cluster if c.area_m2 and c.weight > 0]
        if len(items) < 2:
            return None
        total_w = sum(w for _, w in items)
        if total_w <= 0:
            return None
        return sum(float(a) * w for a, w in items) / total_w  # type: ignore[arg-type]

    avg_low = _weighted_avg_area(cluster_low)
    avg_high = _weighted_avg_area(cluster_high)
    if avg_low is None or avg_high is None or target_area_m2 <= 0:
        return None
    dist_low = abs(avg_low - target_area_m2)
    dist_high = abs(avg_high - target_area_m2)
    if dist_low <= dist_high:
        return cluster_low, "low"
    return cluster_high, "high"


# ---------------------------------------------------------------------------
# Coeficiente de variação (CV) — usado para classificar confidence.
# ---------------------------------------------------------------------------
def coefficient_of_variation(values: Iterable[float]) -> float:
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return 0.0
    mean = statistics.fmean(vals)
    if mean <= 0:
        return float("inf")
    sd = statistics.pstdev(vals)
    return sd / mean


# ---------------------------------------------------------------------------
# Mapeamento confidence (acompanha cma_min_comparables_*).
# ---------------------------------------------------------------------------
def classify_confidence(
    n_comparables: int,
    cv: float,
    *,
    min_acceptable: int = 3,
    min_confident: int = 5,
) -> Confidence:
    """Classifica em HIGH / MEDIUM / LOW / INSUFFICIENT.

    Regras (sintonizáveis):
      ≥ 8 comparáveis e CV < 0.20  → HIGH
      ≥ min_confident e CV < 0.30  → MEDIUM
      ≥ min_acceptable             → LOW
      caso contrário               → INSUFFICIENT
    """
    if n_comparables < min_acceptable:
        return "INSUFFICIENT"
    if n_comparables >= 8 and cv < 0.20:
        return "HIGH"
    if n_comparables >= min_confident and cv < 0.30:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Função principal: estima o preço a partir de comparáveis e área-alvo.
# ---------------------------------------------------------------------------
_SAME_BUILDING_MIN = 3
"""Mínimo de comparáveis do MESMO prédio para acionar o modo dedicado."""


def estimate_price(
    target_area_m2: float | None,
    comparables: list[Comparable],
    *,
    min_acceptable: int = 3,
    min_confident: int = 5,
    trim: bool = True,
    trim_k: float = 1.5,
    property_type: str | None = None,
) -> Valuation:
    """Devolve uma ``Valuation`` (preço central + intervalo + confidence).

    Se houver < ``min_acceptable`` comparáveis ou área-alvo inválida,
    devolve ``confidence=INSUFFICIENT`` com preços ``None``.

    **Modo "same building"**: quando há pelo menos ``_SAME_BUILDING_MIN``
    comparáveis com ``same_building=True``, usamos APENAS esses (mediana
    simples, sem ponderação) e cravece a ``confidence`` em ``HIGH``
    (>=5 listings) ou ``MEDIUM`` (3–4). É o caminho mais defensável
    quando temos várias unidades do mesmo prédio à venda.

    **Trim adaptativo**: ``trim_k`` controla a agressividade do filtro
    de outliers. Para apartamentos, o caller costuma passar ``trim_k=1.0``
    (em vez do 1.5 padrão), porque prédios distintos têm R$/m²
    descontínuo e o IQR padrão deixa premium passar.
    """
    n0 = len(comparables)

    if not target_area_m2 or target_area_m2 <= 0:
        return Valuation(
            estimated_price=None,
            price_lower_bound=None,
            price_upper_bound=None,
            ppm2_estimated=None,
            confidence="INSUFFICIENT",
            method="weighted_median_ppm2",
            comparables_used=n0,
        )

    if n0 < min_acceptable:
        return Valuation(
            estimated_price=None,
            price_lower_bound=None,
            price_upper_bound=None,
            ppm2_estimated=None,
            confidence="INSUFFICIENT",
            method="weighted_median_ppm2",
            comparables_used=n0,
        )

    # ----------------------------------------------------------------- #
    # Caminho 1: temos vários listings do MESMO prédio.
    # ----------------------------------------------------------------- #
    same_building = [c for c in comparables if c.same_building]
    if len(same_building) >= _SAME_BUILDING_MIN:
        ppm2_values = [c.ppm2 for c in same_building]
        # Pesos uniformes: para o MESMO prédio, similaridade extra (área,
        # quartos) só atrapalha — todas as unidades já são intrinsecamente
        # ótimos comparables. Usar todos com peso igual evita viés.
        weights = [1.0] * len(same_building)
        ppm2_est = weighted_median(ppm2_values, weights)
        p10 = weighted_quantile(ppm2_values, weights, 0.10)
        p90 = weighted_quantile(ppm2_values, weights, 0.90)

        n = len(same_building)
        cv = coefficient_of_variation(ppm2_values)
        # Confidence cravada com piso pelo nº de unidades do mesmo prédio.
        if n >= 5 and cv < 0.20:
            confidence: Confidence = "HIGH"
        elif n >= 3:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return Valuation(
            estimated_price=round(ppm2_est * target_area_m2, 2),
            price_lower_bound=round(p10 * target_area_m2, 2),
            price_upper_bound=round(p90 * target_area_m2, 2),
            ppm2_estimated=round(ppm2_est, 2),
            confidence=confidence,
            method="same_building_median_ppm2",
            comparables_used=n,
        )

    # ----------------------------------------------------------------- #
    # Caminho 2: pricing tradicional (mediana ponderada com trim).
    # ----------------------------------------------------------------- #
    # Trim mais agressivo para apartamentos (prédios diferentes geram
    # R$/m² descontínuo).
    effective_k = trim_k
    if property_type and property_type.strip().lower() == "apartamento":
        effective_k = min(trim_k, 1.0)

    comps = trim_outliers(comparables, k=effective_k) if trim else list(comparables)

    # ----------------------------------------------------------------- #
    # Caminho 2a: bimodalidade segmentada.
    # Quando a amostra é claramente bimodal e temos área dos comparáveis,
    # escolhemos o cluster cuja área média é mais próxima da do target
    # (heurística — premium correlaciona com área maior). Só ativa se o
    # cluster escolhido tiver ``n >= min_acceptable``; senão volta ao
    # caminho global com confidence rebaixada. NUNCA relaxa confidence —
    # se o cluster produzir HIGH, ok; se INSUFFICIENT, voltamos pro global.
    # ----------------------------------------------------------------- #
    method_label = "weighted_median_ppm2"
    split = split_bimodal_clusters(comps, gap_pct=0.30, min_each_side=2)
    if split is not None:
        chosen = pick_cluster_by_area_proximity(split[0], split[1], target_area_m2)
        if chosen is not None and len(chosen[0]) >= min_acceptable:
            cluster_comps, _side = chosen
            cluster_ppm2 = [c.ppm2 for c in cluster_comps]
            cluster_weights = [c.weight for c in cluster_comps]
            cluster_cv = coefficient_of_variation(cluster_ppm2)
            cluster_confidence = classify_confidence(
                len(cluster_comps),
                cluster_cv,
                min_acceptable=min_acceptable,
                min_confident=min_confident,
            )
            # CV global (para comparação).
            global_cv = coefficient_of_variation([c.ppm2 for c in comps])
            global_confidence = classify_confidence(
                len(comps),
                global_cv,
                min_acceptable=min_acceptable,
                min_confident=min_confident,
            )
            # Cluster só substitui o global se NÃO PIORAR confidence.
            order = {"INSUFFICIENT": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
            if order[cluster_confidence] >= order[global_confidence]:
                ppm2_est = weighted_median(cluster_ppm2, cluster_weights)
                p10 = weighted_quantile(cluster_ppm2, cluster_weights, 0.10)
                p90 = weighted_quantile(cluster_ppm2, cluster_weights, 0.90)
                return Valuation(
                    estimated_price=round(ppm2_est * target_area_m2, 2),
                    price_lower_bound=round(p10 * target_area_m2, 2),
                    price_upper_bound=round(p90 * target_area_m2, 2),
                    ppm2_estimated=round(ppm2_est, 2),
                    confidence=cluster_confidence,
                    method=f"bimodal_cluster_{_side}_median_ppm2",
                    comparables_used=len(cluster_comps),
                )

    ppm2_values = [c.ppm2 for c in comps]
    weights = [c.weight for c in comps]

    ppm2_est = weighted_median(ppm2_values, weights)
    p10 = weighted_quantile(ppm2_values, weights, 0.10)
    p90 = weighted_quantile(ppm2_values, weights, 0.90)

    cv = coefficient_of_variation(ppm2_values)
    confidence = classify_confidence(
        len(comps),
        cv,
        min_acceptable=min_acceptable,
        min_confident=min_confident,
    )

    return Valuation(
        estimated_price=round(ppm2_est * target_area_m2, 2),
        price_lower_bound=round(p10 * target_area_m2, 2),
        price_upper_bound=round(p90 * target_area_m2, 2),
        ppm2_estimated=round(ppm2_est, 2),
        confidence=confidence,
        method=method_label,
        comparables_used=len(comps),
    )


# ---------------------------------------------------------------------------
# Área efetiva do alvo: qual campo de área usar para multiplicar pelo ppm2.
# ---------------------------------------------------------------------------
# Imóveis vindos dos editais Caixa frequentemente registram TRÊS áreas:
#   * area_total_m2  → área da matrícula (privativa + comum + garagem etc.)
#   * area_built_m2  → área construída (= privativa real)
#   * area_useful_m2 → área útil (≈ privativa, quando informada)
#
# Já os portais (ZAP/VivaReal) anunciam APENAS a "área anunciada":
#   * para apartamentos isso é a área PRIVATIVA/ÚTIL;
#   * para casas é (em geral) a área CONSTRUÍDA.
#
# Como o ppm2 dos comparáveis é sempre derivado da área anunciada, multiplicar
# pelo `area_total_m2` da matrícula superdimensiona o preço quando a matrícula
# é maior que a privativa (caso típico em apartamentos: área_total = privativa
# + fração ideal da garagem/áreas comuns). Esta função escolhe o campo
# coerente com o `property_type` do alvo para que ppm2 (de mercado) × área
# (do alvo) viva no mesmo "espaço de áreas".
def effective_target_area_m2(
    target: dict | None,
) -> tuple[float | None, str | None]:
    """Devolve ``(area_m2, source_field)`` para o cálculo do preço.

    Política por ``property_type`` (case-insensitive):

    * ``apartamento``, ``comercial``, ``galpao``: prioriza
      ``area_built_m2`` → ``area_useful_m2`` → ``area_total_m2``.
    * ``casa``, ``sobrado``: prioriza ``area_built_m2`` →
      ``area_useful_m2`` → ``area_total_m2`` (em casas a "área total" também
      pode incluir o terreno, então construída é mais comparável).
    * ``terreno``, ``rural``, ``outro`` ou tipo desconhecido: usa
      ``area_total_m2`` (mantém o comportamento legado).

    Retorna ``(None, None)`` quando nenhum dos campos válidos está preenchido.
    """
    if not target:
        return (None, None)

    def _pick(*keys: str) -> tuple[float | None, str | None]:
        for k in keys:
            v = target.get(k)
            try:
                fv = float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                continue
            if fv > 0:
                return (fv, k)
        return (None, None)

    ptype = (target.get("property_type") or "").strip().lower()

    if ptype in {"apartamento", "comercial", "galpao"}:
        return _pick("area_built_m2", "area_useful_m2", "area_total_m2")
    if ptype in {"casa", "sobrado"}:
        return _pick("area_built_m2", "area_useful_m2", "area_total_m2")
    return _pick("area_total_m2", "area_useful_m2", "area_built_m2")


__all__ = [
    "Comparable",
    "Valuation",
    "weighted_quantile",
    "weighted_median",
    "trim_outliers",
    "detect_bimodal_ppm2",
    "split_bimodal_clusters",
    "pick_cluster_by_area_proximity",
    "coefficient_of_variation",
    "classify_confidence",
    "estimate_price",
    "effective_target_area_m2",
]
