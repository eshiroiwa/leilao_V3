"use client";

import { FileDown, Loader2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  api,
  type DeepAnalysisRow,
  type LegalCheckResult,
  type OpportunityAnalysisRow,
  type OpportunityInput,
  type OpportunityResult,
  type OpportunityScenario,
  type Property,
  type Verdict,
  type ValuationDetail,
} from "@/lib/api";
import {
  generateReportHtml,
  type ScenarioLabel,
} from "@/lib/report-html";
import { reportFilename } from "@/lib/report-slug";
import { formatBRL } from "@/lib/utils";

const PAYMENT_LABEL: Record<string, string> = {
  cash: "à vista",
  financed_bank: "financiado",
  installments_judicial: "parcelado (judicial)",
};

const SCENARIO_LABELS: { value: ScenarioLabel; label: string }[] = [
  { value: "pessimista", label: "Pessimista" },
  { value: "realista", label: "Realista" },
  { value: "otimista", label: "Otimista" },
];

/** Reconstrói um `OpportunityResult` a partir de uma row salva do histórico,
 * suficiente para gerar a seção do relatório (3 cenários + assumptions +
 * verdict). Como o save persiste tudo que importa, é fiel ao snapshot. */
function rowToResult(row: OpportunityAnalysisRow): OpportunityResult {
  const ov = row.input_overrides ?? {};
  const pt = row.payment_terms ?? {};
  const input: OpportunityInput = {
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
    payment_mode: pt.payment_mode ?? "cash",
    down_payment_pct: pt.down_payment_pct ?? null,
    loan_months: pt.loan_months ?? null,
    loan_rate_annual_pct: pt.loan_rate_annual_pct ?? null,
    installments_count: pt.installments_count ?? null,
    installments_index: pt.installments_index ?? null,
  };
  return {
    input,
    pessimista: row.scenarios.pessimista,
    realista: row.scenarios.realista,
    otimista: row.scenarios.otimista,
    max_bid_for_target: row.max_bid_for_target,
    verdict: row.verdict,
    verdict_base: row.verdict_base ?? row.verdict,
    verdict_factors: row.verdict_factors ?? [],
    warnings: row.warnings ?? [],
    assumptions: row.assumptions,
  };
}

/** Rótulo curto para identificar análise no diálogo. */
function analysisLabel(row: OpportunityAnalysisRow): string {
  const mode = row.payment_terms?.payment_mode ?? "cash";
  const modeLabel = PAYMENT_LABEL[mode] ?? mode;
  const date = new Date(row.created_at).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
  });
  return `${date} · ${modeLabel} · lance ${formatBRL(row.bid_amount)}`;
}

function currentAnalysisLabel(result: OpportunityResult): string {
  const mode = result.input.payment_mode ?? "cash";
  const modeLabel = PAYMENT_LABEL[mode] ?? mode;
  return `Atual (não salva) · ${modeLabel} · lance ${formatBRL(result.input.bid_amount)}`;
}

const CURRENT_KEY = "__current__";

export function ReportButton({
  property,
  result,
  valuationId,
  history,
  className,
}: {
  property: Property;
  /** OpportunityResult ATUAL (em edição no painel). */
  result: OpportunityResult;
  /** Valuation mais recente (ou null se não houver CMA). */
  valuationId: string | null;
  /** Histórico de análises salvas — alimenta a lista de seleção. */
  history?: OpportunityAnalysisRow[];
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const historyList = history ?? [];

  // Seleções: por default, marca a análise ATUAL e todos os 3 cenários.
  const [selectedAnalyses, setSelectedAnalyses] = useState<Set<string>>(
    () => new Set([CURRENT_KEY]),
  );
  const [selectedScenarios, setSelectedScenarios] = useState<
    Set<ScenarioLabel>
  >(() => new Set(["pessimista", "realista", "otimista"]));

  const totalSelected = selectedAnalyses.size;
  const canGenerate =
    !working &&
    selectedScenarios.size > 0 &&
    totalSelected > 0;

  const toggleAnalysis = (key: string) => {
    setSelectedAnalyses((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleScenario = (label: ScenarioLabel) => {
    setSelectedScenarios((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const orderedAnalyses = useMemo(() => {
    const items: { key: string; label: string; row: OpportunityResult }[] = [
      { key: CURRENT_KEY, label: currentAnalysisLabel(result), row: result },
    ];
    for (const h of historyList) {
      items.push({
        key: h.id,
        label: analysisLabel(h),
        row: rowToResult(h),
      });
    }
    return items;
  }, [result, historyList]);

  const handleGenerate = useCallback(async () => {
    setWorking(true);
    setError(null);
    try {
      const [valuationDetail, latestDeep, latestLegal] = await Promise.all([
        valuationId
          ? api
              .getValuationDetail(property.id, valuationId)
              .catch(() => null as ValuationDetail | null)
          : Promise.resolve(null as ValuationDetail | null),
        api
          .getLatestDeepAnalysis(property.id)
          .catch(() => null as DeepAnalysisRow | null),
        api
          .getLatestLegalCheck(property.id)
          .catch(
            () =>
              null as (LegalCheckResult & { id?: string | null }) | null,
          ),
      ]);

      const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

      const chosenAnalyses = orderedAnalyses
        .filter((a) => selectedAnalyses.has(a.key))
        .map((a) => ({ result: a.row, label: a.label }));

      const html = generateReportHtml({
        property,
        analyses: chosenAnalyses,
        valuation: valuationDetail,
        deepAnalysis: latestDeep,
        legalCheck: latestLegal,
        apiKey,
        selectedScenarios: Array.from(selectedScenarios),
      });

      const filename = reportFilename({
        property_type: property.property_type,
        state: property.state,
        city: property.city,
        neighborhood: property.neighborhood,
        street: property.street,
      });

      const blob = new Blob([html], { type: "text/html;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorking(false);
    }
  }, [
    property,
    valuationId,
    orderedAnalyses,
    selectedAnalyses,
    selectedScenarios,
  ]);

  return (
    <div className={className}>
      <Button
        type="button"
        variant="outline"
        className="w-full"
        onClick={() => setOpen(true)}
      >
        <FileDown className="mr-1.5 size-3.5" />
        Gerar relatório (HTML)
      </Button>
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        Inclui foto, dados, cenários, mapa interativo e análise profunda
        (se disponível).
      </p>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Personalizar relatório</DialogTitle>
            <DialogDescription>
              Escolha quais análises e cenários incluir. O relatório fica em
              uma única página HTML offline.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Análises ({orderedAnalyses.length})
              </div>
              <ul className="max-h-56 space-y-1 overflow-auto rounded-md border p-2">
                {orderedAnalyses.map((a) => (
                  <li key={a.key}>
                    <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted">
                      <input
                        type="checkbox"
                        checked={selectedAnalyses.has(a.key)}
                        onChange={() => toggleAnalysis(a.key)}
                        className="size-3.5 cursor-pointer"
                      />
                      <span className="flex-1">
                        {a.label}
                        <VerdictBadge verdict={a.row.verdict} />
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Cenários internos (por análise)
              </div>
              <div className="flex flex-wrap gap-1.5">
                {SCENARIO_LABELS.map((s) => {
                  const active = selectedScenarios.has(s.value);
                  return (
                    <button
                      key={s.value}
                      type="button"
                      onClick={() => toggleScenario(s.value)}
                      className={`rounded-md border px-2 py-1 text-[11px] transition-colors ${
                        active
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border hover:bg-muted"
                      }`}
                    >
                      {s.label}
                    </button>
                  );
                })}
              </div>
              {selectedScenarios.size === 0 && (
                <p className="mt-1 text-[11px] text-destructive">
                  Selecione ao menos um cenário.
                </p>
              )}
            </div>
          </div>

          {error && (
            <p className="text-xs text-destructive">{error}</p>
          )}

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={working}>
                Cancelar
              </Button>
            </DialogClose>
            <Button
              type="button"
              onClick={handleGenerate}
              disabled={!canGenerate}
            >
              {working ? (
                <>
                  <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                  Gerando…
                </>
              ) : (
                <>
                  <FileDown className="mr-1.5 size-3.5" />
                  Gerar ({totalSelected})
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

const VERDICT_COLOR: Record<Verdict, string> = {
  BOA_OPORTUNIDADE: "bg-success-100 text-success-700",
  BOA_COM_RESSALVAS: "bg-warning-100 text-warning-700",
  NEUTRO: "bg-muted text-muted-foreground",
  INVIAVEL: "bg-danger-100 text-danger-700",
  INDETERMINADO: "bg-muted text-muted-foreground",
};
const VERDICT_SHORT: Record<Verdict, string> = {
  BOA_OPORTUNIDADE: "Boa",
  BOA_COM_RESSALVAS: "Ressalvas",
  NEUTRO: "Neutro",
  INVIAVEL: "Inviável",
  INDETERMINADO: "—",
};

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`ml-2 inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium ${VERDICT_COLOR[verdict]}`}
    >
      {VERDICT_SHORT[verdict]}
    </span>
  );
}

// Suprime variável referenciada só para tipos no compilador.
void ([] as OpportunityScenario[]);
