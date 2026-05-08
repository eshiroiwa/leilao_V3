"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

type Status = "checking" | "online" | "offline";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function BackendStatus({
  className,
  intervalMs = 30000,
}: {
  className?: string;
  intervalMs?: number;
}) {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    async function ping() {
      try {
        const res = await fetch(`${API_BASE}/health`, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (cancelled) return;
        setStatus(res.ok ? "online" : "offline");
      } catch {
        if (!cancelled) setStatus("offline");
      }
    }

    ping();
    const id = window.setInterval(ping, intervalMs);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(id);
    };
  }, [intervalMs]);

  const dot =
    status === "online"
      ? "bg-success"
      : status === "offline"
        ? "bg-danger"
        : "bg-muted-foreground/50";

  const label =
    status === "online"
      ? "API conectada"
      : status === "offline"
        ? "API fora do ar"
        : "Verificando…";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border border-border/60 bg-card/40 px-2.5 py-1.5 text-xs text-muted-foreground",
        className,
      )}
      title={`${label} · ${API_BASE}`}
    >
      <span className="relative flex size-2">
        {status === "online" && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
        )}
        <span className={cn("relative inline-flex size-2 rounded-full", dot)} />
      </span>
      <span className="truncate">{label}</span>
    </div>
  );
}
