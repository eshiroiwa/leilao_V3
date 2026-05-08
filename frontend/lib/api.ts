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
  title: string | null;
  description: string | null;
  property_type: string | null;
  image_url: string | null;
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
  total_acquisition_cost: number;
  realtor_fee: number;
  gross_profit: number;
  income_tax: number;
  net_profit: number;
  gross_roi_pct: number;
  net_roi_pct: number;
};

export type OpportunityAssumptions = {
  itbi_pct: number;
  itbi_source: "city_table" | "default" | "override";
  registration_pct: number;
  auctioneer_fee_pct: number;
  auctioneer_fee_source:
    | "edital"
    | "caixa_zero"
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
  max_bid_for_target: number | null;
  verdict: Verdict;
  /** Verdict APENAS pelo ROI realista (antes dos downgrades). */
  verdict_base: Verdict;
  /** Frases curtas que rebaixaram o verdict do base para o final. */
  verdict_factors: string[];
  warnings: string[];
  assumptions: OpportunityAssumptions;
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
};
