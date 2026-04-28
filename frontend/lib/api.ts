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

export type Property = {
  id: string;
  source_url: string;
  auctioneer_id: string | null;
  auctioneer_lot_id: string | null;
  title: string | null;
  description: string | null;
  property_type: string | null;
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
  status: string;
  created_at: string;
  updated_at: string;
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
};
