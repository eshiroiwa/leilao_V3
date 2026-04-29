"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  Confidence,
  Property,
  Valuation,
  ValuationDetail,
} from "@/lib/api";

import { ComparablesMap } from "./ComparablesMap";
import { ComparablesTable } from "./ComparablesTable";

const CONFIDENCE_VARIANT: Record<
  Confidence,
  "success" | "warning" | "destructive" | "secondary"
> = {
  HIGH: "success",
  MEDIUM: "warning",
  LOW: "destructive",
  INSUFFICIENT: "secondary",
};

const CONFIDENCE_LABEL: Record<Confidence, string> = {
  HIGH: "Alta",
  MEDIUM: "Média",
  LOW: "Baixa",
  INSUFFICIENT: "Insuficiente",
};

export function ValuationDetailView({
  property,
  valuation,
  detail,
  history,
}: {
  property: Property;
  valuation: Valuation;
  detail: ValuationDetail | null;
  history: Valuation[];
}) {
  const [showRejected, setShowRejected] = useState(false);

  const comparables = detail?.comparables ?? [];
  const visible = showRejected ? comparables : comparables.filter((c) => c.used);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle className="text-base">
              Estimativa de mercado
            </CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Calculada em {new Date(valuation.created_at).toLocaleString("pt-BR")}
              {" · "}
              estratégia: {valuation.search_strategy ?? "—"}
              {" · "}
              raio: {valuation.search_radius_m ? `${valuation.search_radius_m} m` : "—"}
            </p>
          </div>
          <Badge variant={CONFIDENCE_VARIANT[valuation.confidence]}>
            {CONFIDENCE_LABEL[valuation.confidence]}
          </Badge>
        </CardHeader>
        <CardContent>
          {valuation.confidence === "INSUFFICIENT" ? (
            <p className="text-sm text-muted-foreground">
              Não foi possível obter uma quantidade mínima de comparáveis
              confiáveis para este imóvel. O sistema NÃO sugere preço — isso é
              proposital para evitar avaliações enganosas.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <Big label="Preço estimado" value={fmtBRL(valuation.estimated_price)} />
              <Big
                label="Intervalo (P10–P90)"
                value={`${fmtBRL(valuation.price_lower_bound)} – ${fmtBRL(valuation.price_upper_bound)}`}
              />
              <Big
                label="R$/m² mediano"
                value={fmtBRL(valuation.ppm2_estimated)}
              />
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
            <span>
              Comparáveis usados: <strong>{valuation.comparables_used}</strong>
            </span>
            <span>
              Rejeitados: <strong>{valuation.comparables_rejected}</strong>
            </span>
            <span>
              Firecrawl: <strong>{valuation.firecrawl_calls}</strong>
            </span>
            <span>
              LLM: <strong>{valuation.llm_calls}</strong>
            </span>
            <span>
              Custo estimado:{" "}
              <strong>
                R$ {(valuation.cost_estimate_brl ?? 0).toFixed(2)}
              </strong>
            </span>
          </div>
        </CardContent>
      </Card>

      {comparables.length > 0 && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Mapa de comparáveis</CardTitle>
            </CardHeader>
            <CardContent className="h-[420px] p-0">
              <ComparablesMap target={property} comparables={visible} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">
                Comparáveis ({visible.length})
              </CardTitle>
              <button
                className="text-xs text-muted-foreground hover:text-primary"
                onClick={() => setShowRejected((v) => !v)}
              >
                {showRejected ? "Esconder rejeitados" : "Mostrar rejeitados"}
              </button>
            </CardHeader>
            <CardContent className="p-0">
              <ComparablesTable comparables={visible} />
            </CardContent>
          </Card>
        </>
      )}

      {history.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Histórico</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {history.map((v) => (
                <li
                  key={v.id}
                  className="flex items-center justify-between text-muted-foreground"
                >
                  <span>{new Date(v.created_at).toLocaleString("pt-BR")}</span>
                  <span>
                    {fmtBRL(v.estimated_price) ?? "—"}{" "}
                    <Badge variant={CONFIDENCE_VARIANT[v.confidence]}>
                      {v.confidence}
                    </Badge>
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Big({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold">{value ?? "—"}</div>
    </div>
  );
}

function fmtBRL(v: number | null | undefined): string | null {
  if (v == null) return null;
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(v);
}
