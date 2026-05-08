"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  OpportunityAssumptions,
  OpportunityInput,
  Property,
  RenovationLevel,
} from "@/lib/api";
import {
  REGISTRATION_PCT_DEFAULT,
  auctioneerFeePctFor,
  itbiPctFor,
} from "@/lib/opportunity-math";
import { formatBRL, formatPct } from "@/lib/utils";

const RENOVATION_OPTIONS: { value: RenovationLevel; label: string }[] = [
  { value: "none", label: "Nenhuma" },
  { value: "basic", label: "Básica (R$ 500/m²)" },
  { value: "moderate", label: "Moderada (R$ 1.000/m²)" },
  { value: "full", label: "Completa (R$ 1.500/m²)" },
  { value: "premium", label: "Premium (R$ 2.500/m²)" },
];

/** Converte fração (0.05) ↔ % editável (5). null/empty quando vazio. */
function pctFracToInputStr(frac: number | null | undefined): string {
  if (frac == null) return "";
  return String(Math.round(frac * 1_000_000) / 10_000);
}
function pctInputStrToFrac(s: string): number | null {
  const t = s.trim();
  if (t === "") return null;
  const n = Number(t.replace(",", "."));
  if (!Number.isFinite(n) || n < 0) return null;
  return n / 100;
}

export function OpportunityForm({
  input,
  onChange,
  property,
  assumptions,
}: {
  input: OpportunityInput;
  onChange: (next: OpportunityInput) => void;
  property: Property;
  assumptions: OpportunityAssumptions;
}) {
  const set = <K extends keyof OpportunityInput>(
    key: K,
    value: OpportunityInput[K],
  ) => onChange({ ...input, [key]: value });

  // Defaults "reais" (sem override) — para o placeholder e o subtítulo.
  const itbiInfo = itbiPctFor(property.city, property.state);
  const itbiDefault = itbiInfo.pct;
  const itbiDefaultLabel = itbiInfo.exact
    ? "tabela do município"
    : "default de mercado";
  const auctioneerDefault = auctioneerFeePctFor(
    property.auctioneer_fee_pct,
    null,
  );
  const auctioneerDefaultLabel =
    property.auctioneer_fee_pct != null
      ? "do edital"
      : "default de mercado";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Parâmetros da análise</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Tipo de comprador */}
        <div className="space-y-2">
          <Label>Comprador</Label>
          <div className="flex gap-2">
            {(["PF", "PJ"] as const).map((bt) => (
              <button
                key={bt}
                type="button"
                onClick={() => set("buyer_type", bt)}
                className={`flex-1 rounded-md border px-3 py-2 text-sm transition-colors ${
                  input.buyer_type === bt
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border hover:bg-muted"
                }`}
              >
                {bt}
              </button>
            ))}
          </div>
          {input.buyer_type === "PJ" && (
            <p className="text-[11px] text-amber-700 dark:text-amber-400">
              Estimativa: tributação simplificada (Lucro Presumido ≈ 6,5%
              sobre venda). Consulte seu contador.
            </p>
          )}
        </div>

        {/* ROI alvo */}
        <div className="space-y-1">
          <Label htmlFor="target_roi">
            ROI líquido alvo: {formatPct(input.target_net_roi_pct)}
          </Label>
          <input
            id="target_roi"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={input.target_net_roi_pct}
            onChange={(e) =>
              set("target_net_roi_pct", Number(e.target.value))
            }
            className="w-full"
          />
        </div>

        {/* Lance */}
        <div className="space-y-1.5">
          <Label htmlFor="bid_amount">Lance (R$)</Label>
          <Input
            id="bid_amount"
            type="number"
            min={0}
            value={input.bid_amount}
            onChange={(e) =>
              set("bid_amount", Number(e.target.value || 0))
            }
          />
          {/* Atalhos: 1ª/2ª praça preenchem o lance automaticamente */}
          {(property.minimum_bid_first != null ||
            property.minimum_bid_second != null) && (
            <div className="flex flex-wrap gap-1.5">
              {property.minimum_bid_first != null && (
                <button
                  type="button"
                  onClick={() =>
                    set("bid_amount", property.minimum_bid_first ?? 0)
                  }
                  className={`flex-1 rounded-md border px-2 py-1 text-[11px] transition-colors ${
                    input.bid_amount === property.minimum_bid_first
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-muted"
                  }`}
                  title="Usar valor da 1ª praça"
                >
                  1ª praça <br />
                  <span className="font-medium">
                    {formatBRL(property.minimum_bid_first)}
                  </span>
                </button>
              )}
              {property.minimum_bid_second != null && (
                <button
                  type="button"
                  onClick={() =>
                    set("bid_amount", property.minimum_bid_second ?? 0)
                  }
                  className={`flex-1 rounded-md border px-2 py-1 text-[11px] transition-colors ${
                    input.bid_amount === property.minimum_bid_second
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-muted"
                  }`}
                  title="Usar valor da 2ª praça"
                >
                  2ª praça <br />
                  <span className="font-medium">
                    {formatBRL(property.minimum_bid_second)}
                  </span>
                </button>
              )}
            </div>
          )}
        </div>

        {/* Valor de venda estimado (override do realista) */}
        <div className="space-y-1">
          <Label htmlFor="sale_price">Valor de venda estimado (R$)</Label>
          <Input
            id="sale_price"
            type="number"
            min={0}
            placeholder="Use a CMA (deixe vazio)"
            value={
              input.sale_price_override != null
                ? input.sale_price_override
                : ""
            }
            onChange={(e) => {
              const raw = e.target.value.trim();
              set(
                "sale_price_override",
                raw === "" ? null : Number(raw),
              );
            }}
          />
          <p className="text-[11px] text-muted-foreground">
            Vazio = usar a avaliação de mercado (CMA). Quando preenchido,
            cenários pessimista/otimista ficam ±10% deste valor.
          </p>
        </div>

        {/* Reforma */}
        <div className="space-y-1">
          <Label htmlFor="renovation">Nível da reforma</Label>
          <select
            id="renovation"
            value={input.renovation_level}
            onChange={(e) =>
              set("renovation_level", e.target.value as RenovationLevel)
            }
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {RENOVATION_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {property.area_total_m2 != null && (
            <p className="text-[11px] text-muted-foreground">
              Área considerada: {property.area_total_m2} m²
            </p>
          )}
        </div>

        {/* IPTU em atraso */}
        <div className="space-y-1">
          <Label htmlFor="iptu">IPTU em atraso (R$)</Label>
          <Input
            id="iptu"
            type="number"
            min={0}
            value={input.iptu_arrears}
            onChange={(e) =>
              set("iptu_arrears", Number(e.target.value || 0))
            }
          />
          {property.iptu_arrears != null && (
            <p className="text-[11px] text-muted-foreground">
              Edital: R$ {property.iptu_arrears.toLocaleString("pt-BR")}
            </p>
          )}
        </div>

        {/* Condomínio em atraso */}
        <div className="space-y-1">
          <Label htmlFor="condo">Condomínio em atraso (R$)</Label>
          <Input
            id="condo"
            type="number"
            min={0}
            value={input.condo_arrears}
            onChange={(e) =>
              set("condo_arrears", Number(e.target.value || 0))
            }
          />
          {property.condo_arrears != null && (
            <p className="text-[11px] text-muted-foreground">
              Edital: R$ {property.condo_arrears.toLocaleString("pt-BR")}
            </p>
          )}
        </div>

        {/* Outros custos */}
        <div className="space-y-1">
          <Label htmlFor="other">Outros custos (R$)</Label>
          <Input
            id="other"
            type="number"
            min={0}
            value={input.other_costs}
            onChange={(e) =>
              set("other_costs", Number(e.target.value || 0))
            }
          />
          <p className="text-[11px] text-muted-foreground">
            Desocupação, advogado, mudança, etc.
          </p>
        </div>

        {/* Overrides de alíquotas */}
        <div className="space-y-3 rounded-md border border-dashed p-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Alíquotas (deixe vazio para usar o padrão)
          </div>

          <PctOverrideField
            id="auc_pct"
            label="Comissão do leiloeiro"
            value={input.auctioneer_fee_pct_override ?? null}
            defaultValue={auctioneerDefault}
            defaultSourceLabel={auctioneerDefaultLabel}
            onChange={(frac) => set("auctioneer_fee_pct_override", frac)}
          />

          <PctOverrideField
            id="itbi_pct"
            label="ITBI"
            value={input.itbi_pct_override ?? null}
            defaultValue={itbiDefault}
            defaultSourceLabel={itbiDefaultLabel}
            onChange={(frac) => set("itbi_pct_override", frac)}
          />

          <PctOverrideField
            id="reg_pct"
            label="Registro"
            value={input.registration_pct_override ?? null}
            defaultValue={REGISTRATION_PCT_DEFAULT}
            defaultSourceLabel="default de mercado"
            onChange={(frac) => set("registration_pct_override", frac)}
          />
        </div>

        {/* Snapshot das premissas */}
        <details className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
          <summary className="cursor-pointer font-medium text-foreground">
            Premissas usadas
          </summary>
          <ul className="mt-2 space-y-1">
            <li>
              ITBI: {formatPct(assumptions.itbi_pct)} ({assumptions.itbi_source})
            </li>
            <li>Registro: {formatPct(assumptions.registration_pct)}</li>
            <li>
              Comissão leiloeiro: {formatPct(assumptions.auctioneer_fee_pct)} (
              {assumptions.auctioneer_fee_source})
            </li>
            <li>Corretagem venda: {formatPct(assumptions.realtor_fee_pct)}</li>
            <li>
              IR: {formatPct(assumptions.income_tax_pct)} sobre{" "}
              {assumptions.income_tax_basis === "sale_price"
                ? "venda (PJ)"
                : "ganho (PF)"}
            </li>
            <li>
              Reforma: R${" "}
              {assumptions.renovation_per_m2.toLocaleString("pt-BR")}/m²
            </li>
          </ul>
        </details>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// PctOverrideField — campo numérico em % com placeholder mostrando o default
// =============================================================================
function PctOverrideField({
  id,
  label,
  value,
  defaultValue,
  defaultSourceLabel,
  onChange,
}: {
  id: string;
  label: string;
  /** Valor atual em FRAÇÃO (0.05 = 5%) ou null. */
  value: number | null;
  /** Valor que seria usado se este input fosse vazio (em fração). */
  defaultValue: number;
  /** Texto curto de origem do default (ex.: "tabela do município"). */
  defaultSourceLabel: string | null;
  onChange: (frac: number | null) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id} className="text-xs">
          {label}
        </Label>
        {value != null && (
          <button
            type="button"
            className="text-[10px] text-muted-foreground underline hover:text-primary"
            onClick={() => onChange(null)}
          >
            limpar
          </button>
        )}
      </div>
      <div className="relative">
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          min={0}
          step={0.1}
          placeholder={`${(defaultValue * 100).toFixed(2).replace(/\.?0+$/, "")}`}
          value={pctFracToInputStr(value)}
          onChange={(e) => onChange(pctInputStrToFrac(e.target.value))}
          className="pr-7"
        />
        <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
          %
        </span>
      </div>
      <p className="text-[10px] text-muted-foreground">
        Padrão: {formatPct(defaultValue)}
        {defaultSourceLabel && ` · ${defaultSourceLabel}`}
      </p>
    </div>
  );
}

