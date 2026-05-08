import { ArrowRight, CheckCircle2, PlusCircle } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type DashboardResponse } from "@/lib/api";

import { DashboardBody } from "./_components/DashboardBody";

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
        <DashboardBody data={data!} />
      )}
    </div>
  );
}
