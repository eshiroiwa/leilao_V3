"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Building2, Check, Edit3, Loader2, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Editor inline para o ``condo_name`` do imóvel.
 *
 * Por que existe: editais de leilão (Caixa em particular) raramente
 * trazem o nome do prédio. Quando o usuário sabe ("Edifício Park
 * Crispim"), ele preenche aqui — o AGENTE 2 passa a usar como query
 * primária e bonifica fortemente listings do MESMO prédio no scoring.
 *
 * Comportamento:
 *  - Botão de edição alterna para input.
 *  - Salvar (PATCH /properties/{id}) e router.refresh() para recarregar
 *    o Server Component pai com o valor novo.
 *  - String vazia/só-espaço → grava ``null`` (limpa).
 */
export function CondoNameEditor({
  propertyId,
  initialValue,
  propertyType,
}: {
  propertyId: string;
  initialValue: string | null;
  propertyType: string | null;
}) {
  const router = useRouter();
  const [editing, setEditing] = useState<boolean>(false);
  const [draft, setDraft] = useState<string>(initialValue ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  // Mostramos o card só para apartamentos — para casas/terrenos não faz
  // sentido perguntar nome do prédio.
  const showsForType =
    !propertyType ||
    ["apartamento", "comercial", "outro"].includes(
      propertyType.trim().toLowerCase(),
    );
  if (!showsForType) return null;

  const current = (initialValue ?? "").trim();

  function handleSave() {
    setError(null);
    const next = draft.trim();
    if (next === current) {
      setEditing(false);
      return;
    }
    startTransition(async () => {
      try {
        await api.patchProperty(propertyId, { condo_name: next || null });
        setEditing(false);
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    });
  }

  function handleCancel() {
    setDraft(initialValue ?? "");
    setEditing(false);
    setError(null);
  }

  return (
    <section
      className={cn(
        "flex flex-wrap items-start gap-3 rounded-xl border bg-muted/40 p-3 sm:items-center sm:p-4",
        !current && "border-dashed",
      )}
    >
      <Building2 className="size-4 shrink-0 text-primary" aria-hidden />

      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Nome do prédio / condomínio
        </div>

        {editing ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ex.: Edifício Park Crispim"
              maxLength={200}
              autoFocus
              disabled={isPending}
              className="h-9 max-w-md text-sm"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleSave();
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  handleCancel();
                }
              }}
            />
            <div className="flex items-center gap-1.5">
              <Button
                size="sm"
                onClick={handleSave}
                disabled={isPending}
                className="h-9 px-3"
              >
                {isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Check className="size-4" />
                )}
                <span className="ml-1">Salvar</span>
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={handleCancel}
                disabled={isPending}
                className="h-9 px-2"
              >
                <X className="size-4" />
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {current ? (
              <>
                <span className="text-sm font-medium">{current}</span>
                <Badge variant="success" className="text-[10px]">
                  usado pelo AGENTE 2
                </Badge>
              </>
            ) : (
              <span className="text-sm italic text-muted-foreground">
                Não informado — adicione para que a CMA priorize listings do
                mesmo prédio.
              </span>
            )}

            <Button
              size="sm"
              variant="ghost"
              onClick={() => setEditing(true)}
              className="ml-auto h-7 px-2 text-xs"
            >
              <Edit3 className="size-3.5" />
              <span className="ml-1">{current ? "Editar" : "Adicionar"}</span>
            </Button>
          </div>
        )}

        {error && (
          <p className="mt-1.5 text-xs text-destructive">{error}</p>
        )}

        {!editing && current && (
          <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">
            Quando preenchido, refaça a avaliação para o AGENTE 2 priorizar
            anúncios do MESMO prédio.
          </p>
        )}
      </div>
    </section>
  );
}
