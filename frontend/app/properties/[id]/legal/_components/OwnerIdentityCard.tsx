"use client";

import { ChevronDown, ChevronUp, Loader2, Search } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Property } from "@/lib/api";
import {
  digitsOnly,
  maskCpfCnpj,
  validateCpfCnpj,
} from "@/lib/cpf-cnpj";

export function OwnerIdentityCard({
  property,
  currentCpfCnpj,
  running,
  error,
  onRun,
}: {
  property: Property;
  currentCpfCnpj: string | null;
  running: boolean;
  error: string | null;
  onRun: (params: {
    owner_name: string | null;
    owner_cpf_cnpj: string | null;
  }) => void;
}) {
  // Nome do proprietário — sinal principal para a busca web.
  const [nameDraft, setNameDraft] = useState<string>(property.owner_name ?? "");

  // CPF/CNPJ — secundário, só para registro.
  const [cpfDraft, setCpfDraft] = useState<string>(
    maskCpfCnpj(currentCpfCnpj ?? property.owner_cpf_cnpj ?? ""),
  );
  const [cpfExpanded, setCpfExpanded] = useState<boolean>(
    !!currentCpfCnpj || !!property.owner_cpf_cnpj,
  );

  const v = validateCpfCnpj(cpfDraft);
  const cpfFilled = v.kind === "cpf" || v.kind === "cnpj";
  const cpfDvOk = cpfFilled && v.dvValid;
  const cpfBlocking = cpfFilled && !cpfDvOk;

  const nameTrimmed = nameDraft.trim();
  const nameValid = nameTrimmed.length > 0 && nameTrimmed.split(/\s+/).length >= 2;

  const canRun = !running && nameValid && !cpfBlocking;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Identificação do proprietário</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="space-y-1">
          <Label htmlFor="owner_name" className="text-[11px]">
            Nome completo do proprietário
          </Label>
          <Input
            id="owner_name"
            value={nameDraft}
            placeholder="Ex.: João da Silva Pereira"
            onChange={(e) => setNameDraft(e.target.value)}
            aria-invalid={nameDraft.length > 0 && !nameValid}
          />
          {nameDraft.length > 0 && !nameValid && (
            <p className="text-[10px] text-destructive">
              Informe nome completo (≥ 2 palavras).
            </p>
          )}
          {!nameDraft && (
            <p className="text-[10px] text-muted-foreground">
              Scraper não extraiu o nome — informe manualmente para buscar.
            </p>
          )}
        </div>

        <Button
          className="w-full"
          onClick={() =>
            onRun({
              owner_name: nameTrimmed || null,
              owner_cpf_cnpj: digitsOnly(cpfDraft) || null,
            })
          }
          disabled={!canRun}
        >
          {running ? (
            <>
              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              Buscando…
            </>
          ) : (
            <>
              <Search className="mr-1.5 size-3.5" />
              Buscar processos do proprietário
            </>
          )}
        </Button>

        <button
          type="button"
          onClick={() => setCpfExpanded((v) => !v)}
          className="flex w-full items-center justify-between gap-2 text-[11px] text-muted-foreground hover:text-foreground"
        >
          <span>CPF/CNPJ (opcional, apenas para registro)</span>
          {cpfExpanded ? (
            <ChevronUp className="size-3" />
          ) : (
            <ChevronDown className="size-3" />
          )}
        </button>

        {cpfExpanded && (
          <div className="space-y-1">
            <Input
              id="owner_cpf_cnpj"
              value={cpfDraft}
              placeholder="000.000.000-00"
              onChange={(e) => setCpfDraft(maskCpfCnpj(e.target.value))}
              aria-invalid={cpfBlocking}
            />
            {cpfBlocking && (
              <p className="text-[10px] text-destructive">
                Documento inválido (DV não confere).
              </p>
            )}
            {cpfFilled && cpfDvOk && (
              <p className="text-[10px] text-muted-foreground">
                {v.kind === "cpf" ? "CPF válido" : "CNPJ válido"} — fica
                registrado mas não entra na busca.
              </p>
            )}
            {v.kind === "incomplete" && (
              <p className="text-[10px] text-muted-foreground">
                Digite 11 (CPF) ou 14 (CNPJ) dígitos.
              </p>
            )}
          </div>
        )}

        {error && <p className="text-xs text-destructive">{error}</p>}

        <p className="text-[10px] text-muted-foreground">
          A descoberta usa busca web (Firecrawl) sobre o NOME do proprietário,
          extrai números CNJ dos snippets e enriquece cada um via CNJ DataJud.
          O DataJud público não permite busca direta por CPF/nome (LGPD), por
          isso o nome é o sinal real — homônimos podem aparecer e devem ser
          validados.
        </p>
      </CardContent>
    </Card>
  );
}
