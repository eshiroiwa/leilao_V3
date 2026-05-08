"use client";

import { Eye, EyeOff, Search, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type PropertiesFilterBarProps = {
  query: string;
  onQueryChange: (q: string) => void;
  showExpired: boolean;
  onShowExpiredChange: (v: boolean) => void;
  /** Total bruto (antes do filtro). */
  totalCount: number;
  /** Total exibido após filtros. */
  visibleCount: number;
  /** Quantidade de leilões encerrados na lista bruta (para hint). */
  expiredCount: number;
};

export function PropertiesFilterBar({
  query,
  onQueryChange,
  showExpired,
  onShowExpiredChange,
  totalCount,
  visibleCount,
  expiredCount,
}: PropertiesFilterBarProps) {
  const filtered = visibleCount !== totalCount;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {/* Campo de busca (ocupa o espaço disponível) */}
        <div className="relative min-w-0 flex-1">
          <Search
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Buscar por cidade, bairro, tipo, endereço…"
            aria-label="Buscar imóvel"
            className="pl-9 pr-9"
          />
          {query && (
            <button
              type="button"
              onClick={() => onQueryChange("")}
              aria-label="Limpar busca"
              className="absolute right-2 top-1/2 inline-flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>

        {/* Toggle pill: encerrados */}
        <button
          type="button"
          onClick={() => onShowExpiredChange(!showExpired)}
          aria-pressed={showExpired}
          className={cn(
            "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
            showExpired
              ? "border-primary bg-primary-100 text-primary-700 hover:bg-primary-100/80"
              : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground",
          )}
          title={
            showExpired
              ? "Ocultar leilões encerrados"
              : "Mostrar leilões encerrados também"
          }
        >
          {showExpired ? (
            <Eye className="size-3.5" />
          ) : (
            <EyeOff className="size-3.5" />
          )}
          {showExpired ? "Mostrando encerrados" : "Ocultar encerrados"}
          {expiredCount > 0 && (
            <span
              className={cn(
                "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
                showExpired
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {expiredCount}
            </span>
          )}
        </button>
      </div>

      {/* Resumo abaixo da barra */}
      <p className="text-xs text-muted-foreground">
        {filtered
          ? `${visibleCount} de ${totalCount} imóveis`
          : `${totalCount} imóveis`}
        {!showExpired && expiredCount > 0 && (
          <>
            {" · "}
            <span>{expiredCount} encerrado(s) ocultos</span>
          </>
        )}
      </p>
    </div>
  );
}
