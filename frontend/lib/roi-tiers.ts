/**
 * Faixas de ROI anualizado líquido — alinhadas com os thresholds do
 * `classify_verdict` no backend (Agente 3). Usadas para colorir células
 * da tabela e regiões do gráfico de simulação de lances.
 *
 * Convenção: ``roi`` é uma fração decimal (0.40 = 40%).
 */

export type RoiTier =
  | "excellent" // ≥ 50%
  | "good" // 20-50%
  | "neutral" // 5-20%
  | "infeasible" // 0-5%
  | "loss"; // < 0%

export type RoiTierMeta = {
  tier: RoiTier;
  label: string;
  /** Classe Tailwind para fundo + texto em células de tabela. */
  cellClass: string;
  /** Classe Tailwind para badge (variante mais saturada). */
  badgeClass: string;
  /** Cor HEX para uso em gráfico Recharts (Recharts não aceita class names). */
  lineColor: string;
  /** Cor HEX para área de referência (mais clara). */
  fillColor: string;
};

const META: Record<RoiTier, RoiTierMeta> = {
  excellent: {
    tier: "excellent",
    label: "Excelente",
    cellClass:
      "bg-green-100 text-green-900 dark:bg-green-500/25 dark:text-green-100",
    badgeClass: "bg-green-600 text-white",
    lineColor: "#15803d",
    fillColor: "#bbf7d0",
  },
  good: {
    tier: "good",
    label: "Bom",
    cellClass:
      "bg-green-50 text-green-800 dark:bg-green-500/15 dark:text-green-200",
    badgeClass: "bg-green-500 text-white",
    lineColor: "#22c55e",
    fillColor: "#dcfce7",
  },
  neutral: {
    tier: "neutral",
    label: "Neutro",
    cellClass:
      "bg-yellow-50 text-yellow-900 dark:bg-yellow-500/20 dark:text-yellow-100",
    badgeClass: "bg-yellow-500 text-white",
    lineColor: "#ca8a04",
    fillColor: "#fef9c3",
  },
  infeasible: {
    tier: "infeasible",
    label: "Inviável",
    cellClass:
      "bg-orange-50 text-orange-900 dark:bg-orange-500/20 dark:text-orange-100",
    badgeClass: "bg-orange-500 text-white",
    lineColor: "#ea580c",
    fillColor: "#ffedd5",
  },
  loss: {
    tier: "loss",
    label: "Prejuízo",
    cellClass:
      "bg-red-100 text-red-900 dark:bg-red-500/25 dark:text-red-100",
    badgeClass: "bg-red-600 text-white",
    lineColor: "#b91c1c",
    fillColor: "#fecaca",
  },
};

/** Cortes (em fração decimal) que separam as faixas, do maior para o menor. */
export const TIER_THRESHOLDS: { tier: RoiTier; min: number }[] = [
  { tier: "excellent", min: 0.5 },
  { tier: "good", min: 0.2 },
  { tier: "neutral", min: 0.05 },
  { tier: "infeasible", min: 0 },
  { tier: "loss", min: -Infinity },
];

export function roiTier(roi: number | null | undefined): RoiTierMeta {
  if (roi == null || !Number.isFinite(roi)) return META.infeasible;
  for (const t of TIER_THRESHOLDS) {
    if (roi >= t.min) return META[t.tier];
  }
  return META.loss;
}

export function tierMeta(tier: RoiTier): RoiTierMeta {
  return META[tier];
}
