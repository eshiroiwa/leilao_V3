"use client";

import {
  AlertTriangle,
  Building2,
  CameraOff,
  CheckCircle2,
  ExternalLink,
  GraduationCap,
  Hospital,
  Info,
  TrainFront,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  ConditionAssessment,
  DeepAnalysisRow,
  DeepConfidence,
  NeighborhoodClass,
  UrbanRiskItem,
} from "@/lib/api";
import { formatBRL, formatPct } from "@/lib/utils";

const SCORE_LABELS = ["—", "muito ruim", "ruim", "neutro", "bom", "excelente"];

function scoreVariant(
  score: number | null | undefined,
): "success" | "warning" | "danger" | "secondary" {
  if (score == null) return "secondary";
  if (score >= 4) return "success";
  if (score === 3) return "secondary";
  if (score === 2) return "warning";
  return "danger";
}

function confidenceLabel(c: DeepConfidence | null | undefined): string {
  if (!c) return "—";
  return { HIGH: "alta", MEDIUM: "média", LOW: "baixa" }[c];
}

function confidenceVariant(
  c: DeepConfidence | null | undefined,
): "success" | "warning" | "secondary" {
  if (c === "HIGH") return "success";
  if (c === "MEDIUM") return "secondary";
  return "warning";
}

function fmtMeters(m: number | null | undefined): string {
  if (m == null) return "—";
  if (m < 1_000) return `${m} m`;
  return `${(m / 1_000).toFixed(2)} km`;
}

export function DeepAnalysisCard({
  row,
  latitude,
  longitude,
}: {
  row: DeepAnalysisRow;
  latitude?: number | null;
  longitude?: number | null;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="space-y-1 pb-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-lg">Análise aprofundada</CardTitle>
            <p className="text-xs text-muted-foreground">
              {row.completed_at
                ? `Concluída em ${new Date(row.completed_at).toLocaleString("pt-BR")}`
                : "—"}
              {row.duration_ms != null && (
                <> · {Math.round(row.duration_ms / 100) / 10}s</>
              )}
            </p>
          </div>
          {row.overall_score != null && (
            <Badge variant={scoreVariant(row.overall_score)} className="text-sm">
              Score {row.overall_score}/5 · {SCORE_LABELS[row.overall_score]}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-5 text-sm">
        {/* 4 mini-cards de score por dimensão */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <ScoreTile
            label="Liquidez"
            score={row.liquidity_score}
            confidence={row.liquidity_confidence}
            sub={liquiditySub(row)}
          />
          <ScoreTile
            label="Flipping"
            score={row.flipping_potential_score}
            sub={
              row.neighborhood_price_p90 != null
                ? `p90 ${formatBRL(row.neighborhood_price_p90)}`
                : undefined
            }
          />
          <OutlierTile
            isOutlier={row.is_outlier_size || row.is_outlier_price || false}
            sizeZ={row.size_zscore}
            priceZ={row.price_zscore}
          />
          <TrendTile
            pct={row.price_trend_12m_pct}
            confidence={row.price_trend_confidence}
          />
        </div>

        {/* Classe do bairro + concorrentes */}
        {row.neighborhood_class && (
          <NeighborhoodClassBlock cls={row.neighborhood_class} />
        )}

        {/* Amenidades */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <AmenityTile
            icon={TrainFront}
            label="Metrô / estação"
            distance={row.nearest_metro_m}
          />
          <AmenityTile
            icon={GraduationCap}
            label="Escola mais próxima"
            distance={row.nearest_school_m}
          />
          <AmenityTile
            icon={Hospital}
            label="Hospital mais próximo"
            distance={row.nearest_hospital_m}
          />
        </div>

        {/* Avaliação visual (Vision LLM) — opcional, vira null sem foto */}
        {row.condition_assessment && (
          <ConditionAssessmentBlock
            condition={row.condition_assessment}
            latitude={latitude}
            longitude={longitude}
          />
        )}

        {/* Red / Green flags */}
        {(row.red_flags?.length || row.green_flags?.length) ? (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {row.green_flags && row.green_flags.length > 0 && (
              <FlagsList
                title="Pontos a favor"
                items={row.green_flags}
                icon={CheckCircle2}
                tone="success"
              />
            )}
            {row.red_flags && row.red_flags.length > 0 && (
              <FlagsList
                title="Pontos de atenção"
                items={row.red_flags}
                icon={AlertTriangle}
                tone="warning"
              />
            )}
          </div>
        ) : null}

        {/* Riscos urbanos */}
        {row.urban_risks && row.urban_risks.length > 0 && (
          <details className="rounded-md border border-dashed p-3 text-xs">
            <summary className="cursor-pointer font-medium text-foreground">
              Riscos urbanos identificados ({row.urban_risks.length})
            </summary>
            <ul className="mt-2 space-y-1.5">
              {row.urban_risks.map((r, i) => (
                <UrbanRiskRow key={i} risk={r} />
              ))}
            </ul>
          </details>
        )}

        {/* Recomendações */}
        {row.recommendations && row.recommendations.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Recomendações de diligência
            </h4>
            <ul className="space-y-1 text-xs">
              {row.recommendations.map((r, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="mt-1 size-1 shrink-0 rounded-full bg-primary" />
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Histórico de leilão */}
        {row.prior_auction_count != null && row.prior_auction_count > 0 && (
          <div className="rounded-md border border-warning/30 bg-warning-50 p-2 text-xs text-warning-700">
            <strong>Histórico de leilão:</strong> {row.prior_auction_count}{" "}
            menção(ões) a leilões anteriores deste imóvel.{" "}
            <span className="text-muted-foreground">
              (contagem por palavras-chave; verifique manualmente)
            </span>
          </div>
        )}

        {/* Fontes */}
        {row.source_documents && row.source_documents.length > 0 && (
          <details className="rounded-md border border-dashed p-3 text-xs">
            <summary className="cursor-pointer font-medium text-foreground">
              Fontes consultadas ({row.source_documents.length})
            </summary>
            <ul className="mt-2 space-y-1.5">
              {row.source_documents.map((s, i) => (
                <li key={i} className="flex items-start gap-2">
                  <ExternalLink className="mt-0.5 size-3 shrink-0" />
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary underline break-all"
                  >
                    {s.title || s.url}
                  </a>
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Mini-cards
// =============================================================================
function ScoreTile({
  label,
  score,
  confidence,
  sub,
}: {
  label: string;
  score: number | null | undefined;
  confidence?: DeepConfidence | null;
  sub?: string;
}) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className={`text-xl font-semibold ${scoreColor(score)}`}>
          {score ?? "—"}
          {score != null && <span className="text-xs">/5</span>}
        </span>
        {confidence && (
          <Badge variant={confidenceVariant(confidence)} className="text-[10px]">
            {confidenceLabel(confidence)}
          </Badge>
        )}
      </div>
      {sub && <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

function OutlierTile({
  isOutlier,
  sizeZ,
  priceZ,
}: {
  isOutlier: boolean;
  sizeZ: number | null | undefined;
  priceZ: number | null | undefined;
}) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        Outlier
      </div>
      <div className="mt-1">
        {isOutlier ? (
          <Badge variant="warning">atípico no bairro</Badge>
        ) : (
          <Badge variant="success">típico</Badge>
        )}
      </div>
      <div className="mt-1 text-[11px] text-muted-foreground">
        z(área) {sizeZ?.toFixed(1) ?? "—"} · z(preço) {priceZ?.toFixed(1) ?? "—"}
      </div>
    </div>
  );
}

function TrendTile({
  pct,
  confidence,
}: {
  pct: number | null | undefined;
  confidence?: DeepConfidence | null;
}) {
  const Icon = pct != null && pct >= 0 ? TrendingUp : TrendingDown;
  const color =
    pct == null ? "" : pct >= 0 ? "text-success-700" : "text-danger-700";
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        Tendência (12m)
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <Icon className={`size-4 ${color}`} />
        <span className={`text-xl font-semibold ${color}`}>
          {pct != null ? `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%` : "—"}
        </span>
      </div>
      {confidence && (
        <Badge variant={confidenceVariant(confidence)} className="mt-1 text-[10px]">
          {confidenceLabel(confidence)}
        </Badge>
      )}
    </div>
  );
}

function AmenityTile({
  icon: Icon,
  label,
  distance,
}: {
  icon: typeof TrainFront;
  label: string;
  distance: number | null | undefined;
}) {
  return (
    <div className="flex items-center gap-2 rounded-md border bg-card p-2.5 text-xs">
      <Icon className="size-4 text-muted-foreground shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-[11px] text-muted-foreground">{label}</div>
        <div className="font-medium">{fmtMeters(distance)}</div>
      </div>
    </div>
  );
}

// =============================================================================
function FlagsList({
  title,
  items,
  icon: Icon,
  tone,
}: {
  title: string;
  items: string[];
  icon: typeof CheckCircle2;
  tone: "success" | "warning";
}) {
  const cls =
    tone === "success"
      ? "border-success/30 bg-success-50 text-success-700"
      : "border-warning/30 bg-warning-50 text-warning-700";
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title} ({items.length})
      </h4>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li
            key={i}
            className={`flex items-start gap-2 rounded-md border p-2 text-xs ${cls}`}
          >
            <Icon className="mt-0.5 size-3.5 shrink-0" />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function UrbanRiskRow({ risk }: { risk: UrbanRiskItem }) {
  return (
    <li className="flex items-start gap-2">
      <Info className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
      <div className="flex-1">
        <div className="font-medium uppercase">{risk.type}</div>
        <div className="text-muted-foreground">{risk.summary}</div>
        {risk.source_url && (
          <a
            href={risk.source_url}
            target="_blank"
            rel="noreferrer"
            className="text-[10px] text-primary underline break-all"
          >
            {risk.source_url}
          </a>
        )}
      </div>
      <Badge variant={confidenceVariant(risk.confidence)} className="text-[10px]">
        {confidenceLabel(risk.confidence)}
      </Badge>
    </li>
  );
}

// =============================================================================
// ConditionAssessmentBlock — Vision LLM sobre Street View + aérea + edital
// =============================================================================
const NEIGHBORHOOD_PATTERN_META: Record<
  Exclude<ConditionAssessment["neighborhood_pattern"], null>,
  { label: string; tone: "success" | "warning" | "danger" | "secondary" }
> = {
  uniforme: { label: "Uniforme", tone: "success" },
  misto: { label: "Misto", tone: "secondary" },
  precario: { label: "Precário", tone: "warning" },
};

const PROPERTY_VS_NEIGHBORS_META: Record<
  Exclude<ConditionAssessment["property_vs_neighbors"], null>,
  { label: string; tone: "success" | "warning" | "danger" | "secondary" }
> = {
  acima: { label: "Acima dos vizinhos", tone: "success" },
  igual: { label: "Compatível", tone: "secondary" },
  abaixo: { label: "Abaixo dos vizinhos", tone: "warning" },
};

const RENO_SUGGESTION_LABEL: Record<
  Exclude<ConditionAssessment["suggested_renovation_level"], null>,
  string
> = {
  none: "Nenhuma",
  cosmetic: "Cosmética",
  light: "Leve",
  basic: "Básica",
  moderate: "Moderada",
  full: "Completa",
  premium: "Premium",
};

const SLOT_LABEL: Record<string, string> = {
  aerial: "Vista aérea",
  sv_front: "Frente do imóvel",
  sv_left: "Vizinho à esquerda",
  sv_right: "Vizinho à direita",
  sv_back: "Outro lado da rua",
  listing: "Foto do edital",
};

const SLOT_ORDER: string[] = [
  "aerial",
  "sv_front",
  "sv_left",
  "sv_right",
  "sv_back",
  "listing",
];

function slotFromUrl(url: string): string {
  // Path: .../{property_id}/{analysis_id}/{slot}.jpg
  const filename = url.split("/").pop() || "";
  return filename.replace(/\.[^.]+$/, "");
}

/** Heading do Street View para cada slot (graus, 0=N / 90=E / 180=S / 270=W). */
const SV_HEADING_BY_SLOT: Record<string, number> = {
  sv_front: 0,
  sv_left: 90,
  sv_back: 180,
  sv_right: 270,
};

/** Constrói o link do Google Maps adequado ao slot, ou null se sem coords.
 *
 * - `aerial` → Maps com layer satellite no ponto exato (`t=k`).
 * - `sv_*` → Street View interativo no ponto, com heading correspondente.
 * - `listing` → link direto da imagem (sem geo associada). */
function mapsLinkForSlot(
  slot: string,
  url: string,
  lat: number | null | undefined,
  lng: number | null | undefined,
): string {
  if (slot === "listing") return url;
  if (lat == null || lng == null) return url;
  if (slot === "aerial") {
    return `https://www.google.com/maps?q=${lat},${lng}&t=k&z=19`;
  }
  const heading = SV_HEADING_BY_SLOT[slot];
  if (heading != null) {
    return (
      "https://www.google.com/maps/@?api=1&map_action=pano" +
      `&viewpoint=${lat},${lng}&heading=${heading}&pitch=0&fov=80`
    );
  }
  return url;
}

function ConditionAssessmentBlock({
  condition,
  latitude,
  longitude,
}: {
  condition: ConditionAssessment;
  latitude?: number | null;
  longitude?: number | null;
}) {
  // Tolerância a análises antigas (pré-pivot): image_urls/risk_flags podem
  // vir undefined no JSONB do banco.
  const riskFlags = condition.risk_flags ?? [];
  const imageUrls = condition.image_urls ?? [];
  const hasInsights =
    condition.neighborhood_pattern != null ||
    condition.property_vs_neighbors != null ||
    condition.pool_observed_nearby != null ||
    condition.suggested_renovation_level != null ||
    riskFlags.length > 0;
  const hasImages = imageUrls.length > 0;
  const patternMeta = condition.neighborhood_pattern
    ? NEIGHBORHOOD_PATTERN_META[condition.neighborhood_pattern]
    : null;
  const vsMeta = condition.property_vs_neighbors
    ? PROPERTY_VS_NEIGHBORS_META[condition.property_vs_neighbors]
    : null;

  // Ordena URLs pela posição canônica do slot (aerial, sv_front, ..., listing).
  const orderedImages = [...imageUrls].sort((a, b) => {
    const ai = SLOT_ORDER.indexOf(slotFromUrl(a));
    const bi = SLOT_ORDER.indexOf(slotFromUrl(b));
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return (
    <div className="space-y-3 rounded-md border border-dashed bg-card/40 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Análise visual do entorno
        </h4>
        <Badge variant={confidenceVariant(condition.confidence)} className="text-[10px]">
          confiança {confidenceLabel(condition.confidence)}
        </Badge>
      </div>

      {!hasInsights && !hasImages ? (
        <div className="flex items-start gap-2 text-xs text-muted-foreground">
          <CameraOff className="mt-0.5 size-3.5 shrink-0" />
          <span>{condition.notes || "Sem análise visual disponível."}</span>
        </div>
      ) : (
        <>
          {/* Badges de entorno */}
          {hasInsights && (
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5 text-xs">
              {patternMeta && (
                <span>
                  <span className="text-muted-foreground">Padrão do bairro:</span>{" "}
                  <Badge variant={patternMeta.tone} className="text-[10px]">
                    {patternMeta.label}
                  </Badge>
                </span>
              )}
              {vsMeta && (
                <span>
                  <span className="text-muted-foreground">Imóvel vs vizinhos:</span>{" "}
                  <Badge variant={vsMeta.tone} className="text-[10px]">
                    {vsMeta.label}
                  </Badge>
                </span>
              )}
              {condition.pool_observed_nearby != null && (
                <span>
                  <span className="text-muted-foreground">Piscina próxima:</span>{" "}
                  <Badge
                    variant={
                      condition.pool_observed_nearby ? "success" : "secondary"
                    }
                    className="text-[10px]"
                  >
                    {condition.pool_observed_nearby ? "Sim" : "Não"}
                  </Badge>
                </span>
              )}
              {condition.suggested_renovation_level && (
                <span>
                  <span className="text-muted-foreground">Reforma sugerida:</span>{" "}
                  <strong>
                    {RENO_SUGGESTION_LABEL[condition.suggested_renovation_level]}
                  </strong>
                </span>
              )}
            </div>
          )}

          {/* Galeria de imagens capturadas */}
          {hasImages && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {orderedImages.map((url) => {
                const slot = slotFromUrl(url);
                const label = SLOT_LABEL[slot] || slot;
                const href = mapsLinkForSlot(slot, url, latitude, longitude);
                const opensMaps = href !== url;
                return (
                  <a
                    key={url}
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    title={
                      opensMaps
                        ? `Abrir no Google Maps: ${label}`
                        : label
                    }
                    className="block overflow-hidden rounded-md border bg-muted transition hover:border-primary"
                  >
                    {/* biome-ignore lint/performance/noImgElement: Supabase Storage, sem next/image loader configurado */}
                    <img
                      src={url}
                      alt={label}
                      className="aspect-video w-full object-cover"
                    />
                    <div className="flex items-center justify-between gap-1 px-2 py-1 text-[10px] text-muted-foreground">
                      <span>{label}</span>
                      {opensMaps && (
                        <ExternalLink className="size-3 shrink-0 opacity-60" />
                      )}
                    </div>
                  </a>
                );
              })}
            </div>
          )}

          {/* Notes + risk flags */}
          {condition.notes && (
            <p className="text-[11px] text-muted-foreground">{condition.notes}</p>
          )}
          {riskFlags.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-danger-700">
                Riscos do entorno observados
              </div>
              <ul className="space-y-1 text-xs">
                {riskFlags.map((flag, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 size-3 shrink-0 text-danger-700" />
                    <span>{flag}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-[10px] text-muted-foreground italic">
            Sinal informativo — não substitui o nível de reforma que você
            informou no Agente 3.
          </p>
        </>
      )}
    </div>
  );
}

function scoreColor(score: number | null | undefined): string {
  if (score == null) return "";
  if (score >= 4) return "text-success-700";
  if (score === 3) return "";
  if (score === 2) return "text-warning-700";
  return "text-danger-700";
}

// =============================================================================
// Liquidez: subtítulo agora combina densidade + população
// =============================================================================
function liquiditySub(row: DeepAnalysisRow): string | undefined {
  const ev = row.liquidity_evidence as
    | { listings_per_km2?: number | null }
    | null
    | undefined;
  const density = ev?.listings_per_km2;
  const parts: string[] = [];
  if (typeof density === "number" && Number.isFinite(density)) {
    parts.push(`${density.toFixed(1)} listings/km²`);
  }
  if (row.city_population != null) {
    parts.push(`${row.city_population.toLocaleString("pt-BR")} hab.`);
  }
  return parts.length > 0 ? parts.join(" · ") : undefined;
}

// =============================================================================
// NeighborhoodClassBlock — tier do bairro + 3 concorrentes
// =============================================================================
const TIER_META: Record<
  NonNullable<NeighborhoodClass["tier"]>,
  { tone: "success" | "secondary" | "warning"; label: string }
> = {
  A: { tone: "success", label: "A · premium" },
  B: { tone: "secondary", label: "B · médio-alto" },
  C: { tone: "secondary", label: "C · médio" },
  D: { tone: "warning", label: "D · popular" },
};

function NeighborhoodClassBlock({ cls }: { cls: NeighborhoodClass }) {
  const competitors = cls.competing_neighborhoods ?? [];
  const tierMeta = cls.tier ? TIER_META[cls.tier] : null;
  const ratioPct =
    cls.ratio != null ? `${(cls.ratio * 100).toFixed(0)}% da cidade` : null;

  return (
    <div className="space-y-3 rounded-md border border-dashed bg-card/40 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Building2 className="size-3.5" />
          Classe do bairro
        </h4>
        <Badge
          variant={confidenceVariant(cls.confidence)}
          className="text-[10px]"
        >
          confiança {confidenceLabel(cls.confidence)}
        </Badge>
      </div>

      {tierMeta ? (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5 text-xs">
          <Badge variant={tierMeta.tone} className="text-[11px]">
            {tierMeta.label}
          </Badge>
          {cls.target_ppm2_median != null && (
            <span className="text-muted-foreground">
              ppm² bairro:{" "}
              <strong className="text-foreground">
                {formatBRL(cls.target_ppm2_median)}
              </strong>
            </span>
          )}
          {cls.city_ppm2_brl != null && (
            <span className="text-muted-foreground">
              ppm² cidade:{" "}
              <strong className="text-foreground">
                {formatBRL(cls.city_ppm2_brl)}
              </strong>
            </span>
          )}
          {ratioPct && (
            <span className="text-muted-foreground">{ratioPct}</span>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Amostra insuficiente no bairro para classificação.
        </p>
      )}

      {competitors.length > 0 && (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Bairros concorrentes (ppm² semelhante)
          </div>
          <ul className="space-y-1 text-xs">
            {competitors.map((c) => (
              <li
                key={c.name}
                className="flex items-center justify-between gap-2 rounded-md border bg-card px-2 py-1"
              >
                <span className="truncate font-medium">{c.name}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {c.distance_km.toFixed(1)} km · {formatBRL(c.ppm2_median)}/m²
                  · {c.n_listings} anúncios
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Indicar uso para mantermos o lint feliz e suportar formatPct se necessário no futuro
void formatPct;
