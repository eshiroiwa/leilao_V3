"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import type { DashboardCalendarEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

const WEEKDAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MONTHS = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

function ymd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

export type DashboardCalendarProps = {
  events: DashboardCalendarEvent[];
  selectedDate: string | null;
  onSelectDate: (ymd: string) => void;
  /** ISO timestamp do servidor — usado para destacar "hoje" sem
   *  causar hydration mismatch. */
  nowIso: string;
};

export function DashboardCalendar({
  events,
  selectedDate,
  onSelectDate,
  nowIso,
}: DashboardCalendarProps) {
  // Mês a exibir — começa no mês do "hoje" ou da data selecionada.
  const initialAnchor = useMemo(() => {
    const seed = selectedDate ? new Date(selectedDate) : new Date(nowIso);
    return startOfMonth(seed);
  }, [selectedDate, nowIso]);

  const [anchor, setAnchor] = useState<Date>(initialAnchor);

  // Index de eventos por dia (YYYY-MM-DD).
  const eventsByDay = useMemo(() => {
    const map = new Map<string, { first: number; second: number }>();
    for (const e of events) {
      const d = new Date(e.date);
      if (Number.isNaN(d.getTime())) continue;
      const key = ymd(d);
      const cur = map.get(key) ?? { first: 0, second: 0 };
      if (e.kind === "first") cur.first += 1;
      else cur.second += 1;
      map.set(key, cur);
    }
    return map;
  }, [events]);

  // Grade do mês: 6 linhas × 7 colunas, cobrindo dias que vazam para meses adjacentes.
  const cells = useMemo(() => {
    const first = startOfMonth(anchor);
    const last = endOfMonth(anchor);
    const startWeekday = first.getDay(); // 0 = domingo
    const startDate = new Date(
      first.getFullYear(),
      first.getMonth(),
      1 - startWeekday,
    );
    const totalDays = startWeekday + last.getDate();
    const rows = Math.ceil(totalDays / 7);
    const out: Date[] = [];
    const total = rows * 7;
    for (let i = 0; i < total; i++) {
      out.push(
        new Date(
          startDate.getFullYear(),
          startDate.getMonth(),
          startDate.getDate() + i,
        ),
      );
    }
    return out;
  }, [anchor]);

  const todayKey = ymd(new Date(nowIso));
  const monthLabel = `${MONTHS[anchor.getMonth()]} ${anchor.getFullYear()}`;

  return (
    <div className="rounded-2xl border bg-card p-3 sm:p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Calendário de leilões
          </p>
          <h3 className="truncate text-sm font-semibold capitalize tracking-tight">
            {monthLabel}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="size-7"
            onClick={() => setAnchor((a) => addMonths(a, -1))}
            aria-label="Mês anterior"
          >
            <ChevronLeft className="size-3.5" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => setAnchor(startOfMonth(new Date(nowIso)))}
          >
            Hoje
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="size-7"
            onClick={() => setAnchor((a) => addMonths(a, 1))}
            aria-label="Próximo mês"
          >
            <ChevronRight className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-0.5 text-center text-[9px] font-medium uppercase tracking-wider text-muted-foreground">
        {WEEKDAYS.map((w) => (
          <div key={w} className="py-0.5">
            {w}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((d) => {
          const key = ymd(d);
          const inMonth = d.getMonth() === anchor.getMonth();
          const isToday = key === todayKey;
          const isSelected = key === selectedDate;
          const counts = eventsByDay.get(key);
          const has = !!counts;

          return (
            <button
              key={key}
              type="button"
              onClick={() => has && onSelectDate(key)}
              disabled={!has}
              aria-pressed={isSelected}
              className={cn(
                "relative flex h-9 flex-col items-center justify-center gap-0.5 rounded-md border text-xs transition-colors",
                inMonth ? "" : "opacity-40",
                has
                  ? "cursor-pointer hover:border-primary/50 hover:bg-primary-50"
                  : "cursor-default border-transparent",
                isSelected
                  ? "border-primary bg-primary-100 text-primary-700 ring-2 ring-primary/40"
                  : isToday
                    ? "border-primary/40 bg-primary-50 text-foreground"
                    : has
                      ? "border-border text-foreground"
                      : "text-muted-foreground",
              )}
              title={
                has
                  ? `${(counts?.first ?? 0) + (counts?.second ?? 0)} leilão(ões) em ${d.toLocaleDateString("pt-BR")}`
                  : undefined
              }
            >
              <span className="text-[11px] font-medium leading-none">
                {d.getDate()}
              </span>
              {has ? (
                <span
                  className="flex h-1.5 items-center justify-center gap-0.5"
                  aria-hidden="true"
                >
                  {counts!.first > 0 && (
                    <span className="size-1.5 rounded-full bg-primary" />
                  )}
                  {counts!.second > 0 && (
                    <span className="size-1.5 rounded-full bg-warning" />
                  )}
                </span>
              ) : (
                <span className="h-1.5" aria-hidden="true" />
              )}
            </button>
          );
        })}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <span className="size-1.5 rounded-full bg-primary" />
          1ª praça
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="size-1.5 rounded-full bg-warning" />
          2ª praça
        </span>
      </div>
    </div>
  );
}
