import { ArrowRight, BarChart3, Brain, Sparkles } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  api,
  type DeepAnalysisRow,
  type OpportunityAnalysisRow,
  type Valuation,
} from "@/lib/api";
import { formatBRL, formatDateTimeBR, formatPct } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function PropertyOverviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [valuations, opportunities, latestDeep] = await Promise.all([
    api.listValuations(id).catch(() => [] as Valuation[]),
    api.listOpportunities(id).catch(() => [] as OpportunityAnalysisRow[]),
    api
      .getLatestDeepAnalysis(id)
      .catch(() => null as DeepAnalysisRow | null),
  ]);

  const latestVal = valuations[0] ?? null;
  const latestOpp = opportunities[0] ?? null;
  const base = `/properties/${encodeURIComponent(id)}`;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <SummaryCard
        title="Avaliação de mercado (CMA)"
        description="Estima preço a partir de comparáveis de portais imobiliários."
        icon={BarChart3}
        tone="info"
        href={`${base}/valuation` as Route}
        cta={latestVal ? "Abrir avaliação" : "Rodar avaliação"}
        empty={!latestVal}
        emptyMessage="Nenhuma avaliação ainda. Esta é a base para os cenários de oportunidade."
      >
        {latestVal && (
          <div className="space-y-1.5 text-sm">
            <Row
              label="Preço estimado"
              value={formatBRL(latestVal.estimated_price)}
              strong
            />
            <Row
              label="Intervalo P10–P90"
              value={
                latestVal.price_lower_bound != null &&
                latestVal.price_upper_bound != null
                  ? `${formatBRL(latestVal.price_lower_bound)} – ${formatBRL(
                      latestVal.price_upper_bound,
                    )}`
                  : "—"
              }
            />
            <Row
              label="Comparáveis"
              value={`${latestVal.comparables_used} usado(s)`}
            />
            <Row label="Confiança" value={latestVal.confidence ?? "—"} />
            <Row
              label="Calculada em"
              value={formatDateTimeBR(latestVal.created_at)}
              muted
            />
          </div>
        )}
      </SummaryCard>

      <SummaryCard
        title="Análise de oportunidade"
        description="Custos, ROI e veredicto financeiro do lance."
        icon={Sparkles}
        tone="primary"
        href={`${base}/opportunity` as Route}
        cta={latestOpp ? "Abrir análise" : "Configurar análise"}
        empty={!latestOpp}
        emptyMessage="Defina o lance e veja se o investimento bate o ROI alvo."
      >
        {latestOpp && (
          <div className="space-y-1.5 text-sm">
            <Row
              label="Veredicto"
              value={formatVerdictLabel(latestOpp.verdict)}
              strong
            />
            <Row
              label="ROI realista"
              value={formatPct(latestOpp.scenarios.realista.net_roi_pct)}
            />
            <Row
              label="Lucro realista"
              value={formatBRL(latestOpp.scenarios.realista.net_profit)}
            />
            <Row
              label="Lance analisado"
              value={formatBRL(latestOpp.bid_amount)}
            />
            <Row
              label="Calculada em"
              value={formatDateTimeBR(latestOpp.created_at)}
              muted
            />
          </div>
        )}
      </SummaryCard>

      <SummaryCard
        title="Análise profunda"
        description="Liquidez, outliers, tendência, riscos urbanos."
        icon={Brain}
        tone="success"
        href={`${base}/opportunity` as Route}
        cta={latestDeep ? "Ver análise profunda" : "Disparar análise profunda"}
        empty={!latestDeep || latestDeep.status !== "completed"}
        emptyMessage="Pesquisa na web para enriquecer o parecer com contexto local."
      >
        {latestDeep && latestDeep.status === "completed" && (
          <div className="space-y-1.5 text-sm">
            <Row
              label="Score geral"
              value={
                latestDeep.overall_score != null
                  ? `${latestDeep.overall_score}/5`
                  : "—"
              }
              strong
            />
            <Row
              label="Liquidez"
              value={
                latestDeep.liquidity_score != null
                  ? `${latestDeep.liquidity_score}/5`
                  : "—"
              }
            />
            <Row
              label="Flipping"
              value={
                latestDeep.flipping_potential_score != null
                  ? `${latestDeep.flipping_potential_score}/5`
                  : "—"
              }
            />
            <Row
              label="Outlier"
              value={
                latestDeep.is_outlier_size || latestDeep.is_outlier_price
                  ? "atípico"
                  : "típico"
              }
            />
            <Row
              label="Concluída em"
              value={formatDateTimeBR(latestDeep.completed_at)}
              muted
            />
          </div>
        )}
      </SummaryCard>
    </div>
  );
}

const TONE_STYLES = {
  info: { bar: "bg-info", chip: "bg-info-100 text-info-700" },
  primary: { bar: "bg-primary", chip: "bg-primary-100 text-primary-700" },
  success: { bar: "bg-success", chip: "bg-success-100 text-success-700" },
} as const;

type Tone = keyof typeof TONE_STYLES;

function SummaryCard({
  title,
  description,
  icon: Icon,
  tone,
  href,
  cta,
  empty,
  emptyMessage,
  children,
}: {
  title: string;
  description: string;
  icon: typeof BarChart3;
  tone: Tone;
  href: Route;
  cta: string;
  empty?: boolean;
  emptyMessage?: string;
  children?: React.ReactNode;
}) {
  const style = TONE_STYLES[tone];

  return (
    <Card className="relative flex h-full flex-col overflow-hidden">
      <span aria-hidden className={`absolute inset-x-0 top-0 h-1 ${style.bar}`} />
      <CardHeader className="pb-3">
        <div className="flex items-start gap-3">
          <span
            className={`inline-flex size-9 shrink-0 items-center justify-center rounded-lg ${style.chip}`}
          >
            <Icon className="size-4" />
          </span>
          <div>
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription className="mt-0.5 text-xs">
              {description}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        {empty ? (
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          children
        )}
        <div className="mt-auto pt-4">
          <Button asChild variant={empty ? "outline" : "default"} className="w-full">
            <Link href={href}>
              {cta} <ArrowRight className="size-4" />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  strong,
  muted,
}: {
  label: string;
  value: string;
  strong?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={[
          "tabular-nums",
          strong ? "text-sm font-semibold text-foreground" : "text-foreground",
          muted ? "text-muted-foreground" : "",
        ].join(" ")}
      >
        {value}
      </span>
    </div>
  );
}

function formatVerdictLabel(v: string | null | undefined): string {
  if (!v) return "—";
  return (
    {
      BOA_OPORTUNIDADE: "Boa oportunidade",
      BOA_COM_RESSALVAS: "Boa, com ressalvas",
      NEUTRO: "Neutro",
      INVIAVEL: "Inviável",
      INDETERMINADO: "Indeterminado",
    }[v] ?? v
  );
}
