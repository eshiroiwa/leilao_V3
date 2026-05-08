import { Building2, PlusCircle } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { api, type Property } from "@/lib/api";

import { PropertiesView } from "./_components/PropertiesView";

export const dynamic = "force-dynamic";

export default async function PropertiesPage() {
  let properties: Property[] = [];
  let loadError: string | null = null;

  try {
    properties = await api.listProperties({ limit: 100 });
  } catch (err) {
    loadError = err instanceof Error ? err.message : "Erro desconhecido";
  }

  const geocoded = properties.filter(
    (p) => p.latitude !== null && p.longitude !== null,
  );

  // Timestamp único compartilhado com o cliente para classificar
  // leilões encerrados de forma determinística (evita mismatch SSR).
  const nowIso = new Date().toISOString();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Imóveis processados
          </h1>
          <p className="text-sm text-muted-foreground">
            {properties.length} registro(s) · {geocoded.length} com
            geolocalização. Use a busca para filtrar e clique nos cards para
            focar no mapa.
          </p>
        </div>
        <Button asChild>
          <Link href="/scrape">
            <PlusCircle className="size-4" /> Novo scrape
          </Link>
        </Button>
      </div>

      {loadError && (
        <div className="rounded-xl border border-danger/40 bg-danger-50 p-4 text-sm text-danger-700">
          Não foi possível carregar a lista: {loadError}
        </div>
      )}

      {!loadError && properties.length === 0 && (
        <EmptyState
          icon={Building2}
          title="Nenhum imóvel processado ainda"
          description="Cole a URL de um lote de leiloeiro para começar — o pipeline cuida do resto."
          action={
            <Button asChild>
              <Link href="/scrape">
                <PlusCircle className="size-4" /> Iniciar primeiro scrape
              </Link>
            </Button>
          }
        />
      )}

      {properties.length > 0 && (
        <PropertiesView properties={properties} nowIso={nowIso} />
      )}
    </div>
  );
}
