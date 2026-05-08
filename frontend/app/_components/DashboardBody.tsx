"use client";

import {
  AlertTriangle,
  Building2,
  CalendarClock,
  ClipboardList,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

import { StatCard } from "@/components/StatCard";
import type { DashboardResponse } from "@/lib/api";

import { CalendarSection } from "./CalendarSection";
import { SidebarPanel } from "./SidebarPanel";
import type { DashboardFilter } from "./types";
import { UpcomingAuctionsList } from "./UpcomingAuctionsList";

export function DashboardBody({ data }: { data: DashboardResponse }) {
  const [filter, setFilter] = useState<DashboardFilter>("good_opportunities");
  const totals = data.totals;

  return (
    <>
      {/* KPIs interativos — clicar troca o conteúdo do painel lateral.
          Cada card mostra "selected" quando ativo. */}
      <section
        role="tablist"
        aria-label="Filtros do dashboard"
        className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5"
      >
        <StatCard
          label="Top ranking"
          value={totals.good_opportunities}
          hint="Boas oportunidades"
          icon={Sparkles}
          tone="success"
          selected={filter === "good_opportunities"}
          onClick={() => setFilter("good_opportunities")}
        />
        <StatCard
          label="Imóveis cadastrados"
          value={totals.properties}
          hint={`${totals.with_geocoding} com geo`}
          icon={Building2}
          tone="primary"
          selected={filter === "all"}
          onClick={() => setFilter("all")}
        />
        <StatCard
          label="Leilões em 30 dias"
          value={totals.upcoming_30d}
          hint="Janela de oportunidade"
          icon={CalendarClock}
          tone="info"
          selected={filter === "upcoming_30d"}
          onClick={() => setFilter("upcoming_30d")}
        />
        <StatCard
          label="Sem avaliação"
          value={totals.pending_valuation}
          hint="Pendentes de CMA"
          icon={ClipboardList}
          tone={totals.pending_valuation > 0 ? "warning" : "success"}
          selected={filter === "pending_valuation"}
          onClick={() => setFilter("pending_valuation")}
        />
        <StatCard
          label="Sem oportunidade"
          value={totals.pending_opportunity}
          hint="Pendentes de análise"
          icon={AlertTriangle}
          tone={totals.pending_opportunity > 0 ? "warning" : "success"}
          selected={filter === "pending_opportunity"}
          onClick={() => setFilter("pending_opportunity")}
        />
      </section>

      {/* Calendário + Painel lateral dinâmico */}
      <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
        <CalendarSection
          events={data.calendar}
          nowIso={data.generated_at}
        />
        {filter === "good_opportunities" ? (
          <SidebarPanel
            filter="good_opportunities"
            items={data.top_opportunities}
          />
        ) : (
          <SidebarPanel filter={filter} items={data.buckets[filter]} />
        )}
      </section>

      <UpcomingAuctionsList
        items={data.upcoming_auctions}
        nowIso={data.generated_at}
      />
    </>
  );
}
