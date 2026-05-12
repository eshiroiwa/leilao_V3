"use client";

import { useCallback, useState } from "react";

import {
  api,
  type LegalCheckResult,
  type Property,
} from "@/lib/api";

import { MatriculaUploadCard } from "./MatriculaUploadCard";
import { OwnerIdentityCard } from "./OwnerIdentityCard";
import { ProcessesList } from "./ProcessesList";
import { WebFindingsCard } from "./WebFindingsCard";

type LegalCheckRow = LegalCheckResult & { id?: string | null };

export function LegalView({
  property,
  initialCheck,
}: {
  property: Property;
  initialCheck: LegalCheckRow | null;
}) {
  const [check, setCheck] = useState<LegalCheckRow | null>(initialCheck);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const handleRun = useCallback(
    async (cpfCnpj: string | null) => {
      setRunning(true);
      setRunError(null);
      try {
        const res = await api.runLegalCheck(property.id, {
          owner_cpf_cnpj: cpfCnpj,
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

  const handleUploaded = useCallback(
    (matriculaOcr: LegalCheckRow["matricula_ocr"], pdfUrl: string | null) => {
      setCheck((prev) => {
        const base: LegalCheckRow =
          prev ?? ({
            property_id: property.id,
            started_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            duration_ms: 0,
            owner_processes: {
              status: "skipped",
              skipped_reason: "execute a análise para listar processos",
              cpf_cnpj: null,
              tribunal: null,
              total_hits: 0,
              critical_hits: 0,
              critical_labels: [],
              sample_processes: [],
            },
            matricula_check: {
              status: "skipped",
              skipped_reason: null,
              matricula: null,
              registry_office: null,
              onus_summary: [],
              fetched_at: null,
            },
            has_critical_findings: false,
            critical_findings: [],
          } as LegalCheckRow);
        return {
          ...base,
          matricula_ocr: matriculaOcr,
          matricula_pdf_signed_url: pdfUrl,
        };
      });
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

        <MatriculaUploadCard
          propertyId={property.id}
          existing={check?.matricula_ocr ?? null}
          pdfSignedUrl={check?.matricula_pdf_signed_url ?? null}
          onUploaded={handleUploaded}
        />
      </aside>

      <section className="space-y-6">
        <ProcessesList check={check} />
        <WebFindingsCard findings={check?.web_findings ?? []} />
      </section>
    </div>
  );
}
