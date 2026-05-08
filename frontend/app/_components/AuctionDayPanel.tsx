"use client";

import { ArrowRight, MapPin } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";

import { PropertyImage } from "@/components/PropertyImage";
import { Badge } from "@/components/ui/badge";
import type { DashboardCalendarEvent } from "@/lib/api";
import { cn, formatBRL } from "@/lib/utils";

export function AuctionDayPanel({
  date,
  events,
  nowIso,
}: {
  /** YYYY-MM-DD */
  date: string;
  events: DashboardCalendarEvent[];
  /** ISO timestamp do servidor — usado para identificar leilões já encerrados. */
  nowIso: string;
}) {
  const dt = new Date(`${date}T12:00:00`);
  const human = dt.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  });

  return (
    <section
      aria-label={`Leilões em ${human}`}
      className="rounded-2xl border bg-card p-4 sm:p-5"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Leilões selecionados
          </p>
          <h3 className="text-base font-semibold capitalize tracking-tight">
            {human}
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">
          {events.length} item(ns)
        </span>
      </div>

      {events.length === 0 ? (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          Nenhum leilão neste dia.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {events.map((e, i) => (
            <li key={`${e.property_id}-${e.kind}-${i}`}>
              <AuctionEventCard event={e} nowIso={nowIso} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function AuctionEventCard({
  event,
  nowIso,
}: {
  event: DashboardCalendarEvent;
  nowIso: string;
}) {
  const cityState = [event.city, event.state].filter(Boolean).join(" / ");
  const href =
    `/properties/${encodeURIComponent(event.property_id)}/valuation` as Route;

  // Considera "encerrado" se a data do leilão ficou no passado em
  // relação ao timestamp gerado no servidor (determinístico e
  // safe pra hidratação).
  const isPast = new Date(event.date).getTime() < new Date(nowIso).getTime();

  return (
    <Link
      href={href}
      aria-label={
        isPast
          ? `${event.title ?? "Imóvel"} (leilão encerrado)`
          : event.title ?? undefined
      }
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-xl border bg-card transition-all hover:-translate-y-0.5 hover:shadow-md",
        isPast
          ? "border-border opacity-70 saturate-50 hover:border-border hover:opacity-90 hover:saturate-100"
          : "hover:border-primary/40",
      )}
    >
      <div className="relative">
        <PropertyImage
          src={event.image_url}
          alt={event.title ?? "Foto do imóvel"}
          aspect="aspect-[16/9]"
          className={cn(
            "[&_img]:transition-all [&_img]:duration-500 group-hover:[&_img]:scale-[1.04]",
            isPast && "[&_img]:grayscale group-hover:[&_img]:grayscale-0",
          )}
        />
        <div className="absolute left-2 top-2 flex gap-1">
          <Badge
            variant={
              isPast ? "secondary" : event.kind === "first" ? "default" : "warning"
            }
            className="backdrop-blur-sm"
          >
            {event.kind === "first" ? "1ª praça" : "2ª praça"}
          </Badge>
          {isPast && (
            <Badge
              variant="secondary"
              className="bg-muted/90 text-muted-foreground backdrop-blur-sm"
            >
              Encerrado
            </Badge>
          )}
        </div>
        {event.property_type && (
          <div className="absolute right-2 top-2">
            <Badge
              variant="secondary"
              className="bg-card/85 capitalize backdrop-blur-sm"
            >
              {event.property_type}
            </Badge>
          </div>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <h4
          className={cn(
            "line-clamp-2 text-sm font-semibold leading-snug",
            isPast && "text-muted-foreground",
          )}
        >
          {event.title ?? "Imóvel sem título"}
        </h4>
        {cityState && (
          <p className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <MapPin className="size-3" />
            {cityState}
          </p>
        )}
        <div className="mt-auto flex items-baseline justify-between pt-1.5">
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Valor mínimo
          </span>
          <span
            className={cn(
              "text-sm font-semibold tabular-nums",
              isPast ? "text-muted-foreground" : "text-primary-700",
            )}
          >
            {formatBRL(event.value)}
          </span>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 text-[11px] font-medium opacity-0 transition-opacity group-hover:opacity-100",
            isPast ? "text-muted-foreground" : "text-primary-700",
          )}
        >
          Abrir avaliação <ArrowRight className="size-3" />
        </span>
      </div>
    </Link>
  );
}
