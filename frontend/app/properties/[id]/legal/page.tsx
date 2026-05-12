import {
  api,
  type DocumentAnalysisRow,
  type LegalCheckResult,
  type Property,
  type PropertyDocument,
} from "@/lib/api";

import { LegalView } from "./_components/LegalView";

export const dynamic = "force-dynamic";

export default async function PropertyLegalPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [propertyList, latestCheck, documents, latestAnalysis] = await Promise.all([
    api.listProperties({ limit: 200 }).catch(() => [] as Property[]),
    api
      .getLatestLegalCheck(id)
      .catch(
        () =>
          null as (LegalCheckResult & { id?: string | null }) | null,
      ),
    api.listPropertyDocuments(id).catch(() => [] as PropertyDocument[]),
    api
      .getLatestDocumentAnalysis(id)
      .catch(() => null as DocumentAnalysisRow | null),
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
          Processos do proprietário (CNJ DataJud), achados na web e análise
          consolidada dos documentos anexados. Para anexar matrícula, edital,
          laudo e outros documentos, use a aba <strong>Documentos</strong>.
        </p>
      </div>

      <LegalView
        property={property}
        initialCheck={latestCheck}
        documents={documents}
        latestAnalysis={latestAnalysis}
      />
    </div>
  );
}
