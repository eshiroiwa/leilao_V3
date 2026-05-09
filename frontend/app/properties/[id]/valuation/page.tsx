import { Card, CardContent } from "@/components/ui/card";
import { api, type Property, type Valuation } from "@/lib/api";

import { CondoNameEditor } from "./_components/CondoNameEditor";
import { ValuationActions } from "./_components/ValuationActions";
import { ValuationDetailView } from "./_components/ValuationDetailView";

export const dynamic = "force-dynamic";

export default async function PropertyValuationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [propertyList, valuations] = await Promise.all([
    api.listProperties({ limit: 200 }).catch(() => [] as Property[]),
    api.listValuations(id).catch(() => [] as Valuation[]),
  ]);

  const property = propertyList.find((p) => p.id === id) ?? null;
  if (!property) return null;

  const latest = valuations[0] ?? null;
  const detail = latest
    ? await api.getValuationDetail(id, latest.id).catch(() => null)
    : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">
            Avaliação de mercado
          </h2>
          <p className="text-sm text-muted-foreground">
            Estimativa via comparáveis em portais imobiliários (CMA).
          </p>
        </div>
        <ValuationActions propertyId={id} />
      </div>

      <CondoNameEditor
        propertyId={id}
        initialValue={property.condo_name}
        propertyType={property.property_type}
      />

      {valuations.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            Nenhuma avaliação ainda. Clique em <strong>Disparar avaliação</strong>{" "}
            no topo da página.
          </CardContent>
        </Card>
      ) : (
        <ValuationDetailView
          property={property}
          valuation={latest!}
          detail={detail}
          history={valuations}
        />
      )}
    </div>
  );
}
