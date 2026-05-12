import {
  api,
  type DocumentAnalysisRow,
  type Property,
  type PropertyDocument,
} from "@/lib/api";

import { DocumentsView } from "./_components/DocumentsView";

export const dynamic = "force-dynamic";

export default async function PropertyDocumentsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [propertyList, documents, latestAnalysis] = await Promise.all([
    api.listProperties({ limit: 200 }).catch(() => [] as Property[]),
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
        <h2 className="text-lg font-semibold tracking-tight">Documentos</h2>
        <p className="text-sm text-muted-foreground">
          Anexe matrícula, edital, laudo de avaliação, peças processuais e
          outros documentos relevantes. Os arquivos ficam disponíveis para
          visualização. Quando quiser, selecione um conjunto e dispare uma
          análise consolidada (riscos, ônus, recomendações).
        </p>
      </div>

      <DocumentsView
        propertyId={property.id}
        initialDocuments={documents}
        initialAnalysis={latestAnalysis}
      />
    </div>
  );
}
