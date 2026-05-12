import { api, type LegalCheckResult, type Property } from "@/lib/api";

import { LegalView } from "./_components/LegalView";

export const dynamic = "force-dynamic";

export default async function PropertyLegalPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [propertyList, latestCheck] = await Promise.all([
    api.listProperties({ limit: 200 }).catch(() => [] as Property[]),
    api
      .getLatestLegalCheck(id)
      .catch(
        () =>
          null as (LegalCheckResult & { id?: string | null }) | null,
      ),
  ]);

  const property = propertyList.find((p) => p.id === id) ?? null;
  if (!property) return null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          Análise jurídica
        </h2>
        <p className="text-sm text-muted-foreground">
          Processos do proprietário (CNJ DataJud), ônus da matrícula e achados
          na web. Anulatórias de leilão e embargos à arrematação são
          destacados como críticos.
        </p>
      </div>

      <LegalView property={property} initialCheck={latestCheck} />
    </div>
  );
}
