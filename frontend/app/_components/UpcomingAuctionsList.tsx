import { ArrowRight, CalendarClock, MapPin } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";

import { PropertyImage } from "@/components/PropertyImage";
import { Badge } from "@/components/ui/badge";
import type { DashboardCalendarEvent } from "@/lib/api";
import { formatBRL } from "@/lib/utils";

function countdown(iso: string, nowIso: string): string {
  const target = new Date(iso);
  if (Number.isNaN(target.getTime())) return "—";
  const now = new Date(nowIso);
  const ms = target.getTime() - now.getTime();
  const days = Math.round(ms / (1000 * 60 * 60 * 24));
  if (days < 0) return "vencido";
  if (days === 0) return "hoje";
  if (days === 1) return "amanhã";
  return `em ${days} dia${days === 1 ? "" : "s"}`;
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
  });
}

export function UpcomingAuctionsList({
  items,
  nowIso,
}: {
  items: DashboardCalendarEvent[];
  nowIso: string;
}) {
  if (items.length === 0) {
    return (
      <section className="rounded-2xl border bg-card p-5">
        <div className="mb-2 flex items-center gap-2">
          <CalendarClock className="size-4 text-primary" />
          <h3 className="text-base font-semibold tracking-tight">
            Próximos leilões
          </h3>
        </div>
        <p className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
          Nenhum leilão agendado no horizonte. Confira a aba de imóveis ou rode
          um novo scrape.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border bg-card p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CalendarClock className="size-4 text-primary" />
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Cronograma
            </p>
            <h3 className="text-base font-semibold tracking-tight">
              Próximos leilões
            </h3>
          </div>
        </div>
        <span className="text-xs text-muted-foreground">
          {items.length} item(ns)
        </span>
      </div>

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {items.map((e, i) => {
          const cityState = [e.city, e.state].filter(Boolean).join(" / ");
          const href =
            `/properties/${encodeURIComponent(e.property_id)}/valuation` as Route;
          return (
            <li key={`${e.property_id}-${e.kind}-${i}`}>
              <Link
                href={href}
                className="group flex h-full flex-col gap-2 rounded-xl border bg-card p-3 transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-sm"
              >
                <div className="flex items-center gap-2">
                  <div className="relative size-12 shrink-0 overflow-hidden rounded-lg">
                    <PropertyImage
                      src={e.image_url}
                      alt={e.title ?? "Foto"}
                      aspect=""
                      iconSize="size-4"
                      className="h-full w-full"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-1 text-xs font-semibold">
                      {countdown(e.date, nowIso)}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {shortDate(e.date)}
                    </p>
                  </div>
                  <Badge
                    variant={e.kind === "first" ? "default" : "warning"}
                    className="shrink-0 text-[10px]"
                  >
                    {e.kind === "first" ? "1ª" : "2ª"}
                  </Badge>
                </div>
                <p className="line-clamp-2 text-[11px] leading-snug">
                  {e.title ?? "Imóvel sem título"}
                </p>
                {cityState && (
                  <p className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                    <MapPin className="size-3" /> {cityState}
                  </p>
                )}
                <div className="mt-auto flex items-baseline justify-between border-t pt-1.5">
                  <span className="text-[10px] text-muted-foreground">
                    Mín
                  </span>
                  <span className="inline-flex items-center gap-1 text-xs font-semibold tabular-nums text-primary-700">
                    {formatBRL(e.value)}
                    <ArrowRight className="size-3 opacity-0 transition-opacity group-hover:opacity-100" />
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
