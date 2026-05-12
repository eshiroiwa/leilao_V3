"use client";

import { AlertTriangle, ArrowRight, FolderOpen, Sparkles } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  DocumentAnalysisRow,
  PropertyDocument,
} from "@/lib/api";
import { formatDateTimeBR } from "@/lib/utils";

export function DocumentsSummaryCard({
  propertyId,
  documents,
  latestAnalysis,
}: {
  propertyId: string;
  documents: PropertyDocument[];
  latestAnalysis: DocumentAnalysisRow | null;
}) {
  const href = `/properties/${encodeURIComponent(propertyId)}/documents` as Route;
  const report = latestAnalysis?.report ?? null;

  return (
    <Card className={latestAnalysis?.has_critical_findings ? "border-danger/40" : ""}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <FolderOpen className="size-4" />
          Documentos
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-xs text-muted-foreground">
          {documents.length === 0
            ? "Nenhum documento anexado a este imóvel."
            : `${documents.length} documento(s) anexado(s).`}
        </p>

        {report && (
          <div className="space-y-1.5 rounded-md border bg-muted/30 p-2">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <Sparkles className="size-3.5 text-primary" />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Última análise
              </span>
              <Badge
                variant={
                  report.confidence === "HIGH"
                    ? "success"
                    : report.confidence === "MEDIUM"
                      ? "secondary"
                      : "warning"
                }
                className="text-[10px]"
              >
                {report.confidence.toLowerCase()}
              </Badge>
              {report.critical_findings && (
                <Badge variant="destructive" className="text-[10px]">
                  <AlertTriangle className="mr-0.5 size-3" />
                  críticos
                </Badge>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {formatDateTimeBR(
                latestAnalysis?.created_at ?? report.extracted_at,
              )}{" "}
              · {report.liens.length} ônus · {report.risks.length} risco(s)
            </p>
          </div>
        )}

        <Link
          href={href}
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          Gerenciar documentos
          <ArrowRight className="size-3" />
        </Link>
      </CardContent>
    </Card>
  );
}
