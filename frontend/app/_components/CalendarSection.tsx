"use client";

import { useMemo, useState } from "react";

import type { DashboardCalendarEvent } from "@/lib/api";

import { AuctionDayPanel } from "./AuctionDayPanel";
import { DashboardCalendar } from "./DashboardCalendar";

function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * Encontra o dia "default" mais útil para abrir o painel:
 *   1. se houver leilão hoje → hoje
 *   2. senão, a próxima data futura com leilão
 *   3. senão, a data mais recente (passada) com leilão
 *   4. senão, hoje (mesmo sem nada)
 *
 * Recebe ``nowIso`` para garantir que o estado inicial seja
 * **determinístico** entre SSR e cliente (evita hydration mismatch).
 * Usar ``new Date()`` aqui produziria valores diferentes no servidor
 * e no cliente quando os fusos divergem perto da meia-noite.
 */
function pickInitialDate(
  events: DashboardCalendarEvent[],
  nowIso: string,
): string {
  const today = ymdLocal(new Date(nowIso));
  const days = new Set<string>();
  for (const e of events) {
    const d = new Date(e.date);
    if (!Number.isNaN(d.getTime())) days.add(ymdLocal(d));
  }
  if (days.has(today)) return today;

  const sorted = [...days].sort();
  const futures = sorted.filter((d) => d >= today);
  if (futures.length > 0) return futures[0];
  if (sorted.length > 0) return sorted[sorted.length - 1];
  return today;
}

export function CalendarSection({
  events,
  nowIso,
}: {
  events: DashboardCalendarEvent[];
  /** ISO timestamp do servidor (ex.: ``DashboardResponse.generated_at``). */
  nowIso: string;
}) {
  const initial = useMemo(
    () => pickInitialDate(events, nowIso),
    [events, nowIso],
  );
  const [selectedDate, setSelectedDate] = useState<string>(initial);

  const dayEvents = useMemo(() => {
    return events.filter((e) => {
      const d = new Date(e.date);
      return !Number.isNaN(d.getTime()) && ymdLocal(d) === selectedDate;
    });
  }, [events, selectedDate]);

  return (
    <div className="space-y-4">
      <DashboardCalendar
        events={events}
        selectedDate={selectedDate}
        onSelectDate={setSelectedDate}
        nowIso={nowIso}
      />
      <AuctionDayPanel
        date={selectedDate}
        events={dayEvents}
        nowIso={nowIso}
      />
    </div>
  );
}
