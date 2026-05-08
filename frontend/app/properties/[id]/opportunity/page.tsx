import Link from "next/link";
import { notFound } from "next/navigation";

import { PropertyImage } from "@/components/PropertyImage";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  type DeepAnalysisRow,
  type OpportunityAnalysisRow,
  type Property,
  type Valuation,
} from "@/lib/api";
import { formatBRL } from "@/lib/utils";

import { DeepAnalysisSection } from "./_components/DeepAnalysisSection";
import { OpportunityView } from "./_components/OpportunityView";

export const dynamic = "force-dynamic";

export default async function PropertyOpportunityPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  // Carrega contexto em paralelo: imóvel, valuations, histórico de análises
  // e a última deep analysis (cache hint para o componente client-side).
  const [propertyList, valuations, history, latestDeep] = await Promise.all([
    api.listProperties({ limit: 200 }).catch(() => [] as Property[]),
    api.listValuations(id).catch(() => [] as Valuation[]),
    api.listOpportunities(id).catch(() => [] as OpportunityAnalysisRow[]),
    api.getLatestDeepAnalysis(id).catch(() => null as DeepAnalysisRow | null),
  ]);

  const property = propertyList.find((p) => p.id === id) ?? null;
  if (!property) notFound();

  const latestValuation = valuations[0] ?? null;

  return (
    <main className="mx-auto w-full max-w-[1600px] space-y-6 p-6">
      <header>
        <Link
          href="/properties"
          className="text-sm text-muted-foreground hover:text-primary"
        >
          ← Voltar
        </Link>
        <h1 className="mt-1 text-2xl font-semibold">
          Análise de oportunidade
        </h1>
        <p className="text-sm text-muted-foreground">
          {property.title ?? "Imóvel sem título"} · {property.city}/
          {property.state}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Imóvel</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-6 md:grid-cols-[280px_1fr]">
          <PropertyImage
            src={property.image_url}
            alt={property.title ?? "Foto do imóvel"}
            className="rounded-md border"
          />
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-3">
            <Field label="Tipo" value={property.property_type} capitalize />
            <Field
              label="Área total"
              value={
                property.area_total_m2
                  ? `${property.area_total_m2} m²`
                  : null
              }
            />
            <Field label="Quartos" value={property.bedrooms} />
            <Field
              label="Endereço"
              value={property.address_full}
              className="col-span-full"
            />
            <Field
              label="Avaliação"
              value={formatBRL(property.appraisal_value)}
            />
            <Field
              label="1ª praça"
              value={formatBRL(property.minimum_bid_first)}
            />
            <Field
              label="2ª praça"
              value={formatBRL(property.minimum_bid_second)}
            />
          </div>
        </CardContent>
      </Card>

      {!latestValuation && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Sem avaliação de mercado
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Recomendamos rodar a{" "}
            <Link
              href={`/properties/${encodeURIComponent(id)}/valuation`}
              className="text-primary hover:underline"
            >
              avaliação de mercado (CMA)
            </Link>{" "}
            antes para fundamentar os preços de venda dos cenários. Você ainda
            pode prosseguir, mas os cenários serão estimados a partir do lance.
          </CardContent>
        </Card>
      )}

      <OpportunityView
        property={property}
        valuation={latestValuation}
        history={history}
      />

      <DeepAnalysisSection
        propertyId={property.id}
        opportunityAnalysisId={history[0]?.id ?? null}
        initialLatest={latestDeep}
      />
    </main>
  );
}

function Field({
  label,
  value,
  className,
  capitalize,
}: {
  label: string;
  value: string | number | null | undefined;
  className?: string;
  capitalize?: boolean;
}) {
  return (
    <div className={className}>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={`mt-0.5 text-sm font-medium ${capitalize ? "capitalize" : ""}`}
      >
        {value ?? "—"}
      </div>
    </div>
  );
}
