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

  const geocoded = properties.filter((p) => p.latitude !== null && p.longitude !== null);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Imóveis processados</h1>
          <p className="text-muted-foreground">
            {properties.length} registro(s) · {geocoded.length} com geolocalização.
            Clique em um card para focar no mapa, ou clique no marcador.
          </p>
        </div>
      </div>

      {loadError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive">
          Não foi possível carregar a lista: {loadError}
        </div>
      )}

      {!loadError && properties.length === 0 && (
        <div className="rounded-md border bg-muted/30 p-10 text-center text-muted-foreground">
          Nenhum imóvel processado ainda. Comece em <strong>/scrape</strong>.
        </div>
      )}

      {properties.length > 0 && <PropertiesView properties={properties} />}
    </div>
  );
}
