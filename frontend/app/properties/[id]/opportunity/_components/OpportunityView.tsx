"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  api,
  type OpportunityAnalysisRow,
  type OpportunityInput,
  type OpportunityResult,
  type Property,
  type Valuation,
} from "@/lib/api";
import {
  DEFAULT_TARGET_NET_ROI,
  otherCostsDefaultFor,
  runAnalysisLocal,
} from "@/lib/opportunity-math";

import { OpportunityForm } from "./OpportunityForm";
import { ScenarioCards } from "./ScenarioCards";
import { VerdictCard } from "./VerdictCard";

export function OpportunityView({
  property,
  valuation,
  history,
}: {
  property: Property;
  valuation: Valuation | null;
  history: OpportunityAnalysisRow[];
}) {
  // Defaults: lance = 1ª praça; outros custos baseados em ocupação;
  // dívidas vindas do edital (Agente 1).
  const initialInput = useMemo<OpportunityInput>(
    () => ({
      buyer_type: "PF",
      target_net_roi_pct: DEFAULT_TARGET_NET_ROI,
      renovation_level: "moderate",
      bid_amount: property.minimum_bid_first ?? 0,
      other_costs: otherCostsDefaultFor(property.occupancy_status),
      iptu_arrears: property.iptu_arrears ?? 0,
      condo_arrears: property.condo_arrears ?? 0,
    }),
    [property],
  );

  const [input, setInput] = useState<OpportunityInput>(initialInput);

  // Cálculo client-side instantâneo (preview).
  const result: OpportunityResult = useMemo(
    () =>
      runAnalysisLocal({
        input,
        property,
        valuation,
        auctioneerSlug: null,
      }),
    [input, property, valuation],
  );

  // Persistência
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedHistory, setSavedHistory] =
    useState<OpportunityAnalysisRow[]>(history);

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api.saveOpportunity(property.id, input);
      // O backend é fonte de verdade — recarrega lista e injeta no topo.
      const updated = await api.listOpportunities(property.id).catch(() => []);
      setSavedHistory(updated.length ? updated : [
        {
          id: res.id,
          property_id: property.id,
          valuation_id: valuation?.id ?? null,
          buyer_type: input.buyer_type,
          target_net_roi_pct: input.target_net_roi_pct,
          renovation_level: input.renovation_level,
          bid_amount: input.bid_amount,
          other_costs: input.other_costs,
          iptu_arrears: input.iptu_arrears,
          condo_arrears: input.condo_arrears,
          scenarios: {
            pessimista: res.result.pessimista,
            realista: res.result.realista,
            otimista: res.result.otimista,
          },
          max_bid_for_target: res.result.max_bid_for_target,
          verdict: res.result.verdict,
          warnings: res.result.warnings,
          assumptions: res.result.assumptions,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    setInput(initialInput);
  }, [initialInput]);

  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className="space-y-4">
        <OpportunityForm
          input={input}
          onChange={setInput}
          property={property}
          assumptions={result.assumptions}
        />

        <Card>
          <CardContent className="space-y-2 pt-6">
            <Button
              className="w-full"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Salvando…" : "Salvar análise"}
            </Button>
            {saveError && (
              <p className="text-xs text-destructive">{saveError}</p>
            )}
            <p className="text-[11px] text-muted-foreground">
              Os números no painel são calculados localmente para resposta
              instantânea. Ao salvar, o servidor recalcula com a versão
              autoritativa e regista a análise para auditoria.
            </p>
          </CardContent>
        </Card>
      </aside>

      <section className="space-y-6">
        <VerdictCard result={result} property={property} />

        <ScenarioCards result={result} />

        {savedHistory.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Histórico de análises ({savedHistory.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {savedHistory.map((row) => (
                <div
                  key={row.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3"
                >
                  <div>
                    <div className="font-medium">
                      {new Date(row.created_at).toLocaleString("pt-BR")}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {row.buyer_type} · ROI alvo{" "}
                      {Math.round(row.target_net_roi_pct * 100)}% · reforma{" "}
                      {row.renovation_level}
                    </div>
                  </div>
                  <Badge variant={verdictVariant(row.verdict)}>
                    {verdictLabel(row.verdict)}
                  </Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  );
}

function verdictVariant(
  v: OpportunityResult["verdict"],
): "success" | "warning" | "destructive" | "secondary" {
  if (v === "BOA_OPORTUNIDADE") return "success";
  if (v === "BOA_COM_RESSALVAS") return "warning";
  if (v === "INVIAVEL") return "destructive";
  return "secondary";
}

function verdictLabel(v: OpportunityResult["verdict"]): string {
  return {
    BOA_OPORTUNIDADE: "Boa oportunidade",
    BOA_COM_RESSALVAS: "Boa, com ressalvas",
    NEUTRO: "Neutro",
    INVIAVEL: "Inviável",
    INDETERMINADO: "Indeterminado",
  }[v];
}
