"use client";

import { AlertTriangle, ArrowRight, Gavel } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";
import { useEffect, useState } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  api,
  type DocumentAnalysisRow,
  type LegalCheckResult,
  type Property,
} from "@/lib/api";
import { maskCpfCnpj } from "@/lib/cpf-cnpj";

type LegalCheckRow = LegalCheckResult & { id?: string | null };

/** Sumário compacto da análise jurídica — substitui o antigo `LegalCheckCard`
 * dentro do `OpportunityView`. Prioriza o relatório consolidado novo
 * (`document_analyses`) e cai para o `legal_checks.matricula_ocr` legado
 * quando não há análise consolidada.
 */
export function LegalSummary({ property }: { property: Property }) {
  const [check, setCheck] = useState<LegalCheckRow | null>(null);
  const [analysis, setAnalysis] = useState<DocumentAnalysisRow | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.getLatestLegalCheck(property.id).catch(() => null),
      api.getLatestDocumentAnalysis(property.id).catch(() => null),
    ])
      .then(([row, analysisRow]) => {
        if (cancelled) return;
        setCheck(row);
        setAnalysis(analysisRow);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [property.id]);

  const detailsHref =
    `/properties/${encodeURIComponent(property.id)}/legal` as Route;
  const total = check?.owner_processes?.total_hits ?? 0;
  const critical = check?.owner_processes?.critical_hits ?? 0;

  // Prioriza relatório consolidado novo; cai para matricula_ocr legado.
  const report = analysis?.report ?? null;
  const liensCount = report
    ? report.liens.length
    : (check?.matricula_ocr?.liens?.length ?? 0);
  const hasMatriculaData =
    !!report ||
    (check?.matricula_ocr && (check.matricula_ocr.owner_name || liensCount > 0));
  const showCritical =
    report?.critical_findings || check?.has_critical_findings;
  const criticalText = report
    ? report.critical_findings_summary[0]
    : check?.critical_findings?.[0];
  const extraCritical = report
    ? Math.max(report.critical_findings_summary.length - 1, 0)
    : Math.max((check?.critical_findings?.length ?? 0) - 1, 0);

  return (
    <Card className={showCritical ? "border-danger/40" : ""}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Gavel className="size-4" />
          Análise jurídica
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {loading ? (
          <p className="text-xs text-muted-foreground">Carregando…</p>
        ) : !check && !analysis ? (
          <p className="text-xs text-muted-foreground">
            Nenhuma análise executada ainda.
          </p>
        ) : (
          <div className="space-y-1.5">
            {check?.owner_processes?.cpf_cnpj && (
              <Row
                label="Proprietário (doc.)"
                value={maskCpfCnpj(check.owner_processes.cpf_cnpj)}
              />
            )}
            <Row
              label="Processos"
              value={`${total} total · ${critical} crítico(s)`}
              danger={critical > 0}
            />
            <Row
              label="Documentos"
              value={
                report
                  ? `${report.documents_analyzed.length} analisado(s) · ${liensCount} ônus`
                  : hasMatriculaData
                    ? `${liensCount} ônus`
                    : "Sem análise"
              }
              danger={liensCount > 0}
            />
            {check?.web_findings && check.web_findings.length > 0 && (
              <Row
                label="Web"
                value={`${check.web_findings.length} achado(s)`}
                danger={check.web_findings.some((f) => f.score >= 0.6)}
              />
            )}

            {showCritical && (
              <div className="flex items-start gap-1.5 rounded-md border border-danger/40 bg-danger-50 p-2 text-[11px] text-danger-700">
                <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                <span>
                  {criticalText ?? "Achados críticos detectados."}
                  {extraCritical > 0 && ` (+${extraCritical})`}
                </span>
              </div>
            )}
          </div>
        )}

        <Link
          href={detailsHref}
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          Ver detalhes na aba Jurídico
          <ArrowRight className="size-3" />
        </Link>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={danger ? "font-medium text-danger-700" : "text-foreground"}
      >
        {value}
      </span>
    </div>
  );
}
