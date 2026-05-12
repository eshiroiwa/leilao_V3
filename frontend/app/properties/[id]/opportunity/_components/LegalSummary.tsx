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
  type LegalCheckResult,
  type Property,
} from "@/lib/api";
import { maskCpfCnpj } from "@/lib/cpf-cnpj";

type LegalCheckRow = LegalCheckResult & { id?: string | null };

/** Sumário compacto da análise jurídica — substitui o antigo `LegalCheckCard`
 * dentro do `OpportunityView`. Linka para a aba "Jurídico" completa.
 */
export function LegalSummary({ property }: { property: Property }) {
  const [check, setCheck] = useState<LegalCheckRow | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getLatestLegalCheck(property.id)
      .then((row) => {
        if (!cancelled) setCheck(row);
      })
      .catch(() => {
        if (!cancelled) setCheck(null);
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
  const ocr = check?.matricula_ocr ?? null;
  const liens = ocr?.liens ?? [];

  return (
    <Card className={check?.has_critical_findings ? "border-danger/40" : ""}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Gavel className="size-4" />
          Análise jurídica
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {loading ? (
          <p className="text-xs text-muted-foreground">Carregando…</p>
        ) : !check ? (
          <p className="text-xs text-muted-foreground">
            Nenhuma análise executada ainda.
          </p>
        ) : (
          <div className="space-y-1.5">
            {check.owner_processes?.cpf_cnpj && (
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
              label="Matrícula"
              value={
                ocr
                  ? ocr.is_clear
                    ? "Livre de ônus"
                    : `${liens.length} ônus`
                  : "Não enviada"
              }
              danger={liens.length > 0}
            />
            {check.web_findings && check.web_findings.length > 0 && (
              <Row
                label="Web"
                value={`${check.web_findings.length} achado(s)`}
                danger={check.web_findings.some((f) => f.score >= 0.6)}
              />
            )}

            {check.has_critical_findings && (
              <div className="flex items-start gap-1.5 rounded-md border border-danger/40 bg-danger-50 p-2 text-[11px] text-danger-700">
                <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                <span>
                  {check.critical_findings[0] ?? "Achados críticos detectados."}
                  {check.critical_findings.length > 1 &&
                    ` (+${check.critical_findings.length - 1})`}
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
