import { AlertTriangle } from "lucide-react";
import Link from "next/link";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  api,
  type DeepAnalysisRow,
  type OpportunityAnalysisRow,
  type Property,
  type Valuation,
} from "@/lib/api";

import { DeepAnalysisSection } from "./_components/DeepAnalysisSection";
import { OpportunityView } from "./_components/OpportunityView";

export const dynamic = "force-dynamic";

export default async function PropertyOpportunityPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [propertyList, valuations, history, latestDeep] = await Promise.all([
    api.listProperties({ limit: 200 }).catch(() => [] as Property[]),
    api.listValuations(id).catch(() => [] as Valuation[]),
    api.listOpportunities(id).catch(() => [] as OpportunityAnalysisRow[]),
    api.getLatestDeepAnalysis(id).catch(() => null as DeepAnalysisRow | null),
  ]);

  const property = propertyList.find((p) => p.id === id) ?? null;
  if (!property) return null;

  const latestValuation = valuations[0] ?? null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          Análise de oportunidade
        </h2>
        <p className="text-sm text-muted-foreground">
          Custos, ROI, veredicto e lance máximo para o ROI alvo.
        </p>
      </div>

      {!latestValuation && (
        <Card className="border-warning/40 bg-warning-50">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-warning-700" />
              <CardTitle className="text-sm">
                Sem avaliação de mercado
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="text-sm text-warning-700">
            Recomendamos rodar a{" "}
            <Link
              href={`/properties/${encodeURIComponent(id)}/valuation`}
              className="font-medium underline underline-offset-2"
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
    </div>
  );
}
