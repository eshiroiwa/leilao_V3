"use client";

import { History, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

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
import { formatBRL } from "@/lib/utils";

import { LegalCheckCard } from "./LegalCheckCard";
import { OpportunityForm } from "./OpportunityForm";
import { ReportButton } from "./ReportButton";
import { ScenarioCards } from "./ScenarioCards";
import { VerdictCard } from "./VerdictCard";

/**
 * Reconstrói o `OpportunityInput` a partir de uma análise salva no histórico.
 * Análises antigas (pré-migration) não terão `input_overrides` — esses
 * campos voltam como `null` (= comportamento padrão), o que é OK.
 */
function rowToInput(row: OpportunityAnalysisRow): OpportunityInput {
  const ov = row.input_overrides ?? {};
  return {
    buyer_type: row.buyer_type,
    target_net_roi_pct: row.target_net_roi_pct,
    renovation_level: row.renovation_level,
    bid_amount: row.bid_amount,
    other_costs: row.other_costs,
    iptu_arrears: row.iptu_arrears,
    condo_arrears: row.condo_arrears,
    itbi_pct_override: ov.itbi_pct_override ?? null,
    registration_pct_override: ov.registration_pct_override ?? null,
    auctioneer_fee_pct_override: ov.auctioneer_fee_pct_override ?? null,
    sale_price_override: ov.sale_price_override ?? null,
  };
}

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
      renovation_level: "basic",
      bid_amount: property.minimum_bid_first ?? 0,
      other_costs: otherCostsDefaultFor(property.occupancy_status),
      iptu_arrears: property.iptu_arrears ?? 0,
      condo_arrears: property.condo_arrears ?? 0,
    }),
    [property],
  );

  const [input, setInput] = useState<OpportunityInput>(initialInput);

  // Quando o usuário clica num item do histórico, guardamos o id para
  // marcar visualmente qual análise está sendo "espelhada" no formulário.
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(
    null,
  );

  /** Edição manual no formulário → desmarca a seleção. */
  const handleInputChange = useCallback((next: OpportunityInput) => {
    setInput(next);
    setSelectedHistoryId(null);
  }, []);

  /** Carrega os parâmetros de uma análise antiga no formulário. */
  const handleLoadFromHistory = useCallback((row: OpportunityAnalysisRow) => {
    setInput(rowToInput(row));
    setSelectedHistoryId(row.id);
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, []);

  /** Volta tudo aos defaults do imóvel (descarta a seleção). */
  const handleResetToDefaults = useCallback(() => {
    setInput(initialInput);
    setSelectedHistoryId(null);
  }, [initialInput]);

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
      setSavedHistory(
        updated.length
          ? updated
          : [
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
                input_overrides: {
                  itbi_pct_override: input.itbi_pct_override ?? null,
                  registration_pct_override:
                    input.registration_pct_override ?? null,
                  auctioneer_fee_pct_override:
                    input.auctioneer_fee_pct_override ?? null,
                  sale_price_override: input.sale_price_override ?? null,
                },
                created_at: new Date().toISOString(),
              },
            ],
      );
      // O registro recém-salvo passa a ser o "ativo" no histórico.
      setSelectedHistoryId(res.id);
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
        {selectedHistoryId && (
          <div className="flex items-center justify-between gap-2 rounded-md border border-primary/40 bg-primary/5 px-3 py-2 text-xs">
            <div className="flex items-center gap-1.5 text-primary">
              <History className="size-3.5" />
              <span>Editando análise do histórico</span>
            </div>
            <button
              type="button"
              onClick={handleResetToDefaults}
              className="inline-flex items-center gap-1 text-[11px] text-muted-foreground underline hover:text-primary"
              title="Voltar aos valores padrão deste imóvel"
            >
              <RotateCcw className="size-3" />
              padrão
            </button>
          </div>
        )}

        <OpportunityForm
          input={input}
          onChange={handleInputChange}
          property={property}
          assumptions={result.assumptions}
        />

        <Card>
          <CardContent className="space-y-3 pt-6">
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

            <ReportButton
              property={property}
              result={result}
              valuationId={valuation?.id ?? null}
              className="border-t pt-3"
            />
          </CardContent>
        </Card>
      </aside>

      <section className="space-y-6">
        <VerdictCard result={result} property={property} />

        <ScenarioCards result={result} />

        <LegalCheckCard property={property} />

        {savedHistory.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Histórico de análises ({savedHistory.length})
              </CardTitle>
              <p className="text-[11px] text-muted-foreground">
                Clique em uma análise para carregar seus parâmetros no
                formulário.
              </p>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {savedHistory.map((row) => {
                const isActive = row.id === selectedHistoryId;
                return (
                  <button
                    key={row.id}
                    type="button"
                    onClick={() => handleLoadFromHistory(row)}
                    aria-pressed={isActive}
                    className={`group flex w-full flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-left transition-colors ${
                      isActive
                        ? "border-primary bg-primary/5 ring-1 ring-primary/40"
                        : "border-border hover:border-primary/60 hover:bg-muted/50 cursor-pointer"
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="font-medium">
                        {new Date(row.created_at).toLocaleString("pt-BR")}
                        {isActive && (
                          <span className="ml-2 text-[10px] font-normal text-primary">
                            ativa
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {row.buyer_type} · ROI alvo{" "}
                        {Math.round(row.target_net_roi_pct * 100)}% · reforma{" "}
                        {row.renovation_level}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Lance {formatBRL(row.bid_amount)}
                      </div>
                    </div>
                    <Badge variant={verdictVariant(row.verdict)}>
                      {verdictLabel(row.verdict)}
                    </Badge>
                  </button>
                );
              })}
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
