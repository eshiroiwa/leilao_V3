"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DOC_TYPE_LABELS, type DocumentType } from "@/lib/api";

import { formatBytes } from "./DocumentsView";

const TYPE_OPTIONS: { value: DocumentType; description: string }[] = [
  { value: "matricula", description: "Certidão de matrícula do imóvel" },
  { value: "edital", description: "Edital publicado pelo leiloeiro/juízo" },
  { value: "laudo_avaliacao", description: "Laudo técnico de avaliação" },
  { value: "pecas_processuais", description: "Decisões, penhora, certidões processuais" },
  { value: "outros", description: "Outro documento — informe um rótulo" },
];

export function DocumentTypeDialog({
  file,
  uploading,
  onCancel,
  onConfirm,
}: {
  file: File;
  uploading: boolean;
  onCancel: () => void;
  onConfirm: (docType: DocumentType, customLabel: string | null) => void;
}) {
  const [docType, setDocType] = useState<DocumentType>("edital");
  const [customLabel, setCustomLabel] = useState("");

  const canConfirm = useMemo(() => {
    if (uploading) return false;
    if (docType === "outros") return customLabel.trim().length > 0;
    return true;
  }, [docType, customLabel, uploading]);

  const handleConfirm = useCallback(() => {
    if (!canConfirm) return;
    onConfirm(docType, docType === "outros" ? customLabel.trim() : null);
  }, [docType, customLabel, canConfirm, onConfirm]);

  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Classificar documento</DialogTitle>
          <DialogDescription>
            {file.name} · {formatBytes(file.size)}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Tipo</Label>
            <div className="space-y-1">
              {TYPE_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex cursor-pointer items-start gap-2 rounded-md border p-2 text-sm transition-colors ${
                    docType === opt.value
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted"
                  }`}
                >
                  <input
                    type="radio"
                    name="doc_type"
                    value={opt.value}
                    checked={docType === opt.value}
                    onChange={() => setDocType(opt.value)}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{DOC_TYPE_LABELS[opt.value]}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {opt.description}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {docType === "outros" && (
            <div className="space-y-1">
              <Label htmlFor="custom_label">Rótulo</Label>
              <Input
                id="custom_label"
                placeholder="Ex.: Termo de visitação, IPTU 2024…"
                value={customLabel}
                onChange={(e) => setCustomLabel(e.target.value)}
                maxLength={120}
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={uploading}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
          >
            {uploading ? (
              <>
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                Enviando…
              </>
            ) : (
              "Anexar"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
