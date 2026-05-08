"use client";

import { AlertTriangle, CheckCircle2, MinusCircle, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { OpportunityResult, Property, Verdict } from "@/lib/api";
import { formatBRL, formatPct } from "@/lib/utils";

const VERDICT_META: Record<
  Verdict,
  {
    label: string;
    description: string;
    badge: "success" | "warning" | "destructive" | "secondary";
    Icon: typeof CheckCircle2;
    accent: string;
  }
> = {
  BOA_OPORTUNIDADE: {
    label: "Boa oportunidade",
    description:
      "ROI líquido projetado acima de 40%. Sinais financeiros são fortes.",
    badge: "success",
    Icon: CheckCircle2,
    accent: "text-emerald-600 dark:text-emerald-400",
  },
  // (Para ROI ≥ 50%, esse parecer é "intocável" — nenhum warning rebaixa.)
  BOA_COM_RESSALVAS: {
    label: "Boa, com ressalvas",
    description:
      "Retorno é razoável (entre 20% e 40%) mas há pontos de atenção. Leia os warnings.",
    badge: "warning",
    Icon: AlertTriangle,
    accent: "text-amber-600 dark:text-amber-400",
  },
  NEUTRO: {
    label: "Neutro",
    description:
      "Retorno modesto (entre 5% e 20%). Possível, mas não há margem para imprevistos.",
    badge: "secondary",
    Icon: MinusCircle,
    accent: "text-muted-foreground",
  },
  INVIAVEL: {
    label: "Inviável",
    description:
      "ROI muito baixo ou negativo. Reduzir o lance ou descartar a oportunidade.",
    badge: "destructive",
    Icon: XCircle,
    accent: "text-destructive",
  },
  INDETERMINADO: {
    label: "Indeterminado",
    description: "Faltam dados para uma conclusão clara.",
    badge: "secondary",
    Icon: MinusCircle,
    accent: "text-muted-foreground",
  },
};

export function VerdictCard({
  result,
  property,
}: {
  result: OpportunityResult;
  property: Property;
}) {
  const meta = VERDICT_META[result.verdict];
  const { Icon } = meta;

  const targetRoi = result.input.target_net_roi_pct;
  const realistaRoi = result.realista.net_roi_pct;
  const reaches = realistaRoi >= targetRoi;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <Icon className={`size-7 ${meta.accent}`} />
            <div>
              <CardTitle className="text-xl">{meta.label}</CardTitle>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {meta.description}
              </p>
            </div>
          </div>
          <Badge variant={meta.badge} className="text-sm">
            {meta.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <KPI
            label="ROI líquido (realista)"
            value={formatPct(realistaRoi)}
            accent={meta.accent}
          />
          <KPI
            label="Lucro líquido (realista)"
            value={formatBRL(result.realista.net_profit)}
            accent={
              result.realista.net_profit >= 0
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-destructive"
            }
          />
          <KPI
            label={`Lance máximo p/ ROI ${Math.round(targetRoi * 100)}%`}
            value={
              result.max_bid_for_target != null
                ? formatBRL(result.max_bid_for_target)
                : "Inalcançável"
            }
            sub={
              result.max_bid_for_target != null
                ? `Lance atual: ${formatBRL(result.input.bid_amount)} (${
                    result.input.bid_amount <=
                    (result.max_bid_for_target ?? Infinity)
                      ? "abaixo do teto"
                      : "ACIMA do teto"
                  })`
                : "Aumente o preço de venda esperado ou reduza custos."
            }
            accent={
              result.max_bid_for_target == null
                ? "text-destructive"
                : result.input.bid_amount <= result.max_bid_for_target
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-amber-600 dark:text-amber-400"
            }
          />
        </div>

        <div className="rounded-md border bg-muted/30 p-3 text-xs">
          <p>
            Cenário <strong>realista</strong>{" "}
            {reaches
              ? "atinge o ROI alvo. ✅"
              : "NÃO atinge o ROI alvo — considere baixar o lance."}{" "}
            ·{" "}
            <span className="text-muted-foreground">
              {property.city}/{property.state}
            </span>
          </p>
        </div>

        {/* Transparência: por que este verdict foi escolhido */}
        <VerdictExplanation result={result} />
        

        {result.warnings.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Pontos de atenção ({result.warnings.length})
            </h4>
            <ul className="space-y-1.5">
              {result.warnings.map((w, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-900 dark:text-amber-200"
                >
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function VerdictExplanation({ result }: { result: OpportunityResult }) {
  const { verdict, verdict_base, verdict_factors } = result;

  // Quando o verdict final == base e não há fatores, não há nada a explicar.
  const wasDowngraded = verdict !== verdict_base;
  const hasFactors = verdict_factors && verdict_factors.length > 0;
  if (!wasDowngraded && !hasFactors) return null;

  return (
    <details className="rounded-md border border-dashed p-3 text-xs">
      <summary className="cursor-pointer font-medium text-foreground">
        Por que este parecer?
      </summary>
      <div className="mt-2 space-y-2 text-muted-foreground">
        <p>
          ROI realista de{" "}
          <strong className="text-foreground">
            {(result.realista.net_roi_pct * 100).toFixed(1)}%
          </strong>{" "}
          enquadra a oportunidade como{" "}
          <strong className="text-foreground">
            {VERDICT_META[verdict_base].label}
          </strong>
          .
        </p>
        {hasFactors && (
          <div>
            <p>Fatores que rebaixaram o parecer:</p>
            <ul className="ml-4 mt-1 list-disc space-y-0.5">
              {verdict_factors.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
        )}
        {wasDowngraded ? (
          <p>
            Resultado final:{" "}
            <strong className="text-foreground">
              {VERDICT_META[verdict].label}
            </strong>
            . O ROI realista impede que o parecer caia abaixo deste nível —
            mesmo com os fatores acima, sua margem de retorno protege a
            oportunidade.
          </p>
        ) : (
          <p>
            Os fatores acima foram absorvidos pelo ROI realista — o parecer{" "}
            <strong className="text-foreground">
              {VERDICT_META[verdict].label}
            </strong>{" "}
            permanece.
          </p>
        )}
      </div>
    </details>
  );
}

function KPI({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className={`mt-1 text-xl font-semibold ${accent ?? ""}`}>
        {value}
      </div>
      {sub && (
        <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>
      )}
    </div>
  );
}
