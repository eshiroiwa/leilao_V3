"use client";

import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarClock,
  ClipboardList,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";

import { PropertyImage } from "@/components/PropertyImage";
import { Badge } from "@/components/ui/badge";
import type {
  DashboardOpportunity,
  DashboardPropertySummary,
  Verdict,
} from "@/lib/api";
import { formatBRL, formatPct } from "@/lib/utils";

import type { DashboardFilter } from "./types";

const VERDICT_BADGE: Record<
  Verdict,
  { label: string; variant: "success" | "warning" | "danger" | "secondary" }
> = {
  BOA_OPORTUNIDADE: { label: "Boa oportunidade", variant: "success" },
  BOA_COM_RESSALVAS: { label: "Boa, com ressalvas", variant: "warning" },
  NEUTRO: { label: "Neutro", variant: "secondary" },
  INVIAVEL: { label: "Inviável", variant: "danger" },
  INDETERMINADO: { label: "Indeterminado", variant: "secondary" },
};

type SidebarPanelProps =
  | {
      filter: "good_opportunities";
      items: DashboardOpportunity[];
    }
  | {
      filter: Exclude<DashboardFilter, "good_opportunities">;
      items: DashboardPropertySummary[];
    };

const FILTER_META: Record<
  DashboardFilter,
  {
    title: string;
    subtitle: string;
    icon: typeof Sparkles;
    emptyMessage: string;
  }
> = {
  good_opportunities: {
    title: "Top oportunidades",
    subtitle: "Ranking",
    icon: Sparkles,
    emptyMessage:
      "Nenhuma análise rodada ainda. Abra um imóvel e dispare a análise de oportunidade para ver o ranking aqui.",
  },
  all: {
    title: "Imóveis cadastrados",
    subtitle: "Todos",
    icon: Building2,
    emptyMessage: "Nenhum imóvel cadastrado ainda.",
  },
  upcoming_30d: {
    title: "Leilões em 30 dias",
    subtitle: "Janela",
    icon: CalendarClock,
    emptyMessage: "Nenhum leilão agendado nos próximos 30 dias.",
  },
  pending_valuation: {
    title: "Sem avaliação",
    subtitle: "Pendentes",
    icon: ClipboardList,
    emptyMessage: "Todos os imóveis já têm avaliação.",
  },
  pending_opportunity: {
    title: "Sem análise de oportunidade",
    subtitle: "Pendentes",
    icon: AlertTriangle,
    emptyMessage: "Todos os imóveis já passaram pela análise.",
  },
};

export function SidebarPanel(props: SidebarPanelProps) {
  const meta = FILTER_META[props.filter];
  const Icon = meta.icon;

  return (
    <section className="flex h-fit flex-col rounded-2xl border bg-card p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="size-4 shrink-0 text-primary" />
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              {meta.subtitle}
            </p>
            <h3 className="truncate text-base font-semibold tracking-tight">
              {meta.title}
            </h3>
          </div>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">
          {props.items.length} item(ns)
        </span>
      </div>

      {props.items.length === 0 ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
          {meta.emptyMessage}
        </p>
      ) : (
        <ul className="max-h-[460px] space-y-2 overflow-y-auto pr-1">
          {props.filter === "good_opportunities"
            ? (props.items as DashboardOpportunity[]).map((it) => (
                <li key={it.opportunity_id}>
                  <OpportunityRow item={it} />
                </li>
              ))
            : (props.items as DashboardPropertySummary[]).map((it) => (
                <li key={it.property_id}>
                  <PropertyRow item={it} variant={props.filter} />
                </li>
              ))}
        </ul>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Linhas
// ---------------------------------------------------------------------------

function OpportunityRow({ item }: { item: DashboardOpportunity }) {
  const meta = VERDICT_BADGE[item.verdict] ?? VERDICT_BADGE.INDETERMINADO;
  const cityState = [item.city, item.state].filter(Boolean).join(" / ");
  const href =
    `/properties/${encodeURIComponent(item.property_id)}/opportunity` as Route;
  const positiveRoi =
    typeof item.net_roi_pct === "number" && item.net_roi_pct >= 0;

  return (
    <RowShell href={href} imageUrl={item.image_url} title={item.title}>
      <div className="flex items-start justify-between gap-2">
        <p className="line-clamp-1 text-sm font-medium leading-snug">
          {item.title ?? "Imóvel sem título"}
        </p>
        <Badge variant={meta.variant} className="shrink-0 text-[10px]">
          {meta.label}
        </Badge>
      </div>
      <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
        {cityState || "—"}
      </p>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <span
          className={`inline-flex items-center gap-1 text-xs font-semibold tabular-nums ${
            positiveRoi ? "text-success-700" : "text-danger-700"
          }`}
        >
          <TrendingUp className="size-3" />
          ROI {formatPct(item.net_roi_pct)}
        </span>
        <span className="text-[11px] text-muted-foreground tabular-nums">
          Lance {formatBRL(item.bid_amount)}
        </span>
        <ArrowRight className="size-3 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
    </RowShell>
  );
}

function PropertyRow({
  item,
  variant,
}: {
  item: DashboardPropertySummary;
  variant: Exclude<DashboardFilter, "good_opportunities">;
}) {
  const cityState = [item.city, item.state].filter(Boolean).join(" / ");

  // Destino padrão é a aba de avaliação (CMA); para "pendente de
  // oportunidade" faz mais sentido ir direto ao passo seguinte do pipeline.
  const path =
    variant === "pending_opportunity" ? "opportunity" : "valuation";
  const href =
    `/properties/${encodeURIComponent(item.property_id)}/${path}` as Route;

  const minBid = item.minimum_bid_first ?? item.minimum_bid_second;
  const minBidLabel =
    item.minimum_bid_first != null
      ? "Mín 1ª"
      : item.minimum_bid_second != null
        ? "Mín 2ª"
        : "—";

  let cta: ReactNode = null;
  if (variant === "pending_valuation")
    cta = (
      <span className="text-[10px] font-medium text-warning-700">Avaliar →</span>
    );
  else if (variant === "pending_opportunity")
    cta = (
      <span className="text-[10px] font-medium text-warning-700">
        Analisar →
      </span>
    );
  else if (variant === "upcoming_30d")
    cta = (
      <span className="text-[10px] font-medium text-info-700">Programado</span>
    );

  return (
    <RowShell href={href} imageUrl={item.image_url} title={item.title}>
      <div className="flex items-start justify-between gap-2">
        <p className="line-clamp-1 text-sm font-medium leading-snug">
          {item.title ?? "Imóvel sem título"}
        </p>
        {item.property_type && (
          <Badge
            variant="secondary"
            className="shrink-0 capitalize text-[10px]"
          >
            {item.property_type}
          </Badge>
        )}
      </div>
      <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
        {cityState || "—"}
      </p>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <span className="text-[11px] text-muted-foreground tabular-nums">
          {minBidLabel} {formatBRL(minBid)}
        </span>
        {cta}
        <ArrowRight className="size-3 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
    </RowShell>
  );
}

function RowShell({
  href,
  imageUrl,
  title,
  children,
}: {
  href: Route;
  imageUrl: string | null;
  title: string | null;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="group flex gap-3 rounded-xl border p-2 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-sm"
    >
      <div className="relative size-16 shrink-0 overflow-hidden rounded-lg">
        <PropertyImage
          src={imageUrl}
          alt={title ?? "Foto"}
          aspect=""
          iconSize="size-5"
          className="h-full w-full"
        />
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </Link>
  );
}
