import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Combina classes Tailwind respeitando precedência. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Formata número como BRL. */
export function formatBRL(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(value);
}

/** Formata número como BRL preservando os centavos. */
export function formatBRLDecimals(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** Formata fração (0.40) como porcentagem ("40%"). */
export function formatPct(
  value: number | null | undefined,
  digits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** Formata data ISO em pt-BR (data + hora curtas). */
export function formatDateTimeBR(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(d);
}

/**
 * Determina se o leilão de um imóvel já encerrou em relação a ``nowIso``.
 *
 * Regras:
 *   • Se houver 2ª praça e ela for posterior a "agora" → ATIVO
 *     (mesmo que a 1ª praça já tenha passado).
 *   • Se houver apenas 2ª praça e ela já passou → ENCERRADO.
 *   • Se houver apenas 1ª praça e ela já passou → ENCERRADO.
 *   • Se NÃO houver datas conhecidas → assume ATIVO (não temos como
 *     afirmar o contrário; mostrar é menos pior que esconder).
 *
 * Recebe ``nowIso`` em vez de chamar ``new Date()`` para garantir
 * resultado determinístico entre SSR e cliente — passar
 * ``DashboardResponse.generated_at`` ou um ISO criado no Server
 * Component pai.
 */
export function isAuctionExpired(
  property: {
    first_auction_at: string | null;
    second_auction_at: string | null;
  },
  nowIso: string,
): boolean {
  const now = new Date(nowIso).getTime();
  const first = property.first_auction_at
    ? new Date(property.first_auction_at).getTime()
    : null;
  const second = property.second_auction_at
    ? new Date(property.second_auction_at).getTime()
    : null;

  if (second != null && !Number.isNaN(second)) {
    return second < now;
  }
  if (first != null && !Number.isNaN(first)) {
    return first < now;
  }
  return false;
}

/**
 * Normaliza string para busca case/diacritic-insensitive.
 *
 * "São Paulo, Vila Madalena" → "sao paulo, vila madalena"
 * Permite que o usuário digite "sao paulo" e encontre "São Paulo".
 */
export function normalizeText(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}
