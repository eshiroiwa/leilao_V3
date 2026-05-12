"use client";

import { ExternalLink, Globe, Info } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { WebFinding } from "@/lib/api";

export function WebFindingsCard({
  findings,
}: {
  findings: WebFinding[];
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe className="size-4" />
          Achados na web ({findings.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {findings.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Nenhum achado relevante na web para os termos pesquisados
            (anulatória, embargos à arrematação). Pode significar que o
            proprietário não tem litígios públicos indexados — confira
            também o DataJud.
          </p>
        ) : (
          <>
            <div className="flex items-start gap-1.5 rounded-md border border-warning/30 bg-warning-50 p-2 text-[11px] text-warning-700">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              <span>
                Achados na web podem incluir homônimos. Confirme manualmente
                clicando no link.
              </span>
            </div>
            <ul className="space-y-1.5">
              {findings.map((f) => (
                <li
                  key={f.url}
                  className="rounded-md border bg-card p-2 text-xs"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <a
                      href={f.url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-1 truncate font-medium text-primary hover:underline"
                    >
                      <ExternalLink className="size-3 shrink-0" />
                      <span className="truncate">{f.title}</span>
                    </a>
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                        f.score >= 0.6
                          ? "bg-danger-100 text-danger-700"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      score {f.score.toFixed(2)}
                    </span>
                  </div>
                  {f.snippet && (
                    <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">
                      {f.snippet}
                    </p>
                  )}
                  <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                    query: {f.query}
                  </p>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
