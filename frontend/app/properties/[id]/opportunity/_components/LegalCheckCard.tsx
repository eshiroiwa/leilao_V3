"use client";

import { useEffect, useState } from "react";
import {
  AlertOctagon,
  CheckCircle2,
  ChevronRight,
  Gavel,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type LegalCheckResult, type Property } from "@/lib/api";
import {
  digitsOnly,
  maskCpfCnpj,
  validateCpfCnpj,
} from "@/lib/cpf-cnpj";
import { cn } from "@/lib/utils";

type LegalRow = LegalCheckResult & { id?: string | null };

export function LegalCheckCard({ property }: { property: Property }) {
  const [row, setRow] = useState<LegalRow | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // CPF/CNPJ a ser usado na verificação. Pré-preenche com o que o Scraper
  // extraiu (se houver); usuário pode sobrescrever a qualquer momento.
  const scrapedCpfCnpj = property.owner_cpf_cnpj ?? "";
  const [cpfCnpj, setCpfCnpj] = useState<string>(
    scrapedCpfCnpj ? maskCpfCnpj(scrapedCpfCnpj) : "",
  );

  // Carrega o último check ao montar.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .getLatestLegalCheck(property.id)
      .then((r) => {
        if (!cancelled) setRow(r);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message ?? e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [property.id]);

  const digits = digitsOnly(cpfCnpj);
  const validation = validateCpfCnpj(cpfCnpj);
  const isComplete =
    validation.kind === "cpf" || validation.kind === "cnpj";
  const dvValid = isComplete ? validation.dvValid : false;
  const isEmpty = validation.kind === "empty";
  const isManualOverride = digits !== digitsOnly(scrapedCpfCnpj);

  const runCheck = async (force = false) => {
    if (isEmpty) {
      setError("Informe o CPF ou CNPJ do proprietário antes de verificar.");
      return;
    }
    if (!isComplete) {
      setError(
        `Documento incompleto (${digits.length} dígito(s)). Esperado 11 (CPF) ou 14 (CNPJ).`,
      );
      return;
    }
    if (!dvValid && !force) {
      // Dígito verificador inválido — vamos pedir confirmação antes de
      // gastar uma chamada DataJud que vai retornar zero hits e dar
      // falsa sensação de "imóvel limpo".
      setError(
        "DV_INVALID",
      );
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const next = await api.runLegalCheck(property.id, {
        owner_cpf_cnpj: digits,
      });
      setRow(next);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Gavel className="size-4 text-muted-foreground" />
            Verificação jurídica
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={() => runCheck(false)}
            disabled={running || loading || isEmpty || !isComplete}
          >
            {running ? (
              <>
                <Loader2 className="mr-1.5 size-3 animate-spin" />
                Verificando…
              </>
            ) : row ? (
              "Reverificar"
            ) : (
              "Verificar"
            )}
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground">
          CNJ DataJud (processos contra o proprietário) + ONR (matrícula —
          stub, integração paga sob demanda).
        </p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {/* Input de CPF/CNPJ — editável, pré-preenchido com o que o
            Scraper extraiu (se algo). */}
        <div className="space-y-1.5 rounded-md border bg-muted/20 p-2.5">
          <div className="flex items-baseline justify-between gap-2">
            <Label htmlFor="legal_cpf" className="text-xs">
              CPF ou CNPJ do proprietário
            </Label>
            {scrapedCpfCnpj && (
              <span className="text-[10px] text-muted-foreground">
                {isManualOverride
                  ? "editado pelo usuário"
                  : "extraído do edital"}
              </span>
            )}
            {!scrapedCpfCnpj && (
              <span className="text-[10px] text-warning-700">
                não extraído — informe manualmente
              </span>
            )}
          </div>
          <Input
            id="legal_cpf"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            placeholder="000.000.000-00 ou 00.000.000/0000-00"
            value={cpfCnpj}
            onChange={(e) => {
              setCpfCnpj(maskCpfCnpj(e.target.value));
              // Limpa erro de DV quando o usuário corrige o número.
              if (error === "DV_INVALID") setError(null);
            }}
            className={cn(
              !isEmpty &&
                !isComplete &&
                "border-warning/60 focus-visible:ring-warning",
              isComplete &&
                !dvValid &&
                "border-danger/60 focus-visible:ring-danger",
            )}
          />
          <p
            className={cn(
              "text-[10px]",
              isComplete && !dvValid
                ? "text-danger-700"
                : "text-muted-foreground",
            )}
          >
            {isEmpty
              ? "Preencha para consultar processos no CNJ DataJud (TJ + TRT da UF)."
              : !isComplete
                ? `${digits.length} dígito(s) — esperado 11 (CPF) ou 14 (CNPJ).`
                : !dvValid
                  ? `Dígito verificador inválido — número provavelmente digitado errado. (${
                      validation.kind === "cpf" ? "CPF" : "CNPJ"
                    })`
                  : validation.kind === "cpf"
                    ? "CPF válido — consulta os tribunais da UF do imóvel."
                    : "CNPJ válido — consulta os tribunais da UF do imóvel."}
          </p>
        </div>

        {error === "DV_INVALID" ? (
          <div className="space-y-2 rounded-md border border-warning/40 bg-warning-50 p-2.5 text-xs text-warning-700">
            <div className="font-semibold">
              Dígito verificador não bate.
            </div>
            <div>
              Esse número {validation.kind === "cpf" ? "CPF" : "CNPJ"} muito
              provavelmente está digitado errado. Confira antes de prosseguir
              — uma consulta com documento inválido devolve zero processos e
              parece &quot;limpo&quot; sem ser.
            </div>
            <div className="pt-1">
              <button
                type="button"
                onClick={() => runCheck(true)}
                className="text-[11px] underline hover:text-warning-900"
              >
                Verificar mesmo assim →
              </button>
            </div>
          </div>
        ) : error ? (
          <div className="rounded-md border border-danger/30 bg-danger-50 p-2 text-xs text-danger-700">
            {error}
          </div>
        ) : null}

        {loading && !row && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" /> Carregando última
            verificação…
          </div>
        )}

        {!loading && !row && !error && (
          <p className="text-xs text-muted-foreground">
            Nenhuma verificação realizada para este imóvel.
            {isEmpty
              ? " Informe o CPF/CNPJ acima e clique em \"Verificar\"."
              : " Clique em \"Verificar\" para consultar o CNJ DataJud."}
          </p>
        )}

        {row && <LegalCheckBody row={row} />}
      </CardContent>
    </Card>
  );
}

// =============================================================================
function LegalCheckBody({ row }: { row: LegalRow }) {
  const owner = row.owner_processes;
  const matricula = row.matricula_check;

  const summary = (() => {
    if (row.has_critical_findings)
      return {
        Icon: AlertOctagon,
        label: "RED FLAG — risco jurídico relevante",
        tone: "danger" as const,
      };
    if (owner.status === "completed")
      return {
        Icon: ShieldCheck,
        label: "Sem processos críticos detectados no TJ da UF",
        tone: "success" as const,
      };
    return {
      Icon: ShieldQuestion,
      label: "Verificação parcial — leia detalhes",
      tone: "warning" as const,
    };
  })();

  const toneClass =
    summary.tone === "danger"
      ? "border-danger/30 bg-danger-50 text-danger-700"
      : summary.tone === "success"
        ? "border-success/30 bg-success-50 text-success-700"
        : "border-warning/30 bg-warning-50 text-warning-700";

  return (
    <div className="space-y-3">
      <div
        className={cn(
          "flex items-start gap-2 rounded-md border p-2.5 text-xs",
          toneClass,
        )}
      >
        <summary.Icon className="mt-0.5 size-4 shrink-0" />
        <div className="flex-1 space-y-1">
          <div className="font-semibold">{summary.label}</div>
          {row.critical_findings.map((f, i) => (
            <div key={i} className="text-[11px] leading-relaxed">
              {f}
            </div>
          ))}
        </div>
      </div>

      {/* Processos do proprietário (DataJud) */}
      <section className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Processos do proprietário (CNJ DataJud)
          </h4>
          <StatusBadge status={owner.status} />
        </div>

        {owner.status === "skipped" && (
          <p className="rounded-md border bg-muted/40 p-2 text-[11px] text-muted-foreground">
            {owner.skipped_reason}
          </p>
        )}
        {owner.status === "failed" && (
          <p className="rounded-md border border-danger/30 bg-danger-50 p-2 text-[11px] text-danger-700">
            {owner.skipped_reason}
          </p>
        )}
        {owner.status === "completed" && (
          <>
            <div className="grid grid-cols-3 gap-2">
              <Metric label="Total" value={owner.total_hits.toString()} />
              <Metric
                label="Críticos"
                value={owner.critical_hits.toString()}
                tone={owner.critical_hits > 0 ? "danger" : "success"}
              />
              <Metric
                label="Tribunais"
                value={
                  owner.tribunals_queried && owner.tribunals_queried.length > 0
                    ? owner.tribunals_queried.length.toString()
                    : "1"
                }
                sub={
                  owner.tribunals_queried && owner.tribunals_queried.length > 0
                    ? owner.tribunals_queried.map((t) => t.toUpperCase()).join(" · ")
                    : owner.tribunal?.toUpperCase()
                }
              />
            </div>

            {owner.tribunals_failed && owner.tribunals_failed.length > 0 && (
              <div className="rounded-md border border-warning/30 bg-warning-50 p-2 text-[11px] text-warning-700">
                ⚠ Falha na consulta de:{" "}
                <strong>
                  {owner.tribunals_failed.map((t) => t.toUpperCase()).join(", ")}
                </strong>
                . Resultado pode estar incompleto.
              </div>
            )}

            {owner.critical_labels.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {owner.critical_labels.map((lbl) => (
                  <Badge key={lbl} variant="danger" className="text-[10px]">
                    {lbl}
                  </Badge>
                ))}
              </div>
            )}

            {owner.sample_processes.length > 0 && (
              <details className="rounded-md border border-dashed text-xs">
                <summary className="cursor-pointer p-2 font-medium hover:bg-muted/40">
                  <ChevronRight className="mr-1 inline size-3" />
                  {owner.sample_processes.length} processo(s) detalhado(s)
                </summary>
                <ul className="divide-y">
                  {owner.sample_processes.map((p, i) => (
                    <li
                      key={i}
                      className="flex items-start justify-between gap-2 p-2"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          {p.is_critical && (
                            <AlertOctagon className="size-3 shrink-0 text-danger-700" />
                          )}
                          <span className="font-mono text-[11px]">
                            {p.numero_processo}
                          </span>
                          <Badge
                            variant={
                              p.tribunal.startsWith("trt")
                                ? "warning"
                                : "secondary"
                            }
                            className="text-[9px]"
                          >
                            {p.tribunal.toUpperCase()}
                          </Badge>
                        </div>
                        <div className="mt-0.5 text-[11px] text-muted-foreground">
                          {p.classe_nome ?? "Classe sem nome"}
                          {p.orgao_julgador && ` · ${p.orgao_julgador}`}
                        </div>
                      </div>
                      {p.data_ajuizamento && (
                        <span className="shrink-0 text-[10px] text-muted-foreground">
                          {new Date(p.data_ajuizamento).toLocaleDateString(
                            "pt-BR",
                          )}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>

      {/* Matrícula / ONR */}
      <section className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Matrícula (ONR)
          </h4>
          <StatusBadge status={matricula.status} />
        </div>

        {matricula.matricula ? (
          <div className="space-y-1 rounded-md border bg-muted/30 p-2 text-[11px]">
            <div>
              <span className="text-muted-foreground">Matrícula:</span>{" "}
              <strong className="font-mono">{matricula.matricula}</strong>
            </div>
            {matricula.registry_office && (
              <div>
                <span className="text-muted-foreground">Cartório:</span>{" "}
                {matricula.registry_office}
              </div>
            )}
            <div className="text-muted-foreground italic">
              {matricula.skipped_reason}
            </div>
          </div>
        ) : (
          <p className="rounded-md border bg-muted/40 p-2 text-[11px] text-muted-foreground">
            {matricula.skipped_reason ?? "Sem matrícula informada."}
          </p>
        )}
      </section>

      <div className="border-t pt-2 text-[10px] text-muted-foreground">
        Verificado em{" "}
        {row.completed_at
          ? new Date(row.completed_at).toLocaleString("pt-BR")
          : "—"}
        {row.duration_ms != null && ` · ${row.duration_ms}ms`}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "success" | "danger";
}) {
  return (
    <div className="rounded-md border bg-card/70 p-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 text-sm font-semibold tabular-nums",
          tone === "danger"
            ? "text-danger-700"
            : tone === "success"
              ? "text-success-700"
              : "text-foreground",
        )}
      >
        {value}
      </div>
      {sub && (
        <div className="mt-0.5 break-words text-[9px] uppercase tracking-wider text-muted-foreground">
          {sub}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: "completed" | "skipped" | "failed" }) {
  const map = {
    completed: {
      label: "concluído",
      variant: "success" as const,
      Icon: CheckCircle2,
    },
    skipped: {
      label: "pulado",
      variant: "secondary" as const,
      Icon: ShieldQuestion,
    },
    failed: {
      label: "falhou",
      variant: "danger" as const,
      Icon: ShieldAlert,
    },
  };
  const m = map[status];
  return (
    <Badge variant={m.variant} className="text-[10px]">
      <m.Icon className="mr-1 size-3" />
      {m.label}
    </Badge>
  );
}
