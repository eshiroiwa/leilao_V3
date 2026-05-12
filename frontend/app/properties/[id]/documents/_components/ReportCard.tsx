"use client";

import { AlertTriangle, CheckCircle2, FileWarning, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DOC_TYPE_LABELS,
  type DocumentAnalysisRow,
  type LegalRisk,
  type LegalRiskSeverity,
} from "@/lib/api";
import { formatBRL, formatDateTimeBR } from "@/lib/utils";

const SEVERITY_ORDER: Record<LegalRiskSeverity, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

const SEVERITY_VARIANT: Record<
  LegalRiskSeverity,
  "destructive" | "danger" | "warning" | "secondary"
> = {
  CRITICAL: "destructive",
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "secondary",
};

const CATEGORY_LABEL: Record<string, string> = {
  onus: "Ônus",
  processo_ativo: "Processo ativo",
  irregularidade_registral: "Irregularidade registral",
  vicio_edital: "Vício de edital",
  ocupacao: "Ocupação",
  tributario: "Tributário",
  outro: "Outro",
};

const LIEN_LABEL: Record<string, string> = {
  hipoteca: "Hipoteca",
  penhora: "Penhora",
  usufruto: "Usufruto",
  alienacao_fiduciaria: "Alienação fiduciária",
  servidao: "Servidão",
  indisponibilidade: "Indisponibilidade",
  outro: "Outro",
};

export function ReportCard({
  analysis,
}: {
  analysis: DocumentAnalysisRow | null;
}) {
  if (!analysis) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Análise consolidada</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          <Sparkles className="mb-2 size-5 text-muted-foreground" />
          Selecione um ou mais documentos e clique em{" "}
          <strong>Analisar selecionados</strong> para gerar um relatório
          consolidado (ônus, riscos e recomendações).
        </CardContent>
      </Card>
    );
  }

  const report = analysis.report;
  const sortedRisks = [...report.risks].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <CardTitle className="text-base">Análise consolidada</CardTitle>
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
            confiança {report.confidence.toLowerCase()}
          </Badge>
          {report.critical_findings && (
            <Badge variant="destructive" className="text-[10px]">
              <AlertTriangle className="mr-1 size-3" />
              críticos detectados
            </Badge>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground">
          {formatDateTimeBR(analysis.created_at ?? report.extracted_at)} ·{" "}
          {report.model || "—"} · custo estimado{" "}
          {report.cost_usd > 0
            ? `US$ ${report.cost_usd.toFixed(2)}`
            : "—"}
        </p>
      </CardHeader>

      <CardContent className="space-y-4 text-sm">
        {report.documents_analyzed.length > 0 && (
          <Section title="Documentos analisados">
            <ul className="space-y-1 text-xs">
              {report.documents_analyzed.map((d) => (
                <li key={d.document_id} className="flex items-baseline gap-2">
                  <Badge variant="outline" className="text-[10px]">
                    {DOC_TYPE_LABELS[d.doc_type] ?? d.doc_type}
                  </Badge>
                  <span className="text-muted-foreground">{d.label}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {report.critical_findings_summary.length > 0 && (
          <Section title="Pontos críticos">
            <ul className="space-y-1 text-xs">
              {report.critical_findings_summary.map((s, i) => (
                <li
                  key={i}
                  className="rounded border border-destructive/40 bg-destructive/5 px-2 py-1"
                >
                  {s}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {report.liens.length > 0 && (
          <Section title={`Ônus encontrados (${report.liens.length})`}>
            <ul className="space-y-1 text-xs">
              {report.liens.map((l, i) => (
                <li
                  key={i}
                  className="rounded border border-danger/30 bg-danger-50 px-2 py-1"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <strong>{LIEN_LABEL[l.tipo] ?? l.tipo}</strong>
                    {l.valor_brl != null && (
                      <span className="text-[10px] text-muted-foreground">
                        {formatBRL(l.valor_brl)}
                      </span>
                    )}
                  </div>
                  {l.credor && (
                    <div className="text-muted-foreground">{l.credor}</div>
                  )}
                  {l.data_registro && (
                    <div className="text-[10px] text-muted-foreground">
                      Data: {l.data_registro}
                    </div>
                  )}
                  {l.notes && (
                    <p className="mt-0.5 text-[10px] italic text-muted-foreground">
                      {l.notes}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {sortedRisks.length > 0 && (
          <Section title={`Riscos (${sortedRisks.length})`}>
            <ul className="space-y-1 text-xs">
              {sortedRisks.map((r, i) => (
                <RiskRow key={i} risk={r} />
              ))}
            </ul>
          </Section>
        )}

        {report.recommendations.length > 0 && (
          <Section title="Recomendações">
            <ul className="space-y-1 text-xs">
              {report.recommendations.map((r, i) => (
                <li key={i} className="flex items-baseline gap-2">
                  <CheckCircle2 className="size-3 shrink-0 text-success-700" />
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {report.notes && (
          <p className="rounded-md border border-muted bg-muted/40 p-2 text-[11px] italic text-muted-foreground">
            <FileWarning className="mr-1 inline size-3" />
            {report.notes}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      {children}
    </div>
  );
}

function RiskRow({ risk }: { risk: LegalRisk }) {
  const variant = SEVERITY_VARIANT[risk.severity];
  return (
    <li className="rounded border bg-background px-2 py-1">
      <div className="flex flex-wrap items-baseline gap-1">
        <Badge variant={variant} className="text-[10px]">
          {risk.severity}
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {CATEGORY_LABEL[risk.category] ?? risk.category}
        </Badge>
      </div>
      <p className="mt-1 text-xs">{risk.description}</p>
    </li>
  );
}
