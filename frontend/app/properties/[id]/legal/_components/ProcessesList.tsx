"use client";

import { AlertTriangle, ExternalLink, Gavel } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  LegalCheckResult,
  LegalProcessSummary,
  ProcessCategory,
} from "@/lib/api";

type LegalCheckRow = LegalCheckResult & { id?: string | null };

const CATEGORY_META: Record<
  ProcessCategory,
  { label: string; tone: "danger" | "warning" | "secondary" | "success" }
> = {
  anulatoria: { label: "Anulatória", tone: "danger" },
  embargos_arrematacao: { label: "Embargos", tone: "danger" },
  execucao_fiscal: { label: "Exec. Fiscal", tone: "warning" },
  cumprimento_sentenca: { label: "Cumprimento", tone: "warning" },
  execucao_titulo: { label: "Exec. Título", tone: "warning" },
  penhora: { label: "Penhora", tone: "warning" },
  despejo: { label: "Despejo", tone: "warning" },
  busca_apreensao: { label: "Busca/Apreensão", tone: "warning" },
  trabalhista: { label: "Trabalhista", tone: "warning" },
  outro: { label: "Outro", tone: "secondary" },
};

type FilterKey = "all" | "criticos" | ProcessCategory;

const FILTER_TABS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "criticos", label: "Críticos" },
  { key: "anulatoria", label: "Anulatórias" },
  { key: "embargos_arrematacao", label: "Embargos" },
  { key: "trabalhista", label: "Trabalhistas" },
  { key: "outro", label: "Outros" },
];

export function ProcessesList({
  check,
}: {
  check: LegalCheckRow | null;
}) {
  const [filter, setFilter] = useState<FilterKey>("all");

  const all: LegalProcessSummary[] = useMemo(() => {
    if (!check) return [];
    return (
      check.owner_processes?.processes_full ??
      check.owner_processes?.sample_processes ??
      []
    );
  }, [check]);

  const filtered = useMemo(() => {
    if (filter === "all") return all;
    if (filter === "criticos") return all.filter((p) => p.is_critical);
    if (filter === "outro") {
      return all.filter((p) => (p.category ?? "outro") === "outro");
    }
    return all.filter((p) => p.category === filter);
  }, [all, filter]);

  const status = check?.owner_processes?.status;
  const criticalCount = all.filter((p) => p.is_critical).length;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-baseline justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Gavel className="size-4" />
            Processos do proprietário
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {all.length} total · {criticalCount} crítico(s)
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!check && (
          <p className="text-xs text-muted-foreground">
            Execute a análise jurídica para listar processos.
          </p>
        )}

        {check && status === "skipped" && (
          <div className="rounded-md border border-warning/30 bg-warning-50 p-2 text-xs text-warning-700">
            {check.owner_processes?.skipped_reason ?? "Consulta pulada."}
          </div>
        )}
        {check && status === "failed" && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
            DataJud falhou: {check.owner_processes?.skipped_reason ?? "—"}
          </div>
        )}

        {all.length > 0 && (
          <>
            <div className="flex flex-wrap gap-1">
              {FILTER_TABS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setFilter(f.key)}
                  className={`rounded-md border px-2 py-0.5 text-[11px] transition-colors ${
                    filter === f.key
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-muted"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <ul className="space-y-1.5">
              {filtered.map((p, i) => {
                const cat = (p.category ?? "outro") as ProcessCategory;
                const meta = CATEGORY_META[cat] ?? CATEGORY_META.outro;
                const critical = p.is_critical;
                return (
                  <li
                    key={`${p.numero_processo}-${i}`}
                    className={`rounded-md border p-2 text-xs ${
                      critical
                        ? "border-danger/40 bg-danger-50"
                        : "border-border bg-card"
                    }`}
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        {critical && (
                          <AlertTriangle className="size-3 shrink-0 text-danger-700" />
                        )}
                        <code className="font-mono text-[11px]">
                          {p.numero_processo || "—"}
                        </code>
                      </div>
                      <Badge variant={meta.tone} className="text-[10px]">
                        {meta.label}
                      </Badge>
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 text-[10px] text-muted-foreground">
                      {p.classe_nome && <span>{p.classe_nome}</span>}
                      {p.tribunal && (
                        <span className="uppercase">{p.tribunal}</span>
                      )}
                      {p.orgao_julgador && <span>{p.orgao_julgador}</span>}
                      {p.data_ajuizamento && (
                        <span>{p.data_ajuizamento.slice(0, 10)}</span>
                      )}
                    </div>
                  </li>
                );
              })}
              {filtered.length === 0 && (
                <li className="rounded-md border border-dashed p-2 text-center text-[11px] text-muted-foreground">
                  Nenhum processo nessa categoria.
                </li>
              )}
            </ul>
          </>
        )}

        {check?.owner_processes?.tribunals_queried &&
          check.owner_processes.tribunals_queried.length > 0 && (
            <p className="text-[10px] text-muted-foreground">
              Tribunais consultados:{" "}
              {check.owner_processes.tribunals_queried
                .map((t) => t.toUpperCase())
                .join(" · ")}
              {check.owner_processes.tribunals_failed &&
                check.owner_processes.tribunals_failed.length > 0 && (
                  <>
                    {" · "}
                    falharam:{" "}
                    {check.owner_processes.tribunals_failed
                      .map((t) => t.toUpperCase())
                      .join(", ")}
                  </>
                )}
            </p>
          )}

        {check?.owner_processes?.cpf_cnpj && (
          <a
            href={`https://www.cnj.jus.br/sgt/consulta_publica_classes.php`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-primary"
          >
            <ExternalLink className="size-2.5" />
            Tabela CNJ de classes processuais
          </a>
        )}
      </CardContent>
    </Card>
  );
}
