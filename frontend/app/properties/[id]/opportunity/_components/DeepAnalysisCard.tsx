"use client";

import {
  AlertTriangle,
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
  DeepAnalysisRow,
  DeepConfidence,
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

export function DeepAnalysisCard({ row }: { row: DeepAnalysisRow }) {
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
            sub={
              row.city_population != null
                ? `${row.city_population.toLocaleString("pt-BR")} hab.`
                : undefined
            }
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

function scoreColor(score: number | null | undefined): string {
  if (score == null) return "";
  if (score >= 4) return "text-success-700";
  if (score === 3) return "";
  if (score === 2) return "text-warning-700";
  return "text-danger-700";
}

// Indicar uso para mantermos o lint feliz e suportar formatPct se necessário no futuro
void formatPct;
