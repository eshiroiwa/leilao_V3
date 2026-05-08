"use client";

import { FileDown, Loader2 } from "lucide-react";
import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  api,
  type DeepAnalysisRow,
  type OpportunityResult,
  type Property,
  type ValuationDetail,
} from "@/lib/api";
import { generateReportHtml } from "@/lib/report-html";
import { reportFilename } from "@/lib/report-slug";

export function ReportButton({
  property,
  result,
  valuationId,
  className,
}: {
  property: Property;
  /** OpportunityResult ATUAL (já no painel — preview do AGENT 3). */
  result: OpportunityResult;
  /** Valuation mais recente (ou null se não houver CMA). */
  valuationId: string | null;
  className?: string;
}) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = useCallback(async () => {
    setWorking(true);
    setError(null);
    try {
      // Carrega comparables + deep analysis em paralelo.
      // Falhas não-fatais: se algum desses cair, o relatório ainda sai
      // (sem mapa ou sem análise profunda).
      const [valuationDetail, latestDeep] = await Promise.all([
        valuationId
          ? api
              .getValuationDetail(property.id, valuationId)
              .catch(() => null as ValuationDetail | null)
          : Promise.resolve(null as ValuationDetail | null),
        api
          .getLatestDeepAnalysis(property.id)
          .catch(() => null as DeepAnalysisRow | null),
      ]);

      const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

      const html = generateReportHtml({
        property,
        opportunity: result,
        valuation: valuationDetail,
        deepAnalysis: latestDeep,
        apiKey,
      });

      const filename = reportFilename({
        property_type: property.property_type,
        state: property.state,
        city: property.city,
        neighborhood: property.neighborhood,
        street: property.street,
      });

      // Trigger download via Blob → não toca server-side, fica offline.
      const blob = new Blob([html], { type: "text/html;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Solta o objeto depois de um beat — alguns browsers cancelam
      // download se revogarem a URL antes do clique propagar.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorking(false);
    }
  }, [property, result, valuationId]);

  return (
    <div className={className}>
      <Button
        type="button"
        variant="outline"
        className="w-full"
        onClick={handleClick}
        disabled={working}
      >
        {working ? (
          <>
            <Loader2 className="mr-1.5 size-3.5 animate-spin" />
            Gerando…
          </>
        ) : (
          <>
            <FileDown className="mr-1.5 size-3.5" />
            Gerar relatório (HTML)
          </>
        )}
      </Button>
      {error && (
        <p className="mt-1.5 text-xs text-destructive">{error}</p>
      )}
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        Inclui foto, dados, cenários, mapa interativo e análise profunda
        (se disponível).
      </p>
    </div>
  );
}
