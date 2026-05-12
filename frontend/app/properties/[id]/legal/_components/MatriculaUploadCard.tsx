"use client";

import {
  CheckCircle2,
  FileText,
  Loader2,
  Upload,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  api,
  type MatriculaOcrResult,
} from "@/lib/api";
import { maskCpfCnpj } from "@/lib/cpf-cnpj";
import { formatBRL } from "@/lib/utils";

const LIEN_LABEL: Record<string, string> = {
  hipoteca: "Hipoteca",
  penhora: "Penhora",
  usufruto: "Usufruto",
  alienacao_fiduciaria: "Alienação fiduciária",
  servidao: "Servidão",
  indisponibilidade: "Indisponibilidade",
  outro: "Outro",
};

export function MatriculaUploadCard({
  propertyId,
  existing,
  pdfSignedUrl,
  onUploaded,
}: {
  propertyId: string;
  existing: MatriculaOcrResult | null;
  pdfSignedUrl: string | null;
  onUploaded: (
    matriculaOcr: MatriculaOcrResult,
    pdfUrl: string | null,
  ) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handlePick = useCallback(() => inputRef.current?.click(), []);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setUploading(true);
      try {
        const res = await api.uploadMatriculaPdf(propertyId, file);
        onUploaded(res.matricula_ocr, res.pdf_signed_url);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [propertyId, onUploaded],
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Matrícula do imóvel</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {existing ? (
          <MatriculaSummary
            ocr={existing}
            pdfUrl={pdfSignedUrl}
            onReplace={handlePick}
            uploading={uploading}
          />
        ) : (
          <div className="rounded-md border border-dashed p-4 text-center">
            <FileText className="mx-auto size-6 text-muted-foreground" />
            <p className="mt-2 text-xs text-muted-foreground">
              Suba o PDF da matrícula para extrair proprietário, CPF, número,
              cartório e ônus ativos (Vision + GPT-4o).
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handlePick}
              disabled={uploading}
              className="mt-3"
            >
              {uploading ? (
                <>
                  <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                  Processando…
                </>
              ) : (
                <>
                  <Upload className="mr-1.5 size-3.5" />
                  Selecionar PDF
                </>
              )}
            </Button>
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
          }}
        />

        {error && <p className="text-xs text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

function MatriculaSummary({
  ocr,
  pdfUrl,
  onReplace,
  uploading,
}: {
  ocr: MatriculaOcrResult;
  pdfUrl: string | null;
  onReplace: () => void;
  uploading: boolean;
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <Badge
          variant={
            ocr.confidence === "HIGH"
              ? "success"
              : ocr.confidence === "MEDIUM"
                ? "secondary"
                : "warning"
          }
          className="text-[10px]"
        >
          confiança {ocr.confidence.toLowerCase()}
        </Badge>
        {ocr.is_clear && (
          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-success-700">
            <CheckCircle2 className="size-3.5" />
            Livre de ônus
          </span>
        )}
      </div>

      <Field label="Proprietário" value={ocr.owner_name} />
      <Field
        label="CPF/CNPJ"
        value={ocr.owner_cpf_cnpj ? maskCpfCnpj(ocr.owner_cpf_cnpj) : null}
      />
      <Field label="Matrícula" value={ocr.matricula_number} />
      <Field label="Cartório" value={ocr.registry_office} />

      {ocr.liens.length > 0 && (
        <div>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-danger-700">
            Ônus ativos ({ocr.liens.length})
          </div>
          <ul className="space-y-1">
            {ocr.liens.map((l, i) => (
              <li
                key={i}
                className="rounded border border-danger/30 bg-danger-50 px-2 py-1 text-[11px]"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <strong>{LIEN_LABEL[l.tipo] ?? l.tipo}</strong>
                  {l.av_numero && (
                    <span className="text-[10px] text-muted-foreground">
                      {l.av_numero}
                    </span>
                  )}
                </div>
                {l.credor && (
                  <div className="text-muted-foreground">{l.credor}</div>
                )}
                <div className="flex flex-wrap gap-x-2 text-[10px] text-muted-foreground">
                  {l.valor_brl != null && (
                    <span>Valor: {formatBRL(l.valor_brl)}</span>
                  )}
                  {l.data_registro && <span>Data: {l.data_registro}</span>}
                </div>
                {l.notes && (
                  <p className="mt-0.5 text-[10px] italic text-muted-foreground">
                    {l.notes}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {ocr.notes && (
        <p className="text-[10px] italic text-muted-foreground">
          {ocr.notes}
        </p>
      )}

      <div className="flex gap-2">
        {pdfUrl && (
          <a
            href={pdfUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] hover:bg-muted"
          >
            <FileText className="size-3.5" />
            Baixar PDF
          </a>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onReplace}
          disabled={uploading}
          className="text-[11px]"
        >
          {uploading ? (
            <>
              <Loader2 className="mr-1.5 size-3 animate-spin" />
              Processando…
            </>
          ) : (
            <>
              <Upload className="mr-1.5 size-3" />
              Trocar PDF
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground">{value ?? "—"}</span>
    </div>
  );
}
