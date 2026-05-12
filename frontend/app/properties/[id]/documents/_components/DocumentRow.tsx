"use client";

import {
  ExternalLink,
  File,
  FileSearch,
  FileText,
  Gavel,
  Scale,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  DOC_TYPE_LABELS,
  type DocumentType,
  type PropertyDocument,
} from "@/lib/api";
import { formatDateTimeBR } from "@/lib/utils";

import { formatBytes } from "./DocumentsView";

const ICON_BY_TYPE: Record<DocumentType, typeof FileText> = {
  matricula: FileText,
  edital: Gavel,
  laudo_avaliacao: Scale,
  pecas_processuais: FileSearch,
  outros: File,
};

export function DocumentRow({
  doc,
  selected,
  onToggle,
  onDelete,
}: {
  doc: PropertyDocument;
  selected: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const Icon = ICON_BY_TYPE[doc.doc_type] ?? File;
  const label = doc.custom_label || DOC_TYPE_LABELS[doc.doc_type];

  return (
    <li className="flex items-center gap-3 py-3">
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggle}
        className="size-4 cursor-pointer"
        aria-label={`Incluir ${doc.original_filename} na análise`}
      />

      <Icon className="size-5 shrink-0 text-muted-foreground" />

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate text-sm font-medium" title={doc.original_filename}>
            {doc.original_filename}
          </span>
          <Badge variant="secondary" className="shrink-0 text-[10px]">
            {label}
          </Badge>
        </div>
        <div className="text-[11px] text-muted-foreground">
          {formatDateTimeBR(doc.created_at)} · {formatBytes(doc.size_bytes)}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        {doc.signed_url ? (
          <a
            href={doc.signed_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] hover:bg-muted"
          >
            <ExternalLink className="size-3" />
            Visualizar
          </a>
        ) : (
          <span
            className="inline-flex cursor-not-allowed items-center gap-1 rounded-md border px-2 py-1 text-[11px] opacity-50"
            title="URL temporária indisponível — recarregue a página"
          >
            <ExternalLink className="size-3" />
            Visualizar
          </span>
        )}
        <button
          type="button"
          onClick={onDelete}
          className="inline-flex items-center gap-1 rounded-md border border-destructive/40 px-2 py-1 text-[11px] text-destructive hover:bg-destructive/10"
          aria-label="Remover documento"
        >
          <Trash2 className="size-3" />
        </button>
      </div>
    </li>
  );
}
