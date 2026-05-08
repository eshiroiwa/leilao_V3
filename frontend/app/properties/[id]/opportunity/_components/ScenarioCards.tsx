"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { OpportunityResult, OpportunityScenario } from "@/lib/api";
import { cn, formatBRL, formatPct } from "@/lib/utils";

const SCENARIO_META: Record<
  OpportunityScenario["label"],
  { label: string; bar: string; chip: string }
> = {
  pessimista: {
    label: "Pessimista",
    bar: "bg-danger",
    chip: "bg-danger-100 text-danger-700",
  },
  realista: {
    label: "Realista",
    bar: "bg-primary",
    chip: "bg-primary-100 text-primary-700",
  },
  otimista: {
    label: "Otimista",
    bar: "bg-success",
    chip: "bg-success-100 text-success-700",
  },
};

export function ScenarioCards({ result }: { result: OpportunityResult }) {
  const scenarios: OpportunityScenario[] = [
    result.pessimista,
    result.realista,
    result.otimista,
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {scenarios.map((s) => (
        <ScenarioCard
          key={s.label}
          s={s}
          highlighted={s.label === "realista"}
        />
      ))}
    </div>
  );
}

function ScenarioCard({
  s,
  highlighted,
}: {
  s: OpportunityScenario;
  highlighted: boolean;
}) {
  const meta = SCENARIO_META[s.label];
  const isProfit = s.net_profit >= 0;
  const profitColor = isProfit ? "text-success-700" : "text-danger-700";
  const summaryBg = isProfit
    ? "bg-success-50 border-success/20"
    : "bg-danger-50 border-danger/20";

  return (
    <Card
      className={cn(
        "relative overflow-hidden transition-all hover:shadow-md",
        highlighted && "shadow-md ring-1 ring-primary/30",
      )}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", meta.bar)} />
      <CardHeader className="pb-2 pl-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
                meta.chip,
              )}
            >
              {meta.label}
            </span>
            {highlighted && (
              <span className="text-[10px] font-medium uppercase tracking-wider text-primary-700">
                referência
              </span>
            )}
          </div>
          <CardTitle className="text-xs font-normal text-muted-foreground">
            Venda {formatBRL(s.sale_price)}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pl-5 text-sm">
        <div className={cn("rounded-lg border p-3", summaryBg)}>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">Lucro líquido</span>
            <span className={cn("text-lg font-semibold tabular-nums", profitColor)}>
              {formatBRL(s.net_profit)}
            </span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">ROI líquido</span>
            <span className={cn("text-sm font-medium tabular-nums", profitColor)}>
              {formatPct(s.net_roi_pct)}
            </span>
          </div>
        </div>

        <div className="space-y-1.5 border-t pt-3">
          <Row label="Lance" value={formatBRL(s.bid)} />
          <Row label="Comissão leiloeiro" value={formatBRL(s.auctioneer_fee)} />
          <Row label="ITBI" value={formatBRL(s.itbi)} />
          <Row label="Registro" value={formatBRL(s.registration)} />
          {s.iptu_arrears > 0 && (
            <Row label="IPTU atrasado" value={formatBRL(s.iptu_arrears)} />
          )}
          {s.condo_arrears > 0 && (
            <Row label="Condomínio atrasado" value={formatBRL(s.condo_arrears)} />
          )}
          {s.renovation_cost > 0 && (
            <Row label="Reforma" value={formatBRL(s.renovation_cost)} />
          )}
          {s.other_costs > 0 && (
            <Row label="Outros" value={formatBRL(s.other_costs)} />
          )}
          <Row
            label="Custo aquisição"
            value={formatBRL(s.total_acquisition_cost)}
            bold
          />
        </div>

        <div className="space-y-1.5 border-t pt-3">
          <Row label="Corretor (venda)" value={formatBRL(s.realtor_fee)} muted />
          <Row label="Imposto de renda" value={formatBRL(s.income_tax)} muted />
          <Row label="Lucro bruto" value={formatBRL(s.gross_profit)} muted />
          <Row label="ROI bruto" value={formatPct(s.gross_roi_pct)} muted />
        </div>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  bold,
  muted,
}: {
  label: string;
  value: string;
  bold?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between text-xs">
      <span className={muted ? "text-muted-foreground" : "text-muted-foreground"}>
        {label}
      </span>
      <span
        className={cn(
          "tabular-nums",
          bold ? "font-semibold text-foreground" : "text-foreground",
          muted && "text-muted-foreground",
        )}
      >
        {value}
      </span>
    </div>
  );
}
