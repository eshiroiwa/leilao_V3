"use client";

import { ExternalLink } from "lucide-react";

import type { ValuationComparable } from "@/lib/api";

export function ComparablesTable({ comparables }: { comparables: ValuationComparable[] }) {
  if (comparables.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-muted-foreground">
        Nenhum comparável a exibir.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="bg-muted/40">
          <tr className="text-left">
            <th className="px-3 py-2">#</th>
            <th className="px-3 py-2">Anúncio</th>
            <th className="px-3 py-2 text-right">Área</th>
            <th className="px-3 py-2 text-right">Quartos / Vagas</th>
            <th className="px-3 py-2 text-right">Distância</th>
            <th className="px-3 py-2 text-right">Preço</th>
            <th className="px-3 py-2 text-right">R$/m²</th>
            <th className="px-3 py-2 text-right">Sim.</th>
            <th className="px-3 py-2 text-right">Peso</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {comparables.map((c, i) => {
            const l = c.listings;
            const ppm2 =
              l.listed_price && l.area_total_m2
                ? l.listed_price / l.area_total_m2
                : null;
            return (
              <tr
                key={l.id}
                className={c.used ? "" : "opacity-50"}
              >
                <td className="px-3 py-2 font-mono">{i + 1}</td>
                <td className="px-3 py-2">
                  <a
                    href={l.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-blue-600 hover:underline"
                  >
                    {l.neighborhood ?? l.city ?? l.source}{" "}
                    <ExternalLink className="size-3" />
                  </a>
                  <div className="text-[10px] text-muted-foreground">
                    {l.source} · geo {l.geocoding_confidence ?? "?"}
                  </div>
                </td>
                <td className="px-3 py-2 text-right">
                  {l.area_total_m2 ? `${l.area_total_m2} m²` : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  {(l.bedrooms ?? "—")} / {(l.parking_spaces ?? "—")}
                </td>
                <td className="px-3 py-2 text-right">
                  {c.distance_m != null ? `${Math.round(c.distance_m)} m` : "—"}
                </td>
                <td className="px-3 py-2 text-right font-medium">
                  {fmt(l.listed_price)}
                </td>
                <td className="px-3 py-2 text-right">{fmt(ppm2)}</td>
                <td className="px-3 py-2 text-right">
                  {c.similarity_score != null ? c.similarity_score.toFixed(2) : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  {c.weight != null ? c.weight.toFixed(3) : "—"}
                </td>
                <td className="px-3 py-2">
                  {c.used ? (
                    <span className="text-green-700">usado</span>
                  ) : (
                    <span title={c.rejection_reason ?? ""} className="text-destructive">
                      rejeitado
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function fmt(v: number | null | undefined): string {
  if (v == null) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(v);
}
