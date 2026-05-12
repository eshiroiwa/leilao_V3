"use client";

import { useCallback, useState } from "react";

import {
  api,
  type DocumentAnalysisRow,
  type LegalCheckResult,
  type Property,
  type PropertyDocument,
} from "@/lib/api";

import { DocumentsSummaryCard } from "./DocumentsSummaryCard";
import { OwnerIdentityCard } from "./OwnerIdentityCard";
import { ProcessesList } from "./ProcessesList";
import { WebFindingsCard } from "./WebFindingsCard";

type LegalCheckRow = LegalCheckResult & { id?: string | null };

export function LegalView({
  property,
  initialCheck,
  documents,
  latestAnalysis,
}: {
  property: Property;
  initialCheck: LegalCheckRow | null;
  documents: PropertyDocument[];
  latestAnalysis: DocumentAnalysisRow | null;
}) {
  const [check, setCheck] = useState<LegalCheckRow | null>(initialCheck);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const handleRun = useCallback(
    async (params: {
      owner_name: string | null;
      owner_cpf_cnpj: string | null;
    }) => {
      setRunning(true);
      setRunError(null);
      try {
        const res = await api.runLegalCheck(property.id, {
          owner_name: params.owner_name,
          owner_cpf_cnpj: params.owner_cpf_cnpj,
        });
        setCheck(res);
      } catch (err) {
        setRunError(err instanceof Error ? err.message : String(err));
      } finally {
        setRunning(false);
      }
    },
    [property.id],
  );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <aside className="space-y-4">
        <OwnerIdentityCard
          property={property}
          currentCpfCnpj={
            check?.owner_processes?.cpf_cnpj ??
            property.owner_cpf_cnpj ??
            null
          }
          running={running}
          error={runError}
          onRun={handleRun}
        />

        <DocumentsSummaryCard
          propertyId={property.id}
          documents={documents}
          latestAnalysis={latestAnalysis}
        />
      </aside>

      <section className="space-y-6">
        <ProcessesList check={check} />
        <WebFindingsCard findings={check?.web_findings ?? []} />
      </section>
    </div>
  );
}
