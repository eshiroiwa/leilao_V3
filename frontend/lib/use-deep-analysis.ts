"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, type DeepAnalysisRow, type DeepAnalysisStatus } from "@/lib/api";

const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS = 6 * 60 * 1_000; // 6 minutos — bem além dos 30-60s esperados.

type State = {
  row: DeepAnalysisRow | null;
  status: DeepAnalysisStatus | null;
  loading: boolean; // true enquanto pendente/rodando
  error: string | null;
};

/**
 * Faz polling em ``GET /deep-analyses/{id}`` até o status virar
 * `completed` ou `failed`. Pára automaticamente em desmontagem ou
 * quando o estado terminal é alcançado.
 */
export function useDeepAnalysis(initial: DeepAnalysisRow | null) {
  const [state, setState] = useState<State>(() => ({
    row: initial,
    status: initial?.status ?? null,
    loading:
      initial?.status === "pending" || initial?.status === "running",
    error: null,
  }));

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingId = useRef<string | null>(null);
  const stoppedAtRef = useRef<number>(0);

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pollingId.current = null;
  }, []);

  /** Inicia (ou reinicia) o polling a partir de uma row. */
  const startPolling = useCallback(
    (row: DeepAnalysisRow) => {
      stopPolling();
      pollingId.current = row.id;
      stoppedAtRef.current = Date.now() + POLL_TIMEOUT_MS;

      setState({
        row,
        status: row.status,
        loading: row.status === "pending" || row.status === "running",
        error: null,
      });

      if (row.status === "completed" || row.status === "failed") {
        return;
      }

      const tick = async () => {
        const id = pollingId.current;
        if (!id) return;
        if (Date.now() > stoppedAtRef.current) {
          setState((s) => ({
            ...s,
            loading: false,
            error: "Tempo limite excedido (6 min). Tente novamente.",
          }));
          stopPolling();
          return;
        }
        try {
          const fresh = await api.getDeepAnalysis(id);
          if (pollingId.current !== id) return;
          const terminal =
            fresh.status === "completed" || fresh.status === "failed";
          setState({
            row: fresh,
            status: fresh.status,
            loading: !terminal,
            error:
              fresh.status === "failed"
                ? fresh.error_message ?? "Falha desconhecida no pipeline."
                : null,
          });
          if (!terminal) {
            timerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
          }
        } catch (err) {
          if (pollingId.current !== id) return;
          setState((s) => ({
            ...s,
            loading: false,
            error: err instanceof Error ? err.message : String(err),
          }));
        }
      };

      timerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
    },
    [stopPolling],
  );

  /** Trigger manual de re-fetch imediato. */
  const refresh = useCallback(async () => {
    if (!state.row) return;
    try {
      const fresh = await api.getDeepAnalysis(state.row.id);
      setState({
        row: fresh,
        status: fresh.status,
        loading: fresh.status === "pending" || fresh.status === "running",
        error: null,
      });
    } catch (err) {
      setState((s) => ({
        ...s,
        error: err instanceof Error ? err.message : String(err),
      }));
    }
  }, [state.row]);

  // Cleanup
  useEffect(() => stopPolling, [stopPolling]);

  // Bootstrap: se entramos com row em execução, começa polling.
  useEffect(() => {
    if (
      initial &&
      (initial.status === "pending" || initial.status === "running")
    ) {
      startPolling(initial);
    }
    // só rodamos no mount, ignoramos updates posteriores de `initial`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ...state, startPolling, refresh, stopPolling };
}
