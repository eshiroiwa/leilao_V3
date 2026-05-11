/**
 * Client HTTP fino para o backend FastAPI.
 *
 * Usamos `fetch` nativo (suportado em Server Components e Client Components no Next 16).
 * Em Server Components configuramos `cache: "no-store"` para sempre buscar dados frescos
 * — adeque conforme a estratégia de cache do projeto.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ScraperRunResponse = {
  run_id: string | null;
  status: "success" | "failed";
  duration_ms: number;
  property_id: string | null;
  warnings: string[];
  errors: string[];
  saved_property: Property | null;
};

export type Confidence = "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT";

export type ValuationSummary = {
  valuation_id: string | null;
  confidence: Confidence;
  estimated_price: number | null;
  price_lower_bound: number | null;
  price_upper_bound: number | null;
  ppm2_estimated: number | null;
  comparables_used: number;
  search_strategy: "condo" | "street" | "neighborhood" | "radius" | null;
  search_radius_m: number | null;
  firecrawl_calls: number;
  llm_calls: number;
  cost_estimate_brl: number;
  warnings: string[];
};

export type Valuation = {
  id: string;
  property_id: string;
  agent_run_id: string | null;
  estimated_price: number | null;
  price_lower_bound: number | null;
  price_upper_bound: number | null;
  ppm2_estimated: number | null;
  confidence: Confidence;
  method: string | null;
  comparables_used: number;
  comparables_rejected: number;
  search_radius_m: number | null;
  search_strategy: string | null;
  firecrawl_calls: number;
  llm_calls: number;
  cost_estimate_brl: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type ValuationComparable = {
  distance_m: number | null;
  similarity_score: number | null;
  weight: number | null;
  used: boolean;
  rejection_reason: string | null;
  listings: {
    id: string;
    source: string;
    source_url: string;
    title: string | null;
    property_type: string | null;
    area_total_m2: number | null;
    bedrooms: number | null;
    bathrooms: number | null;
    parking_spaces: number | null;
    neighborhood: string | null;
    city: string | null;
    state: string | null;
    latitude: number | null;
    longitude: number | null;
    listed_price: number | null;
    geocoding_confidence: string | null;
  };
};

export type ValuationDetail = Valuation & {
  comparables: ValuationComparable[];
};

export type Property = {
  id: string;
  source_url: string;
  auctioneer_id: string | null;
  auctioneer_lot_id: string | null;
  /** Nome do leiloeiro extraído do edital (texto livre). Se preenchido,
   *  o AGENTE 3 entende que existe leiloeiro e cobra comissão. */
  auctioneer_name: string | null;
  title: string | null;
  description: string | null;
  property_type: string | null;
  image_url: string | null;
  condo_name: string | null;
  address_full: string | null;
  street: string | null;
  number: string | null;
  complement: string | null;
  neighborhood: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  google_place_id: string | null;
  geocoding_confidence:
    | "HIGH"
    | "MEDIUM"
    | "LOW"
    | "POSTAL_CODE"
    | "REJECTED"
    | null;
  latitude: number | null;
  longitude: number | null;
  area_total_m2: number | null;
  area_built_m2: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  parking_spaces: number | null;
  appraisal_value: number | null;
  minimum_bid_first: number | null;
  minimum_bid_second: number | null;
  current_bid: number | null;
  first_auction_at: string | null;
  second_auction_at: string | null;
  legal_status: string | null;
  occupancy_status: string | null;
  // Custos do edital — alimentam o AGENTE 3
  iptu_arrears: number | null;
  condo_arrears: number | null;
  auctioneer_fee_pct: number | null;
  status: string;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// AGENTE 3 — Análise de Oportunidade
// =============================================================================
export type BuyerType = "PF" | "PJ";

export type RenovationLevel =
  | "none"
  | "basic"
  | "moderate"
  | "full"
  | "premium";

export type Verdict =
  | "BOA_OPORTUNIDADE"
  | "BOA_COM_RESSALVAS"
  | "NEUTRO"
  | "INVIAVEL"
  | "INDETERMINADO";

export type OpportunityInput = {
  buyer_type: BuyerType;
  target_net_roi_pct: number;
  renovation_level: RenovationLevel;
  bid_amount: number;
  other_costs: number;
  iptu_arrears: number;
  condo_arrears: number;
  /** Horizonte planejado de carregamento até a venda (meses).
   *  Default 12 — mantém comportamento histórico (annualized == bruto). */
  holding_months?: number;
  /** IPTU mensal CORRENTE (parcela/12). Junto com `monthly_condo` ×
   *  `holding_months` compõe o custo de carregamento adicional. Default 0. */
  monthly_iptu?: number;
  /** Condomínio mensal CORRENTE. Default 0. */
  monthly_condo?: number;
  itbi_pct_override?: number | null;
  registration_pct_override?: number | null;
  auctioneer_fee_pct_override?: number | null;
  sale_price_override?: number | null;
};

export type OpportunityScenario = {
  label: "pessimista" | "realista" | "otimista";
  sale_price: number;
  bid: number;
  auctioneer_fee: number;
  itbi: number;
  registration: number;
  iptu_arrears: number;
  condo_arrears: number;
  renovation_cost: number;
  other_costs: number;
  /** (monthly_iptu + monthly_condo) × holding_months. Default 0 quando o
   *  input não preenche os campos correspondentes. */
  holding_costs?: number;
  total_acquisition_cost: number;
  realtor_fee: number;
  gross_profit: number;
  income_tax: number;
  net_profit: number;
  gross_roi_pct: number;
  net_roi_pct: number;
  /** ROI líquido anualizado: (1+net_roi)^(12/holding_months) - 1. */
  annualized_net_roi_pct: number;
};

export type OpportunityAssumptions = {
  itbi_pct: number;
  itbi_source: "city_table" | "default" | "override";
  registration_pct: number;
  auctioneer_fee_pct: number;
  auctioneer_fee_source:
    | "edital"
    | "caixa_zero"
    | "no_auctioneer"
    | "default"
    | "override";
  realtor_fee_pct: number;
  income_tax_pct: number;
  income_tax_basis: "gross_profit" | "sale_price";
  renovation_per_m2: number;
};

export type OpportunityResult = {
  input: OpportunityInput;
  pessimista: OpportunityScenario;
  realista: OpportunityScenario;
  otimista: OpportunityScenario;
  /** E[ROI net] ponderado 30/40/30 (pess/real/oti). Embrião do Monte Carlo. */
  expected_net_roi_pct?: number | null;
  /** E[ROI net anualizado] ponderado — comparável diretamente com CDI. */
  expected_annualized_net_roi_pct?: number | null;
  /** P[ROI<0] aproximada: soma das probabilidades dos cenários deficitários. */
  prob_loss?: number | null;
  max_bid_for_target: number | null;
  verdict: Verdict;
  /** Verdict APENAS pelo ROI realista (antes dos downgrades). */
  verdict_base: Verdict;
  /** Frases curtas que rebaixaram o verdict do base para o final. */
  verdict_factors: string[];
  warnings: string[];
  assumptions: OpportunityAssumptions;
};

// =============================================================================
// AGENTE 4 (Deep Analysis)
// =============================================================================
export type DeepAnalysisStatus = "pending" | "running" | "completed" | "failed";
/** Confidence específica do AGENTE 4 — só 3 níveis (sem INSUFFICIENT). */
export type DeepConfidence = "HIGH" | "MEDIUM" | "LOW";

export type UrbanRiskItem = {
  type: string;
  summary: string;
  confidence: DeepConfidence;
  source_url?: string | null;
};

export type DeepSourceDocument = {
  url: string;
  title?: string | null;
  excerpt?: string | null;
  scraped_at?: string | null;
};

export type DeepAnalysisRow = {
  id: string;
  property_id: string;
  opportunity_analysis_id?: string | null;

  status: DeepAnalysisStatus;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;

  // demografia / liquidez
  city_population?: number | null;
  city_population_year?: number | null;
  city_population_source?: string | null;
  liquidity_score?: number | null;
  liquidity_confidence?: DeepConfidence | null;
  liquidity_evidence?: Record<string, unknown> | null;

  // outlier
  is_outlier_size?: boolean | null;
  is_outlier_price?: boolean | null;
  size_zscore?: number | null;
  price_zscore?: number | null;
  outlier_evidence?: Record<string, unknown> | null;

  // flipping
  neighborhood_price_max?: number | null;
  neighborhood_price_p90?: number | null;
  neighborhood_ppm2_p90?: number | null;
  flipping_potential_score?: number | null;
  flipping_evidence?: Record<string, unknown> | null;

  // tendência
  price_trend_12m_pct?: number | null;
  price_trend_confidence?: DeepConfidence | null;
  price_trend_evidence?: Record<string, unknown> | null;

  // amenidades
  nearest_metro_m?: number | null;
  nearest_school_m?: number | null;
  nearest_hospital_m?: number | null;
  amenities_evidence?: Record<string, unknown> | null;

  // riscos urbanos
  urban_risks?: UrbanRiskItem[] | null;

  // histórico
  prior_auction_count?: number | null;
  prior_auction_evidence?: Record<string, unknown> | null;

  // síntese
  overall_score?: number | null;
  summary_text?: string | null;
  red_flags?: string[] | null;
  green_flags?: string[] | null;
  recommendations?: string[] | null;

  source_documents?: DeepSourceDocument[] | null;
  cost_estimate_usd?: number | null;
  firecrawl_calls?: number | null;
  llm_calls?: number | null;

  created_at: string;
};

export type StartDeepAnalysisResponse = {
  id: string;
  status: DeepAnalysisStatus;
  from_cache: boolean;
  row: DeepAnalysisRow | null;
};

export type OpportunityAnalysisRow = {
  id: string;
  property_id: string;
  valuation_id: string | null;
  buyer_type: BuyerType;
  target_net_roi_pct: number;
  renovation_level: RenovationLevel;
  bid_amount: number;
  other_costs: number;
  iptu_arrears: number;
  condo_arrears: number;
  scenarios: {
    pessimista: OpportunityScenario;
    realista: OpportunityScenario;
    otimista: OpportunityScenario;
  };
  max_bid_for_target: number | null;
  verdict: Verdict;
  warnings: string[];
  assumptions: OpportunityAssumptions;
  verdict_base?: Verdict;
  verdict_factors?: string[];
  /** Overrides persistidos para reproduzir a análise no formulário. */
  input_overrides?: {
    itbi_pct_override?: number | null;
    registration_pct_override?: number | null;
    auctioneer_fee_pct_override?: number | null;
    sale_price_override?: number | null;
  } | null;
  created_at: string;
};

// =============================================================================
// Dashboard (home)
// =============================================================================
export type DashboardPropertySummary = {
  property_id: string;
  title: string | null;
  image_url: string | null;
  city: string | null;
  state: string | null;
  property_type: string | null;
  minimum_bid_first: number | null;
  minimum_bid_second: number | null;
  appraisal_value: number | null;
};

export type DashboardCalendarEvent = DashboardPropertySummary & {
  /** ISO 8601 com timezone. */
  date: string;
  kind: "first" | "second";
  value: number | null;
};

export type DashboardOpportunity = DashboardPropertySummary & {
  opportunity_id: string;
  verdict: Verdict;
  net_roi_pct: number | null;
  net_profit: number | null;
  bid_amount: number | null;
  created_at: string;
};

export type DashboardTotals = {
  properties: number;
  with_geocoding: number;
  upcoming_30d: number;
  pending_valuation: number;
  pending_opportunity: number;
  good_opportunities: number;
};

export type DashboardBuckets = {
  all: DashboardPropertySummary[];
  upcoming_30d: DashboardPropertySummary[];
  pending_valuation: DashboardPropertySummary[];
  pending_opportunity: DashboardPropertySummary[];
};

export type DashboardResponse = {
  totals: DashboardTotals;
  calendar: DashboardCalendarEvent[];
  top_opportunities: DashboardOpportunity[];
  upcoming_auctions: DashboardCalendarEvent[];
  buckets: DashboardBuckets;
  generated_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let detail: string;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      detail = res.statusText;
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }

  // 204 No Content (ex.: DELETE) — não tenta fazer JSON.parse
  if (res.status === 204) return undefined as T;

  return (await res.json()) as T;
}

export const api = {
  runScraper: (url: string) =>
    request<ScraperRunResponse>("/api/v1/agents/scraper/run", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  listProperties: (params?: { limit?: number; offset?: number; status?: string }) => {
    const search = new URLSearchParams();
    if (params?.limit) search.set("limit", String(params.limit));
    if (params?.offset) search.set("offset", String(params.offset));
    if (params?.status) search.set("status", params.status);
    const qs = search.toString();
    return request<Property[]>(`/api/v1/properties${qs ? `?${qs}` : ""}`);
  },

  deleteProperty: (id: string) =>
    request<void>(`/api/v1/properties/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  /**
   * Patch parcial num imóvel. Aceita só os campos da whitelist do backend
   * (`PropertyPatch`): hoje é apenas ``condo_name``. String vazia/só-espaço
   * limpa o campo (grava ``null``).
   */
  patchProperty: (id: string, payload: { condo_name?: string | null }) =>
    request<Property>(`/api/v1/properties/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  // ===== AGENTE 2 (CMA) =====
  valuateProperty: (id: string) =>
    request<ValuationSummary>(
      `/api/v1/properties/${encodeURIComponent(id)}/valuate`,
      { method: "POST" },
    ),

  listValuations: (propertyId: string) =>
    request<Valuation[]>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/valuations`,
    ),

  getValuationDetail: (propertyId: string, valuationId: string) =>
    request<ValuationDetail>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/valuations/${encodeURIComponent(valuationId)}`,
    ),

  // ===== AGENTE 3 (Oportunidade) =====
  previewOpportunity: (propertyId: string, payload: OpportunityInput) =>
    request<OpportunityResult>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/opportunity-analyses/preview`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  saveOpportunity: (propertyId: string, payload: OpportunityInput) =>
    request<{ id: string; result: OpportunityResult }>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/opportunity-analyses`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  listOpportunities: (propertyId: string) =>
    request<OpportunityAnalysisRow[]>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/opportunity-analyses`,
    ),

  getOpportunity: (propertyId: string, analysisId: string) =>
    request<OpportunityAnalysisRow>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/opportunity-analyses/${encodeURIComponent(analysisId)}`,
    ),

  // ===== AGENTE 4 (Deep Analysis) =====
  startDeepAnalysis: (
    propertyId: string,
    payload: {
      opportunity_analysis_id?: string | null;
      force_refresh?: boolean;
    } = {},
  ) =>
    request<StartDeepAnalysisResponse>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/deep-analyses`,
      { method: "POST", body: JSON.stringify(payload) },
    ),

  listDeepAnalyses: (propertyId: string) =>
    request<DeepAnalysisRow[]>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/deep-analyses`,
    ),

  getLatestDeepAnalysis: (propertyId: string) =>
    request<DeepAnalysisRow | null>(
      `/api/v1/properties/${encodeURIComponent(propertyId)}/deep-analyses/latest`,
    ),

  getDeepAnalysis: (analysisId: string) =>
    request<DeepAnalysisRow>(
      `/api/v1/deep-analyses/${encodeURIComponent(analysisId)}`,
    ),

  // ===== Dashboard (home) =====
  getDashboard: (params?: {
    upcoming_window_days?: number;
    top_opportunities?: number;
    upcoming_limit?: number;
    calendar_window_days?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.upcoming_window_days)
      qs.set("upcoming_window_days", String(params.upcoming_window_days));
    if (params?.top_opportunities)
      qs.set("top_opportunities", String(params.top_opportunities));
    if (params?.upcoming_limit)
      qs.set("upcoming_limit", String(params.upcoming_limit));
    if (params?.calendar_window_days)
      qs.set("calendar_window_days", String(params.calendar_window_days));
    const search = qs.toString();
    return request<DashboardResponse>(
      `/api/v1/dashboard${search ? `?${search}` : ""}`,
    );
  },
};
