import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type Property, type Valuation } from "@/lib/api";

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
  if (!property) notFound();

  const latest = valuations[0] ?? null;
  const detail = latest
    ? await api.getValuationDetail(id, latest.id).catch(() => null)
    : null;

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <Link
            href="/properties"
            className="text-sm text-muted-foreground hover:text-primary"
          >
            ← Voltar
          </Link>
          <h1 className="mt-1 text-2xl font-semibold">Avaliação de mercado</h1>
          <p className="text-sm text-muted-foreground">
            {property.title ?? "Imóvel sem título"} · {property.city}/{property.state}
          </p>
        </div>
        <ValuationActions propertyId={id} />
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Imóvel</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
          <Field label="Tipo" value={property.property_type} capitalize />
          <Field label="Área total" value={property.area_total_m2 ? `${property.area_total_m2} m²` : null} />
          <Field label="Quartos" value={property.bedrooms} />
          <Field label="Vagas" value={property.parking_spaces} />
          <Field label="Endereço" value={property.address_full} className="col-span-full" />
          <Field
            label="Avaliação (leiloeiro)"
            value={fmtBRL(property.appraisal_value)}
          />
          <Field label="1ª praça" value={fmtBRL(property.minimum_bid_first)} />
          <Field label="2ª praça" value={fmtBRL(property.minimum_bid_second)} />
          <Field
            label="Geo"
            value={property.geocoding_confidence ?? "—"}
          />
        </CardContent>
      </Card>

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
      <div className={`mt-0.5 text-sm font-medium ${capitalize ? "capitalize" : ""}`}>
        {value ?? "—"}
      </div>
    </div>
  );
}

function fmtBRL(v: number | null | undefined): string | null {
  if (v == null) return null;
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(v);
}
