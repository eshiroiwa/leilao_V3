"use client";

import { Loader2, Search } from "lucide-react";
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
  onRun: (cpfCnpj: string | null) => void;
}) {
  const [draft, setDraft] = useState<string>(
    maskCpfCnpj(currentCpfCnpj ?? property.owner_cpf_cnpj ?? ""),
  );

  const v = validateCpfCnpj(draft);
  const isComplete = v.kind === "cpf" || v.kind === "cnpj";
  const dvOk = isComplete && v.dvValid;
  const canRun =
    !running && (v.kind === "empty" || (isComplete && dvOk));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Identificação do proprietário</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="space-y-1">
          <Label htmlFor="owner_cpf_cnpj" className="text-[11px]">
            CPF / CNPJ
          </Label>
          <Input
            id="owner_cpf_cnpj"
            value={draft}
            placeholder="000.000.000-00"
            onChange={(e) => setDraft(maskCpfCnpj(e.target.value))}
            aria-invalid={isComplete && !dvOk}
          />
          {isComplete && !dvOk && (
            <p className="text-[10px] text-destructive">
              Documento inválido (DV não confere).
            </p>
          )}
          {isComplete && dvOk && (
            <p className="text-[10px] text-muted-foreground">
              {v.kind === "cpf" ? "CPF válido" : "CNPJ válido"}
            </p>
          )}
          {v.kind === "incomplete" && (
            <p className="text-[10px] text-muted-foreground">
              Digite 11 (CPF) ou 14 (CNPJ) dígitos.
            </p>
          )}
        </div>

        <Button
          className="w-full"
          onClick={() => {
            const dg = digitsOnly(draft);
            onRun(dg || null);
          }}
          disabled={!canRun}
        >
          {running ? (
            <>
              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              Consultando DataJud + web…
            </>
          ) : (
            <>
              <Search className="mr-1.5 size-3.5" />
              Executar análise jurídica
            </>
          )}
        </Button>
        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}
        <p className="text-[10px] text-muted-foreground">
          Consulta o CNJ DataJud (TJ + TRT da UF) e faz busca web por
          anulatórias/embargos ligados ao nome.
        </p>
      </CardContent>
    </Card>
  );
}
