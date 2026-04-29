"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api, type ValuationSummary } from "@/lib/api";

export function ValuationActions({ propertyId }: { propertyId: string }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ValuationSummary | null>(null);

  function handleRun() {
    setError(null);
    startTransition(async () => {
      try {
        const res = await api.valuateProperty(propertyId);
        setLastResult(res);
        // Refresca o server component para puxar a nova valuation.
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    });
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <Button onClick={handleRun} disabled={isPending}>
        {isPending ? (
          <>
            <Loader2 className="mr-2 size-4 animate-spin" />
            Avaliando…
          </>
        ) : (
          <>
            <RefreshCw className="mr-2 size-4" />
            Disparar avaliação
          </>
        )}
      </Button>
      {error && (
        <p className="max-w-sm text-right text-xs text-destructive">{error}</p>
      )}
      {lastResult && (
        <p className="text-xs text-muted-foreground">
          Última: {lastResult.confidence} · {lastResult.comparables_used}{" "}
          comparáveis · ~ R$ {lastResult.cost_estimate_brl.toFixed(2)}
        </p>
      )}
    </div>
  );
}
