"use client";

import {
  AlertCircle,
  Loader2,
  RefreshCcw,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, type DeepAnalysisRow } from "@/lib/api";
import { useDeepAnalysis } from "@/lib/use-deep-analysis";

import { DeepAnalysisCard } from "./DeepAnalysisCard";

const STATUS_LABEL: Record<string, string> = {
  pending: "Na fila…",
  running: "Coletando dados externos (Firecrawl + Google Maps + LLM)…",
  completed: "Concluída",
  failed: "Falhou",
};

export function DeepAnalysisSection({
  propertyId,
  opportunityAnalysisId,
  initialLatest,
  latitude,
  longitude,
}: {
  propertyId: string;
  opportunityAnalysisId?: string | null;
  /** Última análise concluída do banco (cache). Pode ser null. */
  initialLatest: DeepAnalysisRow | null;
  /** Coordenadas do imóvel — usadas para abrir Maps/Street View nos thumbs. */
  latitude: number | null;
  longitude: number | null;
}) {
  const [history, setHistory] = useState<DeepAnalysisRow[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(
    initialLatest?.id ?? null,
  );
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const polling = useDeepAnalysis(initialLatest);

  const loadHistory = useCallback(async () => {
    try {
      const list = await api.listDeepAnalyses(propertyId);
      setHistory(list);
    } catch {
      // não bloqueia o fluxo
    } finally {
      setHistoryLoaded(true);
    }
  }, [propertyId]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  // Quando uma análise sai de "running" → recarrega histórico para refletir.
  useEffect(() => {
    if (polling.status === "completed" || polling.status === "failed") {
      void loadHistory();
    }
  }, [polling.status, loadHistory]);

  const handleStart = useCallback(
    async (force: boolean) => {
      setStarting(true);
      setStartError(null);
      try {
        const res = await api.startDeepAnalysis(propertyId, {
          opportunity_analysis_id: opportunityAnalysisId ?? null,
          force_refresh: force,
        });

        if (res.from_cache && res.row) {
          // Cache hit — mostra direto a análise cacheada.
          polling.startPolling(res.row);
          setSelectedId(res.row.id);
        } else {
          // Cache miss — começa a polling no novo id.
          const row: DeepAnalysisRow = {
            id: res.id,
            property_id: propertyId,
            status: res.status,
            created_at: new Date().toISOString(),
          };
          polling.startPolling(row);
          setSelectedId(res.id);
        }
        void loadHistory();
      } catch (err) {
        setStartError(err instanceof Error ? err.message : String(err));
      } finally {
        setStarting(false);
      }
    },
    [propertyId, opportunityAnalysisId, polling, loadHistory],
  );

  const handleSelectFromHistory = useCallback(
    (row: DeepAnalysisRow) => {
      polling.startPolling(row);
      setSelectedId(row.id);
    },
    [polling],
  );

  const showCard =
    polling.row &&
    (polling.row.status === "completed" ||
      polling.row.status === "failed" ||
      polling.row.status === "running" ||
      polling.row.status === "pending");

  const isTerminal =
    polling.status === "completed" || polling.status === "failed";

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">
              Análise aprofundada do bairro
            </CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Demografia · liquidez · outlier · flipping · tendência ·
              amenidades · riscos urbanos · histórico de leilão
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {!polling.row && (
              <Button
                onClick={() => handleStart(false)}
                disabled={starting || polling.loading}
                size="sm"
              >
                {starting ? (
                  <>
                    <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                    iniciando…
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-1.5 size-3.5" />
                    Análise profunda
                  </>
                )}
              </Button>
            )}

            {polling.row && isTerminal && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleStart(true)}
                disabled={starting || polling.loading}
                title="Ignorar cache de 7 dias e recalcular"
              >
                <RefreshCcw className="mr-1.5 size-3.5" />
                Atualizar
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        {/* Estado de progresso */}
        {polling.loading && polling.status && (
          <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-xs">
            <Loader2 className="size-3.5 animate-spin text-primary" />
            <span>
              <strong>{STATUS_LABEL[polling.status]}</strong>
              <br />
              <span className="text-muted-foreground">
                Processo dura entre 30 e 60 segundos. Você pode sair desta
                página — os dados serão persistidos.
              </span>
            </span>
          </div>
        )}

        {/* Erro */}
        {(polling.error || startError) && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
            <AlertCircle className="size-3.5 shrink-0" />
            <span>{polling.error || startError}</span>
          </div>
        )}

        {/* Resultado */}
        {showCard && polling.row && polling.status === "completed" && (
          <DeepAnalysisCard
            row={polling.row}
            latitude={latitude}
            longitude={longitude}
          />
        )}

        {/* Histórico (se houver mais de 1 análise) */}
        {historyLoaded && history.length > 0 && (
          <details
            className="rounded-md border border-dashed p-3 text-xs"
            open={history.length > 1}
          >
            <summary className="cursor-pointer font-medium text-foreground">
              Histórico de análises profundas ({history.length})
            </summary>
            <ul className="mt-2 space-y-1.5">
              {history.map((row) => {
                const isActive = row.id === selectedId;
                return (
                  <li key={row.id}>
                    <button
                      type="button"
                      onClick={() => handleSelectFromHistory(row)}
                      aria-pressed={isActive}
                      className={`flex w-full items-center justify-between gap-2 rounded-md border p-2 text-left transition-colors ${
                        isActive
                          ? "border-primary bg-primary/5"
                          : "border-border hover:bg-muted/50"
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="font-medium">
                          {new Date(row.created_at).toLocaleString("pt-BR")}
                        </div>
                        <div className="text-[10px] text-muted-foreground">
                          status: {row.status}
                          {row.overall_score != null && (
                            <> · score {row.overall_score}/5</>
                          )}
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
