import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  MapPin,
  PlusCircle,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type DashboardResponse } from "@/lib/api";

import { CalendarSection } from "./_components/CalendarSection";
import { TopOpportunitiesList } from "./_components/TopOpportunitiesList";
import { UpcomingAuctionsList } from "./_components/UpcomingAuctionsList";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let data: DashboardResponse | null = null;
  let loadError: string | null = null;

  try {
    data = await api.getDashboard();
  } catch (err) {
    loadError = err instanceof Error ? err.message : "Erro desconhecido";
  }

  const totals = data?.totals;
  const isEmpty = !data || (totals?.properties ?? 0) === 0;

  return (
    <div className="space-y-8">
      {/* HERO compacto */}
      <section className="rounded-2xl border bg-gradient-to-br from-primary-50 via-card to-card p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-2">
            <Badge variant="info" className="w-fit">
              Multi-agente · LangGraph · Supabase
            </Badge>
            <h1 className="text-xl font-bold tracking-tight sm:text-2xl">
              Painel de operações
            </h1>
            <p className="max-w-2xl text-sm text-muted-foreground">
              Calendário de leilões, ranking de oportunidades e atalhos para os
              imóveis que precisam da sua atenção.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild>
              <Link href="/scrape">
                <PlusCircle className="size-4" /> Novo scrape
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/properties">
                Imóveis <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      {loadError && (
        <div className="rounded-xl border border-danger/40 bg-danger-50 p-4 text-sm text-danger-700">
          Não foi possível carregar o dashboard: {loadError}
        </div>
      )}

      {/* KPIs */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Imóveis cadastrados"
          value={totals?.properties ?? 0}
          hint={
            totals
              ? `${totals.with_geocoding} com geo`
              : "—"
          }
          icon={Building2}
          tone="primary"
        />
        <StatCard
          label="Leilões em 30 dias"
          value={totals?.upcoming_30d ?? 0}
          hint="Janela de oportunidade"
          icon={CalendarClock}
          tone="info"
        />
        <StatCard
          label="Sem avaliação"
          value={totals?.pending_valuation ?? 0}
          hint="Pendentes de CMA"
          icon={ClipboardList}
          tone={
            (totals?.pending_valuation ?? 0) > 0 ? "warning" : "success"
          }
        />
        <StatCard
          label="Sem oportunidade"
          value={totals?.pending_opportunity ?? 0}
          hint="Pendentes de análise"
          icon={AlertTriangle}
          tone={
            (totals?.pending_opportunity ?? 0) > 0 ? "warning" : "success"
          }
        />
        <StatCard
          label="Boas oportunidades"
          value={totals?.good_opportunities ?? 0}
          hint="Verdict ≥ ressalvas"
          icon={Sparkles}
          tone="success"
        />
        <StatCard
          label="Com geo"
          value={totals?.with_geocoding ?? 0}
          hint={
            totals && totals.properties > 0
              ? `${Math.round((totals.with_geocoding / totals.properties) * 100)}%`
              : "—"
          }
          icon={MapPin}
          tone="info"
        />
      </section>

      {isEmpty ? (
        <section className="rounded-2xl border border-dashed bg-card p-10 text-center">
          <CheckCircle2 className="mx-auto size-8 text-muted-foreground" />
          <h2 className="mt-3 text-base font-semibold">
            Comece pelo primeiro scrape
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Cole a URL de um lote de leiloeiro e o pipeline cuida do resto.
          </p>
          <div className="mt-4">
            <Button asChild>
              <Link href="/scrape">
                <PlusCircle className="size-4" /> Iniciar scrape
              </Link>
            </Button>
          </div>
        </section>
      ) : (
        <>
          {/* Calendário + Top oportunidades */}
          <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
            <CalendarSection
              events={data!.calendar}
              nowIso={data!.generated_at}
            />
            <TopOpportunitiesList items={data!.top_opportunities} />
          </section>

          {/* Próximos leilões cronológico */}
          <UpcomingAuctionsList
            items={data!.upcoming_auctions}
            nowIso={data!.generated_at}
          />
        </>
      )}
    </div>
  );
}
