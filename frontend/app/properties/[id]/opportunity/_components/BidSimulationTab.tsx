"use client";

import { ArrowRight, Target, UserCheck } from "lucide-react";
import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type {
  OpportunityInput,
  OpportunityResult,
  Property,
  Valuation,
  Verdict,
} from "@/lib/api";
import { runAnalysisLocal } from "@/lib/opportunity-math";
import { roiTier } from "@/lib/roi-tiers";
import { formatBRL } from "@/lib/utils";

const N_STEPS = 12;

type SimulationPoint = {
  bid: number;
  pessimistRoi: number;
  realistRoi: number;
  optimistRoi: number;
  pessimistSale: number;
  realistSale: number;
  optimistSale: number;
  realistProfit: number;
  verdict: Verdict;
  /** Tupla [pess, otim] usada pelo Area do Recharts para desenhar a banda. */
  band: [number, number];
};

type SimulationRange = {
  min: number;
  max: number;
};

/** Determina o range de lances. Inclui pelo menos: lance mínimo (1ª praça),
 * 130% do valor de avaliação e o lance digitado pelo usuário. */
function deriveRange(
  property: Property,
  result: OpportunityResult,
  bidAmount: number,
): SimulationRange {
  const minBids = [
    property.minimum_bid_second,
    property.minimum_bid_first,
  ].filter((v): v is number => v != null && v > 0);

  const start =
    minBids.length > 0
      ? Math.min(...minBids)
      : (property.appraisal_value ?? bidAmount) * 0.5;

  const end =
    property.appraisal_value != null
      ? property.appraisal_value * 1.3
      : result.max_bid_for_target != null
        ? result.max_bid_for_target * 2
        : bidAmount * 1.5;

  // Garante que o lance do usuário caia no range.
  const min = Math.max(1, Math.min(start, bidAmount * 0.9));
  const max = Math.max(end, bidAmount * 1.1);
  return { min, max };
}

function buildSimulations(
  input: OpportunityInput,
  property: Property,
  valuation: Valuation | null,
  range: SimulationRange,
): SimulationPoint[] {
  const out: SimulationPoint[] = [];
  const span = range.max - range.min;
  if (span <= 0) return out;
  for (let i = 0; i < N_STEPS; i++) {
    const bid = Math.round(range.min + (span * i) / (N_STEPS - 1));
    const r = runAnalysisLocal({
      input: { ...input, bid_amount: bid },
      property,
      valuation,
      auctioneerSlug: null,
    });
    const pessRoi = r.pessimista.annualized_net_roi_pct;
    const optRoi = r.otimista.annualized_net_roi_pct;
    out.push({
      bid,
      pessimistRoi: pessRoi,
      realistRoi: r.realista.annualized_net_roi_pct,
      optimistRoi: optRoi,
      pessimistSale: r.pessimista.sale_price,
      realistSale: r.realista.sale_price,
      optimistSale: r.otimista.sale_price,
      realistProfit: r.realista.net_profit,
      verdict: r.verdict,
      band: [pessRoi, optRoi],
    });
  }
  return out;
}

/** Acha o ponto da simulação mais próximo de um marco para destacar. */
function closestPoint(
  sims: SimulationPoint[],
  target: number | null | undefined,
): number | null {
  if (target == null || !Number.isFinite(target)) return null;
  let bestIdx = -1;
  let bestDist = Infinity;
  sims.forEach((p, i) => {
    const d = Math.abs(p.bid - target);
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  });
  return bestIdx;
}

function formatBRLShort(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000) return `R$ ${(v / 1_000).toFixed(0)}k`;
  return formatBRL(v);
}

function formatPctSigned(roi: number): string {
  const pct = roi * 100;
  if (!Number.isFinite(pct)) return "—";
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(0)}%`;
}

const VERDICT_BADGE: Record<
  Verdict,
  { label: string; variant: "success" | "warning" | "destructive" | "secondary" }
> = {
  BOA_OPORTUNIDADE: { label: "Boa", variant: "success" },
  BOA_COM_RESSALVAS: { label: "Ressalvas", variant: "warning" },
  NEUTRO: { label: "Neutro", variant: "secondary" },
  INVIAVEL: { label: "Inviável", variant: "destructive" },
  INDETERMINADO: { label: "—", variant: "secondary" },
};

// =============================================================================
// Tooltip customizado do gráfico
// =============================================================================
function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: SimulationPoint }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const pt = payload[0]?.payload;
  if (!pt) return null;
  const realMeta = roiTier(pt.realistRoi);
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <div className="mb-1 font-medium">Lance: {formatBRL(pt.bid)}</div>
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">Pessimista</span>
          <span>
            <span>{formatPctSigned(pt.pessimistRoi)}</span>{" "}
            <span className="text-[10px] text-muted-foreground">
              · venda {formatBRLShort(pt.pessimistSale)}
            </span>
          </span>
        </div>
        <div className="flex items-center justify-between gap-4 font-semibold">
          <span>Realista</span>
          <span>
            <span style={{ color: realMeta.lineColor }}>
              {formatPctSigned(pt.realistRoi)}
            </span>{" "}
            <span className="text-[10px] font-normal text-muted-foreground">
              · venda {formatBRLShort(pt.realistSale)}
            </span>
          </span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <span className="text-muted-foreground">Otimista</span>
          <span>
            <span>{formatPctSigned(pt.optimistRoi)}</span>{" "}
            <span className="text-[10px] text-muted-foreground">
              · venda {formatBRLShort(pt.optimistSale)}
            </span>
          </span>
        </div>
      </div>
      <div className="mt-1.5 border-t pt-1.5 text-[11px] text-muted-foreground">
        Lucro líquido (real.):{" "}
        <strong className="text-foreground">
          {formatBRL(pt.realistProfit)}
        </strong>
      </div>
      <div className="mt-0.5">
        <Badge
          variant={VERDICT_BADGE[pt.verdict].variant}
          className="text-[10px]"
        >
          {VERDICT_BADGE[pt.verdict].label}
        </Badge>
      </div>
    </div>
  );
}

// =============================================================================
// Componente principal
// =============================================================================
export function BidSimulationTab({
  input,
  property,
  valuation,
  result,
}: {
  input: OpportunityInput;
  property: Property;
  valuation: Valuation | null;
  result: OpportunityResult;
}) {
  const range = useMemo(
    () => deriveRange(property, result, input.bid_amount),
    [property, result, input.bid_amount],
  );
  const simulations = useMemo(
    () => buildSimulations(input, property, valuation, range),
    [input, property, valuation, range],
  );

  const targetRoi = input.target_net_roi_pct;
  const maxBidIdx = closestPoint(simulations, result.max_bid_for_target);
  const userBidIdx = closestPoint(simulations, input.bid_amount);

  const allRois = simulations.flatMap((s) => [
    s.pessimistRoi,
    s.realistRoi,
    s.optimistRoi,
  ]);
  const yMin = Math.min(-0.3, Math.floor(Math.min(...allRois) * 10) / 10);
  const yMax = Math.max(1.2, Math.ceil(Math.max(...allRois) * 10) / 10);

  // Marcos relevantes (1ª praça, 2ª praça, avaliação) — para ReferenceLines.
  const milestones: { x: number; label: string; color: string }[] = [];
  if (
    property.minimum_bid_first != null &&
    property.minimum_bid_first >= range.min &&
    property.minimum_bid_first <= range.max
  ) {
    milestones.push({
      x: property.minimum_bid_first,
      label: "1ª praça",
      color: "#94a3b8",
    });
  }
  if (
    property.minimum_bid_second != null &&
    property.minimum_bid_second >= range.min &&
    property.minimum_bid_second <= range.max &&
    property.minimum_bid_second !== property.minimum_bid_first
  ) {
    milestones.push({
      x: property.minimum_bid_second,
      label: "2ª praça",
      color: "#94a3b8",
    });
  }
  if (
    property.appraisal_value != null &&
    property.appraisal_value >= range.min &&
    property.appraisal_value <= range.max
  ) {
    milestones.push({
      x: property.appraisal_value,
      label: "avaliação",
      color: "#64748b",
    });
  }

  return (
    <div className="space-y-4">
      {/* Header explicativo */}
      <div className="rounded-md border border-dashed bg-card/40 p-3 text-xs text-muted-foreground">
        Simulação de {N_STEPS} lances entre {formatBRLShort(range.min)} e{" "}
        {formatBRLShort(range.max)}. O ROI realista é a linha sólida; a banda
        cinza mostra o intervalo entre pessimista e otimista. Faixas de fundo:
        verde-escuro ≥ 50% · verde 20-50% · amarelo 5-20% · laranja 0-5% ·
        vermelho &lt; 0%. ROI alvo:{" "}
        <strong className="text-foreground">
          {(targetRoi * 100).toFixed(0)}%
        </strong>{" "}
        a.a.
      </div>

      {/* Gráfico */}
      <Card>
        <CardContent className="pt-6">
          <div
            className="h-[320px] w-full"
            aria-label="Gráfico de ROI anualizado por lance"
          >
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={simulations}
                margin={{ top: 10, right: 20, bottom: 8, left: 0 }}
              >
                <CartesianGrid
                  stroke="var(--border)"
                  strokeDasharray="3 3"
                />

                {/* Faixas de fundo coloridas por tier de ROI — opacity baixa
                    funciona tanto em light quanto em dark mode. */}
                <ReferenceArea
                  y1={0.5}
                  y2={yMax}
                  fill="#22c55e"
                  fillOpacity={0.16}
                  ifOverflow="hidden"
                />
                <ReferenceArea
                  y1={0.2}
                  y2={0.5}
                  fill="#84cc16"
                  fillOpacity={0.12}
                  ifOverflow="hidden"
                />
                <ReferenceArea
                  y1={0.05}
                  y2={0.2}
                  fill="#eab308"
                  fillOpacity={0.14}
                  ifOverflow="hidden"
                />
                <ReferenceArea
                  y1={0}
                  y2={0.05}
                  fill="#f97316"
                  fillOpacity={0.14}
                  ifOverflow="hidden"
                />
                <ReferenceArea
                  y1={yMin}
                  y2={0}
                  fill="#ef4444"
                  fillOpacity={0.16}
                  ifOverflow="hidden"
                />

                <XAxis
                  dataKey="bid"
                  type="number"
                  domain={[range.min, range.max]}
                  tickFormatter={(v: number) => formatBRLShort(v)}
                  tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                  stroke="var(--border)"
                />
                <YAxis
                  domain={[yMin, yMax]}
                  tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                  stroke="var(--border)"
                />

                {/* Banda pessimista ↔ otimista (Area com array [low, high] —
                    desenha só o intervalo, sem precisar do truque branco). */}
                <Area
                  type="monotone"
                  dataKey="band"
                  stroke="none"
                  fill="var(--foreground)"
                  fillOpacity={0.12}
                  isAnimationActive={false}
                  name="banda pessimista-otimista"
                />

                {/* Linha realista — usa foreground para contraste em ambos os modos */}
                <Line
                  type="monotone"
                  dataKey="realistRoi"
                  stroke="var(--foreground)"
                  strokeWidth={2.2}
                  dot={false}
                  isAnimationActive={false}
                  name="ROI realista (a.a.)"
                />

                {/* Linha do ROI alvo */}
                <ReferenceLine
                  y={targetRoi}
                  stroke="#3b82f6"
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  label={{
                    value: `ROI alvo ${(targetRoi * 100).toFixed(0)}%`,
                    fill: "#3b82f6",
                    fontSize: 10,
                    position: "insideTopRight",
                  }}
                />

                {/* Marcos verticais (cinza neutro tematizável) */}
                {milestones.map((m) => (
                  <ReferenceLine
                    key={`m-${m.label}`}
                    x={m.x}
                    stroke="var(--muted-foreground)"
                    strokeOpacity={0.5}
                    strokeDasharray="2 4"
                    label={{
                      value: m.label,
                      fill: "var(--muted-foreground)",
                      fontSize: 10,
                      position: "top",
                    }}
                  />
                ))}

                {/* Lance máximo p/ ROI alvo */}
                {result.max_bid_for_target != null &&
                  result.max_bid_for_target >= range.min &&
                  result.max_bid_for_target <= range.max && (
                    <ReferenceLine
                      x={result.max_bid_for_target}
                      stroke="#10b981"
                      strokeWidth={2}
                      label={{
                        value: "máx p/ ROI alvo",
                        fill: "#10b981",
                        fontSize: 11,
                        position: "insideTopLeft",
                      }}
                    />
                  )}

                {/* Lance atual do usuário */}
                {input.bid_amount > 0 &&
                  input.bid_amount >= range.min &&
                  input.bid_amount <= range.max && (
                    <ReferenceLine
                      x={input.bid_amount}
                      stroke="#a855f7"
                      strokeWidth={2}
                      label={{
                        value: "seu lance",
                        fill: "#a855f7",
                        fontSize: 11,
                        position: "insideBottomRight",
                      }}
                    />
                  )}

                <Tooltip
                  content={<ChartTooltip />}
                  cursor={{
                    stroke: "var(--muted-foreground)",
                    strokeOpacity: 0.4,
                    strokeDasharray: "3 3",
                  }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Tabela */}
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Lance
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                ROI pess.<br />
                <span className="text-[10px] font-normal normal-case opacity-70">
                  venda
                </span>
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                ROI real.<br />
                <span className="text-[10px] font-normal normal-case opacity-70">
                  venda
                </span>
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                ROI otim.<br />
                <span className="text-[10px] font-normal normal-case opacity-70">
                  venda
                </span>
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Lucro real.
              </th>
              <th scope="col" className="px-3 py-2 text-center">
                Verdict
              </th>
            </tr>
          </thead>
          <tbody>
            {simulations.map((s, i) => {
              const isMaxBid = i === maxBidIdx;
              const isUserBid = i === userBidIdx;
              const pess = roiTier(s.pessimistRoi);
              const real = roiTier(s.realistRoi);
              const opt = roiTier(s.optimistRoi);
              const profitMeta = roiTier(s.realistRoi); // mesmo tier do realista
              const verdictMeta = VERDICT_BADGE[s.verdict];
              return (
                <tr
                  key={s.bid}
                  className={`border-t ${
                    isUserBid
                      ? "ring-2 ring-inset ring-violet-500"
                      : ""
                  }`}
                >
                  <th
                    scope="row"
                    className="px-3 py-1.5 text-left font-medium"
                  >
                    <div className="flex items-center gap-1.5">
                      {isMaxBid && (
                        <span
                          title="Lance máximo para o ROI alvo"
                          className="inline-flex items-center text-green-700"
                        >
                          <Target className="size-3.5" />
                        </span>
                      )}
                      {isUserBid && (
                        <span
                          title="Seu lance atual"
                          className="inline-flex items-center text-violet-700"
                        >
                          <UserCheck className="size-3.5" />
                        </span>
                      )}
                      {formatBRL(s.bid)}
                    </div>
                  </th>
                  <td
                    className={`px-3 py-1.5 text-right font-mono text-xs leading-tight ${pess.cellClass}`}
                  >
                    <div>{formatPctSigned(s.pessimistRoi)}</div>
                    <div className="text-[10px] opacity-70">
                      {formatBRLShort(s.pessimistSale)}
                    </div>
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right font-mono text-xs font-semibold leading-tight ${real.cellClass}`}
                  >
                    <div>{formatPctSigned(s.realistRoi)}</div>
                    <div className="text-[10px] font-normal opacity-70">
                      {formatBRLShort(s.realistSale)}
                    </div>
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right font-mono text-xs leading-tight ${opt.cellClass}`}
                  >
                    <div>{formatPctSigned(s.optimistRoi)}</div>
                    <div className="text-[10px] opacity-70">
                      {formatBRLShort(s.optimistSale)}
                    </div>
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right font-mono text-xs ${profitMeta.cellClass}`}
                  >
                    {formatBRL(s.realistProfit)}
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <Badge
                      variant={verdictMeta.variant}
                      className="text-[10px]"
                    >
                      {verdictMeta.label}
                    </Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <Target className="size-3 text-green-700" />
          Lance máximo para o ROI alvo
        </span>
        <span className="inline-flex items-center gap-1">
          <UserCheck className="size-3 text-violet-700" />
          Seu lance digitado
        </span>
        <span className="inline-flex items-center gap-1">
          <ArrowRight className="size-3" />
          Linha sólida cinza no gráfico: ROI realista por lance
        </span>
      </div>
    </div>
  );
}
