import { ArrowRight, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";

import { PropertyImage } from "@/components/PropertyImage";
import { Badge } from "@/components/ui/badge";
import type { DashboardOpportunity, Verdict } from "@/lib/api";
import { formatBRL, formatPct } from "@/lib/utils";

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

export function TopOpportunitiesList({
  items,
}: {
  items: DashboardOpportunity[];
}) {
  if (items.length === 0) {
    return (
      <section className="rounded-2xl border bg-card p-5">
        <div className="mb-2 flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          <h3 className="text-base font-semibold tracking-tight">
            Top oportunidades
          </h3>
        </div>
        <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
          Nenhuma análise rodada ainda. Abra um imóvel e dispare a análise de
          oportunidade para ver o ranking aqui.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border bg-card p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Ranking
            </p>
            <h3 className="text-base font-semibold tracking-tight">
              Top oportunidades
            </h3>
          </div>
        </div>
        <span className="text-xs text-muted-foreground">
          {items.length} item(ns)
        </span>
      </div>

      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.opportunity_id}>
            <OpportunityRow item={it} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function OpportunityRow({ item }: { item: DashboardOpportunity }) {
  const meta = VERDICT_BADGE[item.verdict] ?? VERDICT_BADGE.INDETERMINADO;
  const cityState = [item.city, item.state].filter(Boolean).join(" / ");
  const href =
    `/properties/${encodeURIComponent(item.property_id)}/opportunity` as Route;
  const positiveRoi =
    typeof item.net_roi_pct === "number" && item.net_roi_pct >= 0;

  return (
    <Link
      href={href}
      className="group flex gap-3 rounded-xl border p-2 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-sm"
    >
      <div className="relative size-16 shrink-0 overflow-hidden rounded-lg">
        <PropertyImage
          src={item.image_url}
          alt={item.title ?? "Foto"}
          aspect=""
          iconSize="size-5"
          className="h-full w-full"
        />
      </div>
      <div className="min-w-0 flex-1">
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
      </div>
    </Link>
  );
}
