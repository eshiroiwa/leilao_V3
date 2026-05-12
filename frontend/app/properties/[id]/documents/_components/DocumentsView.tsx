"use client";

import { FileText, Loader2, Sparkles } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  api,
  type DocumentAnalysisRow,
  type DocumentType,
  type PropertyDocument,
} from "@/lib/api";

import { DocumentRow } from "./DocumentRow";
import { DocumentTypeDialog } from "./DocumentTypeDialog";
import { ReportCard } from "./ReportCard";

const ACCEPT_MIME =
  "application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

type PendingFile = { file: File; key: string };

export function DocumentsView({
  propertyId,
  initialDocuments,
  initialAnalysis,
}: {
  propertyId: string;
  initialDocuments: PropertyDocument[];
  initialAnalysis: DocumentAnalysisRow | null;
}) {
  const [documents, setDocuments] = useState<PropertyDocument[]>(initialDocuments);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [analysis, setAnalysis] = useState<DocumentAnalysisRow | null>(
    initialAnalysis,
  );
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const [pending, setPending] = useState<PendingFile | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const totalBytes = useMemo(
    () => documents.reduce((s, d) => s + (d.size_bytes || 0), 0),
    [documents],
  );

  const toggleSelected = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const queueFile = useCallback((file: File) => {
    setUploadError(null);
    // Usa nome+size+lastModified como chave para forçar re-render do dialog.
    const key = `${file.name}-${file.size}-${file.lastModified}`;
    setPending({ file, key });
  }, []);

  const handleSelectFiles = useCallback(() => inputRef.current?.click(), []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) queueFile(file);
    },
    [queueFile],
  );

  const handleConfirmUpload = useCallback(
    async (docType: DocumentType, customLabel: string | null) => {
      if (!pending) return;
      setUploading(true);
      setUploadError(null);
      try {
        const row = await api.uploadPropertyDocument(
          propertyId,
          pending.file,
          docType,
          customLabel,
        );
        setDocuments((prev) => [row, ...prev]);
        setPending(null);
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : String(err));
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [pending, propertyId],
  );

  const handleDelete = useCallback(
    async (documentId: string) => {
      if (!confirm("Remover este documento? Esta ação não pode ser desfeita.")) {
        return;
      }
      try {
        await api.deletePropertyDocument(documentId);
        setDocuments((prev) => prev.filter((d) => d.id !== documentId));
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.delete(documentId);
          return next;
        });
      } catch (err) {
        alert(
          `Falha ao remover: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    },
    [],
  );

  const handleAnalyze = useCallback(async () => {
    if (selectedIds.size === 0) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const res = await api.analyzeDocuments(propertyId, Array.from(selectedIds));
      setAnalysis(res);
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : String(err));
    } finally {
      setAnalyzing(false);
    }
  }, [propertyId, selectedIds]);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
      <section className="space-y-4">
        <Card>
          <CardContent className="space-y-3 p-4">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              className={`rounded-md border border-dashed p-6 text-center transition-colors ${
                isDragging ? "border-primary bg-primary/5" : "border-muted"
              }`}
            >
              <FileText className="mx-auto size-6 text-muted-foreground" />
              <p className="mt-2 text-sm text-muted-foreground">
                Arraste arquivos aqui ou{" "}
                <button
                  type="button"
                  onClick={handleSelectFiles}
                  className="text-primary underline-offset-4 hover:underline"
                  disabled={uploading}
                >
                  selecione do disco
                </button>
                .
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Aceitos: PDF, JPG, PNG, DOCX, TXT. Limite por arquivo 25 MB
                (200 MB no total por imóvel).
              </p>
              {uploading && (
                <p className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Loader2 className="size-3 animate-spin" />
                  Enviando…
                </p>
              )}
              {uploadError && (
                <p className="mt-2 text-xs text-destructive">{uploadError}</p>
              )}
            </div>

            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT_MIME}
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) queueFile(f);
              }}
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-2 p-4">
            <header className="flex items-baseline justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">
                  Arquivos anexados ({documents.length})
                </h3>
                <p className="text-[11px] text-muted-foreground">
                  Total: {formatBytes(totalBytes)} · marque para incluir na
                  análise.
                </p>
              </div>
              <Button
                size="sm"
                onClick={handleAnalyze}
                disabled={selectedIds.size === 0 || analyzing}
              >
                {analyzing ? (
                  <>
                    <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                    Analisando…
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-1.5 size-3.5" />
                    Analisar selecionados ({selectedIds.size})
                  </>
                )}
              </Button>
            </header>

            {documents.length === 0 ? (
              <p className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground">
                Nenhum documento anexado ainda.
              </p>
            ) : (
              <ul className="divide-y">
                {documents.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    selected={selectedIds.has(doc.id)}
                    onToggle={() => toggleSelected(doc.id)}
                    onDelete={() => void handleDelete(doc.id)}
                  />
                ))}
              </ul>
            )}

            {analyzeError && (
              <p className="text-xs text-destructive">{analyzeError}</p>
            )}
          </CardContent>
        </Card>
      </section>

      <aside className="space-y-4">
        <ReportCard analysis={analysis} />
      </aside>

      {pending && (
        <DocumentTypeDialog
          key={pending.key}
          file={pending.file}
          uploading={uploading}
          onCancel={() => {
            setPending(null);
            if (inputRef.current) inputRef.current.value = "";
          }}
          onConfirm={handleConfirmUpload}
        />
      )}
    </div>
  );
}

export function formatBytes(n: number): string {
  if (n <= 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`;
}
