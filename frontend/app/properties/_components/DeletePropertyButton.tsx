"use client";

import { useState, useTransition } from "react";
import { Loader2, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export type DeletePropertyButtonProps = {
  propertyId: string;
  propertyTitle?: string | null;
  onDeleted?: (id: string) => void | Promise<void>;
  /** Se true, renderiza um botão pequeno (32×32) só com ícone (default). */
  compact?: boolean;
};

export function DeletePropertyButton({
  propertyId,
  propertyTitle,
  onDeleted,
  compact = true,
}: DeletePropertyButtonProps) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleConfirm() {
    setError(null);
    startTransition(async () => {
      try {
        const { api } = await import("@/lib/api");
        await api.deleteProperty(propertyId);
        await onDeleted?.(propertyId);
        setOpen(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erro desconhecido");
      }
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!isPending) setOpen(o);
      }}
    >
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size={compact ? "icon" : "sm"}
          // o card pai tem onClick de seleção; impedimos que o clique escape
          onClick={(e) => e.stopPropagation()}
          aria-label="Excluir imóvel"
          title="Excluir imóvel"
          className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
        >
          <Trash2 className="size-4" />
          {!compact && <span className="ml-1">Excluir</span>}
        </Button>
      </DialogTrigger>

      <DialogContent
        // bloqueia bubble dos cliques pra não acionar a seleção do card
        onClick={(e) => e.stopPropagation()}
      >
        <DialogHeader>
          <DialogTitle>Excluir imóvel?</DialogTitle>
          <DialogDescription>
            Esta ação não pode ser desfeita. O registro
            {propertyTitle ? (
              <>
                {" "}
                <span className="font-medium text-foreground">
                  &ldquo;{propertyTitle}&rdquo;
                </span>{" "}
              </>
            ) : (
              " "
            )}
            será removido permanentemente. Os logs em{" "}
            <code>agent_runs</code> são preservados (com{" "}
            <code>property_id = NULL</code>).
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={isPending}
          >
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={isPending}
          >
            {isPending && <Loader2 className="size-4 animate-spin" />}
            {isPending ? "Excluindo…" : "Excluir"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
