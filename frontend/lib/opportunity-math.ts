/**
 * AGENTE 3 — núcleo matemático no FRONTEND.
 *
 * Espelha 1:1 a lógica de `backend/app/agents/opportunity/{pricing_math,assumptions,verdict}.py`.
 * O servidor é a FONTE DA VERDADE — esta cópia só permite preview instantâneo
 * sem latência de rede. Quando o usuário "Salvar Análise", a API recalcula
 * tudo do zero e o servidor sobreescreve.
 *
 * Mantenha as constantes em sincronia com `backend/app/agents/opportunity/assumptions.py`.
 * Qualquer divergência produz UI inconsistente e bug de "preview ≠ persistido".
 */

import type {
  BuyerType,
  OpportunityAssumptions,
  OpportunityInput,
  OpportunityResult,
  OpportunityScenario,
  Property,
  RenovationLevel,
  Valuation,
  Verdict,
} from "./api";

// =============================================================================
// 1. Tabelas de premissas (ESPELHO de assumptions.py)
// =============================================================================
const ITBI_BY_CITY: Record<string, number> = {
  "sao paulo|SP": 0.03,
  "rio de janeiro|RJ": 0.03,
  "brasilia|DF": 0.03,
  "belo horizonte|MG": 0.03,
  "salvador|BA": 0.03,
  "fortaleza|CE": 0.03,
  "curitiba|PR": 0.027,
  "porto alegre|RS": 0.03,
  "recife|PE": 0.03,
  "campinas|SP": 0.027,
  "santo andre|SP": 0.03,
  "guarulhos|SP": 0.03,
  "osasco|SP": 0.03,
  "santos|SP": 0.027,
  "sao bernardo do campo|SP": 0.03,
  "pindamonhangaba|SP": 0.02,
  "niteroi|RJ": 0.03,
  "florianopolis|SC": 0.02,
};
const ITBI_DEFAULT = 0.03;
export const REGISTRATION_PCT_DEFAULT = 0.015;
const AUCTIONEER_FEE_DEFAULT = 0.05;
const AUCTIONEER_FEE_CAIXA = 0.0;
const SLUGS_NO_AUCTIONEER_FEE = new Set(["caixa", "caixa-leiloes"]);
const REALTOR_FEE_PCT = 0.06;
const IR_PF_PCT = 0.15;
const IR_PJ_PCT = 0.065;

const RENOVATION_PER_M2: Record<RenovationLevel, number> = {
  none: 0,
  basic: 500,
  moderate: 1_000,
  full: 1_500,
  premium: 2_500,
};

const OTHER_COSTS_DEFAULT_BY_OCC: Record<string, number> = {
  vacant: 3_000,
  occupied: 15_000,
  unknown: 8_000,
};

export const ROI_EXCELLENT = 0.5;
export const ROI_GREAT = 0.4;
export const ROI_OK = 0.2;
export const ROI_NEUTRAL = 0.05;

export const DEFAULT_TARGET_NET_ROI = 0.4;

// =============================================================================
// Helpers
// =============================================================================
function normalizeCity(city: string | null | undefined): string {
  if (!city) return "";
  return city
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

export function itbiPctFor(
  city: string | null | undefined,
  state: string | null | undefined,
): { pct: number; exact: boolean } {
  if (!state) return { pct: ITBI_DEFAULT, exact: false };
  const key = `${normalizeCity(city)}|${state.trim().toUpperCase()}`;
  const v = ITBI_BY_CITY[key];
  return v != null ? { pct: v, exact: true } : { pct: ITBI_DEFAULT, exact: false };
}

export function auctioneerFeePctFor(
  declared: number | null | undefined,
  slug: string | null | undefined,
): number {
  if (declared != null && declared >= 0) return declared;
  if (slug && SLUGS_NO_AUCTIONEER_FEE.has(slug.trim().toLowerCase())) {
    return AUCTIONEER_FEE_CAIXA;
  }
  return AUCTIONEER_FEE_DEFAULT;
}

export function renovationCostFor(
  level: RenovationLevel,
  areaM2: number | null | undefined,
): number {
  if (!areaM2 || areaM2 <= 0) return 0;
  return RENOVATION_PER_M2[level] * areaM2;
}

export function otherCostsDefaultFor(occ: string | null | undefined): number {
  const s = (occ ?? "").trim().toLowerCase();
  if (s === "desocupado" || s === "vacant" || s === "livre") {
    return OTHER_COSTS_DEFAULT_BY_OCC.vacant;
  }
  if (s === "ocupado" || s === "occupied") {
    return OTHER_COSTS_DEFAULT_BY_OCC.occupied;
  }
  return OTHER_COSTS_DEFAULT_BY_OCC.unknown;
}

// =============================================================================
// Núcleo matemático (ESPELHO de pricing_math.py)
// =============================================================================
export function computeAcquisitionCosts(args: {
  bid: number;
  auctioneerFeePct: number;
  itbiPct: number;
  registrationPct: number;
  iptuArrears: number;
  condoArrears: number;
  renovationCost: number;
  otherCosts: number;
}) {
  const { bid, auctioneerFeePct, itbiPct, registrationPct } = args;
  const auctioneerFee = bid * auctioneerFeePct;
  const itbi = bid * itbiPct;
  const registration = bid * registrationPct;
  const total =
    bid +
    auctioneerFee +
    itbi +
    registration +
    args.iptuArrears +
    args.condoArrears +
    args.renovationCost +
    args.otherCosts;
  return {
    bid,
    auctioneerFee,
    itbi,
    registration,
    iptuArrears: args.iptuArrears,
    condoArrears: args.condoArrears,
    renovationCost: args.renovationCost,
    otherCosts: args.otherCosts,
    total,
  };
}

export function computeIncomeTax(
  buyerType: BuyerType,
  salePrice: number,
  grossProfit: number,
): number {
  if (buyerType === "PJ") return Math.max(0, salePrice) * IR_PJ_PCT;
  return Math.max(0, grossProfit) * IR_PF_PCT;
}

function buildScenario(
  label: OpportunityScenario["label"],
  salePrice: number,
  args: {
    bid: number;
    auctioneerFeePct: number;
    itbiPct: number;
    registrationPct: number;
    iptuArrears: number;
    condoArrears: number;
    renovationCost: number;
    otherCosts: number;
    buyerType: BuyerType;
  },
): OpportunityScenario {
  const c = computeAcquisitionCosts(args);
  const realtorFee = salePrice * REALTOR_FEE_PCT;
  const grossProfitPreTax = salePrice - c.total - realtorFee;
  const incomeTax = computeIncomeTax(args.buyerType, salePrice, grossProfitPreTax);
  const grossProfit = salePrice - c.total - realtorFee;
  const netProfit = grossProfit - incomeTax;
  const grossRoi = c.total > 0 ? grossProfit / c.total : 0;
  const netRoi = c.total > 0 ? netProfit / c.total : 0;

  return {
    label,
    sale_price: round2(salePrice),
    bid: round2(c.bid),
    auctioneer_fee: round2(c.auctioneerFee),
    itbi: round2(c.itbi),
    registration: round2(c.registration),
    iptu_arrears: round2(c.iptuArrears),
    condo_arrears: round2(c.condoArrears),
    renovation_cost: round2(c.renovationCost),
    other_costs: round2(c.otherCosts),
    total_acquisition_cost: round2(c.total),
    realtor_fee: round2(realtorFee),
    gross_profit: round2(grossProfit),
    income_tax: round2(incomeTax),
    net_profit: round2(netProfit),
    gross_roi_pct: round6(grossRoi),
    net_roi_pct: round6(netRoi),
  };
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function round6(n: number): number {
  return Math.round(n * 1_000_000) / 1_000_000;
}

// =============================================================================
// Lance máximo p/ ROI alvo (ESPELHO de solve_max_bid)
// =============================================================================
export function solveMaxBid(p: {
  salePrice: number;
  iptuArrears: number;
  condoArrears: number;
  renovationCost: number;
  otherCosts: number;
  auctioneerFeePct: number;
  itbiPct: number;
  registrationPct: number;
  realtorFeePct: number;
  buyerType: BuyerType;
  pfRate: number;
  pjRate: number;
  targetNetRoi: number;
}): number | null {
  const F = p.auctioneerFeePct + p.itbiPct + p.registrationPct;
  const K =
    p.iptuArrears + p.condoArrears + p.renovationCost + p.otherCosts;
  const R = p.salePrice * p.realtorFeePct;
  const onePlusF = 1 + F;
  if (onePlusF <= 0) return null;
  const onePlusTarget = 1 + p.targetNetRoi;

  if (p.buyerType === "PJ") {
    const T = p.salePrice * p.pjRate;
    const numer = p.salePrice - R - T - K * onePlusTarget;
    const denom = onePlusF * onePlusTarget;
    if (denom <= 0) return null;
    const b = numer / denom;
    return b > 0 ? b : null;
  }

  const pf = p.pfRate;
  const factor = (1 - pf) + p.targetNetRoi;

  // Hipótese 1: GP ≥ 0
  if (factor > 0) {
    const numer = (p.salePrice - R) * (1 - pf) - K * factor;
    const denom = onePlusF * factor;
    if (denom > 0) {
      const b = numer / denom;
      const A = b * onePlusF + K;
      const GP = p.salePrice - A - R;
      if (b > 0 && GP >= 0) return b;
    }
  }

  // Hipótese 2: GP < 0 (T = 0)
  const numer = p.salePrice - R - K * onePlusTarget;
  const denom = onePlusF * onePlusTarget;
  if (denom > 0) {
    const b = numer / denom;
    const A = b * onePlusF + K;
    const GP = p.salePrice - A - R;
    if (b > 0 && GP < 0) return b;
  }
  return null;
}

// =============================================================================
// Verdict (ESPELHO de verdict.py)
// =============================================================================
const VERDICT_CHAIN: Verdict[] = [
  "BOA_OPORTUNIDADE",
  "BOA_COM_RESSALVAS",
  "NEUTRO",
  "INVIAVEL",
];

function classifyByRoi(roi: number): Verdict {
  if (roi >= ROI_GREAT) return "BOA_OPORTUNIDADE";
  if (roi >= ROI_OK) return "BOA_COM_RESSALVAS";
  if (roi >= ROI_NEUTRAL) return "NEUTRO";
  return "INVIAVEL";
}

function downgrade(v: Verdict): Verdict {
  const idx = VERDICT_CHAIN.indexOf(v);
  if (idx === -1) return v;
  return VERDICT_CHAIN[Math.min(idx + 1, VERDICT_CHAIN.length - 1)];
}

function floorForRoi(roi: number): Verdict {
  // ROI ≥ 50% é "intocável" — nenhum warning rebaixa.
  if (roi >= ROI_EXCELLENT) return "BOA_OPORTUNIDADE";
  if (roi >= ROI_GREAT) return "BOA_COM_RESSALVAS";
  if (roi >= ROI_OK) return "NEUTRO";
  return "INVIAVEL";
}

function betterOf(a: Verdict, b: Verdict): Verdict {
  const ia = VERDICT_CHAIN.indexOf(a);
  const ib = VERDICT_CHAIN.indexOf(b);
  if (ia === -1) return b;
  if (ib === -1) return a;
  return VERDICT_CHAIN[Math.min(ia, ib)];
}

export function buildWarnings(args: {
  occupancyStatus: string | null;
  hasLiens: boolean;
  valuationConfidence: string | null;
  nComparables: number | null;
  buyerType: BuyerType;
  pessimistaNetProfit: number;
  auctioneerFeeSource: OpportunityAssumptions["auctioneer_fee_source"];
  itbiSource: OpportunityAssumptions["itbi_source"];
}): string[] {
  const out: string[] = [];
  const occ = (args.occupancyStatus ?? "").toLowerCase();
  if (occ === "ocupado") {
    out.push(
      "Imóvel ocupado (comum em leilões). O default de 'outros custos' já inclui desocupação; ajuste se for necessário ação judicial.",
    );
  } else if (!occ || occ === "unknown" || occ === "desconhecido") {
    out.push(
      "Status de ocupação não confirmado — verificar antes de dar o lance.",
    );
  }
  if (args.hasLiens) {
    out.push(
      "Edital indica ônus/dívidas: confirme se serão sub-rogados no preço (Lei 14.711/2023).",
    );
  }
  if (
    args.valuationConfidence === "LOW" ||
    args.valuationConfidence === "INSUFFICIENT"
  ) {
    out.push(
      "Avaliação de mercado com confiança baixa — refazer CMA antes de decidir.",
    );
  }
  if (args.nComparables != null && args.nComparables < 5) {
    out.push(
      `Apenas ${args.nComparables} comparáveis encontrados — ampliar busca para reduzir incerteza.`,
    );
  }
  if (args.pessimistaNetProfit < 0) {
    out.push(
      "Cenário pessimista é deficitário — só prossiga se aceitar essa cauda de risco.",
    );
  }
  if (args.buyerType === "PJ") {
    out.push(
      "Imposto PJ é uma ESTIMATIVA simplificada (Lucro Presumido ≈ 6,5% sobre venda). " +
        "Consulte seu contador para o cálculo exato do seu regime.",
    );
  }
  if (args.auctioneerFeeSource === "default") {
    out.push(
      "Comissão do leiloeiro (5%) é o default — confira no edital se é menor.",
    );
  }
  if (args.itbiSource === "default") {
    out.push("Alíquota de ITBI é estimada (3%) — confira a tabela do município.");
  }
  return out;
}

export function hasCriticalWarnings(ws: string[]): boolean {
  // SOMENTE riscos FINANCEIROS rebaixam o verdict.
  // Imóvel OCUPADO é o normal em leilões — aparece como informativo, mas
  // não é "crítico" (custos de desocupação já estão em "outros custos").
  const keys = ["confiança baixa", "ônus/dívidas"];
  return ws.some((w) => keys.some((k) => w.includes(k)));
}

export type VerdictDecision = {
  verdict: Verdict;
  base: Verdict;
  factors: string[];
};

export function classifyVerdict(args: {
  realistaNetRoi: number;
  pessimistaNetProfit: number;
  hasCritical: boolean;
}): VerdictDecision {
  const base = classifyByRoi(args.realistaNetRoi);
  const floor = floorForRoi(args.realistaNetRoi);

  const factors: string[] = [];
  if (args.pessimistaNetProfit < 0)
    factors.push("Cenário pessimista é deficitário");
  if (args.hasCritical)
    factors.push("Riscos financeiros relevantes (ônus declarados ou CMA fraca)");

  let v = base;
  for (let i = 0; i < factors.length; i++) v = downgrade(v);
  v = betterOf(v, floor);

  return { verdict: v, base, factors };
}

// =============================================================================
// Orquestrador (ESPELHO de service.run_analysis)
// =============================================================================
function safeFloat(v: unknown): number | null {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function scenarioPricesFromValuation(
  valuation: Valuation | null,
  areaM2: number | null,
): [number, number, number] | null {
  if (!valuation) return null;
  const low = safeFloat(valuation.price_lower_bound);
  const mid = safeFloat(valuation.estimated_price);
  const high = safeFloat(valuation.price_upper_bound);
  if (low != null && mid != null && high != null && low <= mid && mid <= high) {
    return [low, mid, high];
  }
  if (areaM2 && areaM2 > 0) {
    const ppm = safeFloat(valuation.ppm2_estimated);
    if (ppm) {
      const m = ppm * areaM2;
      return [m * 0.9, m, m * 1.1];
    }
  }
  if (mid) return [mid * 0.9, mid, mid * 1.1];
  return null;
}

export function runAnalysisLocal(args: {
  input: OpportunityInput;
  property: Property;
  valuation: Valuation | null;
  auctioneerSlug?: string | null;
}): OpportunityResult {
  const { input, property, valuation } = args;
  const areaM2 = property.area_total_m2 ?? property.area_built_m2 ?? null;
  const occupancy = property.occupancy_status;

  // Alíquotas
  const itbiInfo = itbiPctFor(property.city, property.state);
  let itbiPct = itbiInfo.pct;
  let itbiSource: OpportunityAssumptions["itbi_source"] = itbiInfo.exact
    ? "city_table"
    : "default";
  if (input.itbi_pct_override != null) {
    itbiPct = input.itbi_pct_override;
    itbiSource = "override";
  }

  const registrationPct =
    input.registration_pct_override ?? REGISTRATION_PCT_DEFAULT;

  let auctioneerFeePct: number;
  let auctioneerFeeSource: OpportunityAssumptions["auctioneer_fee_source"];
  if (input.auctioneer_fee_pct_override != null) {
    auctioneerFeePct = input.auctioneer_fee_pct_override;
    auctioneerFeeSource = "override";
  } else {
    auctioneerFeePct = auctioneerFeePctFor(
      property.auctioneer_fee_pct,
      args.auctioneerSlug,
    );
    if (
      property.auctioneer_fee_pct != null &&
      property.auctioneer_fee_pct >= 0
    ) {
      auctioneerFeeSource = "edital";
    } else if (auctioneerFeePct === AUCTIONEER_FEE_CAIXA) {
      auctioneerFeeSource = "caixa_zero";
    } else {
      auctioneerFeeSource = "default";
    }
  }

  const renovationCost = renovationCostFor(input.renovation_level, areaM2);

  // Custos fixos
  const iptuArrears =
    input.iptu_arrears || property.iptu_arrears || 0;
  const condoArrears =
    input.condo_arrears || property.condo_arrears || 0;
  const otherCosts = input.other_costs || otherCostsDefaultFor(occupancy);

  // Cenários — override do usuário tem prioridade sobre a CMA
  let pessP: number, realP: number, otiP: number;
  if (input.sale_price_override != null && input.sale_price_override > 0) {
    realP = input.sale_price_override;
    pessP = realP * 0.9;
    otiP = realP * 1.1;
  } else {
    const prices = scenarioPricesFromValuation(valuation, areaM2);
    if (prices) {
      [pessP, realP, otiP] = prices;
    } else {
      const proxy = Math.max((input.bid_amount || 0) * 1.2, 1);
      pessP = proxy * 0.9;
      realP = proxy;
      otiP = proxy * 1.1;
    }
  }

  const common = {
    bid: input.bid_amount,
    auctioneerFeePct,
    itbiPct,
    registrationPct,
    iptuArrears,
    condoArrears,
    renovationCost,
    otherCosts,
    buyerType: input.buyer_type,
  };

  const pessimista = buildScenario("pessimista", pessP, common);
  const realista = buildScenario("realista", realP, common);
  const otimista = buildScenario("otimista", otiP, common);

  // Lance máximo (sobre cenário REALISTA)
  const maxBidRaw = solveMaxBid({
    salePrice: realP,
    iptuArrears,
    condoArrears,
    renovationCost,
    otherCosts,
    auctioneerFeePct,
    itbiPct,
    registrationPct,
    realtorFeePct: REALTOR_FEE_PCT,
    buyerType: input.buyer_type,
    pfRate: IR_PF_PCT,
    pjRate: IR_PJ_PCT,
    targetNetRoi: input.target_net_roi_pct,
  });
  const maxBid = maxBidRaw != null ? round2(maxBidRaw) : null;

  // Warnings + verdict
  const warnings = buildWarnings({
    occupancyStatus: occupancy,
    hasLiens: false, // backend tem flag has_liens_or_debts; expor depois
    valuationConfidence: valuation?.confidence ?? null,
    nComparables: valuation?.comparables_used ?? null,
    buyerType: input.buyer_type,
    pessimistaNetProfit: pessimista.net_profit,
    auctioneerFeeSource,
    itbiSource,
  });
  const decision = classifyVerdict({
    realistaNetRoi: realista.net_roi_pct,
    pessimistaNetProfit: pessimista.net_profit,
    hasCritical: hasCriticalWarnings(warnings),
  });

  const assumptions: OpportunityAssumptions = {
    itbi_pct: itbiPct,
    itbi_source: itbiSource,
    registration_pct: registrationPct,
    auctioneer_fee_pct: auctioneerFeePct,
    auctioneer_fee_source: auctioneerFeeSource,
    realtor_fee_pct: REALTOR_FEE_PCT,
    income_tax_pct: input.buyer_type === "PJ" ? IR_PJ_PCT : IR_PF_PCT,
    income_tax_basis:
      input.buyer_type === "PJ" ? "sale_price" : "gross_profit",
    renovation_per_m2: RENOVATION_PER_M2[input.renovation_level],
  };

  return {
    input,
    pessimista,
    realista,
    otimista,
    max_bid_for_target: maxBid,
    verdict: decision.verdict,
    verdict_base: decision.base,
    verdict_factors: decision.factors,
    warnings,
    assumptions,
  };
}
