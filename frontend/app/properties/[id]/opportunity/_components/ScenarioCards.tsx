"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { OpportunityResult, OpportunityScenario } from "@/lib/api";
import { formatBRL, formatPct } from "@/lib/utils";

const SCENARIO_LABELS: Record<OpportunityScenario["label"], string> = {
  pessimista: "Pessimista",
  realista: "Realista",
  otimista: "Otimista",
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
        <ScenarioCard key={s.label} s={s} highlighted={s.label === "realista"} />
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
  const profitColor =
    s.net_profit >= 0
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-destructive";

  return (
    <Card
      className={
        highlighted ? "border-primary shadow-md ring-1 ring-primary/40" : ""
      }
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-baseline justify-between text-base">
          <span>{SCENARIO_LABELS[s.label]}</span>
          <span className="text-xs font-normal text-muted-foreground">
            Venda {formatBRL(s.sale_price)}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="rounded-md bg-muted/40 p-3">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">Lucro líquido</span>
            <span className={`text-lg font-semibold ${profitColor}`}>
              {formatBRL(s.net_profit)}
            </span>
          </div>
          <div className="mt-1 flex items-baseline justify-between">
            <span className="text-xs text-muted-foreground">ROI líquido</span>
            <span className={`text-sm font-medium ${profitColor}`}>
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

        <div className="space-y-1.5 border-t pt-3 text-muted-foreground">
          <Row label="Corretor (venda)" value={formatBRL(s.realtor_fee)} />
          <Row label="Imposto de renda" value={formatBRL(s.income_tax)} />
          <Row label="Lucro bruto" value={formatBRL(s.gross_profit)} />
          <Row label="ROI bruto" value={formatPct(s.gross_roi_pct)} />
        </div>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  bold,
}: {
  label: string;
  value: string;
  bold?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className={bold ? "font-semibold text-foreground" : "text-foreground"}>
        {value}
      </span>
    </div>
  );
}
