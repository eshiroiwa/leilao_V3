import { BarChart3, FileText, Sparkles } from "lucide-react";
import { notFound } from "next/navigation";
import type { Route } from "next";

import { TabsNav } from "@/components/ui/tabs";
import { api, type Property } from "@/lib/api";

import { PropertyHero } from "./_components/PropertyHero";

export const dynamic = "force-dynamic";

export default async function PropertyLayout({
  params,
  children,
}: LayoutProps<"/properties/[id]">) {
  const { id } = await params;

  let property: Property | null = null;
  try {
    const list = await api.listProperties({ limit: 200 });
    property = list.find((p) => p.id === id) ?? null;
  } catch {
    property = null;
  }

  if (!property) notFound();

  const base = `/properties/${encodeURIComponent(id)}`;

  return (
    <div className="space-y-6">
      <PropertyHero property={property} />

      <TabsNav
        items={[
          {
            href: base as Route,
            label: "Visão geral",
            icon: FileText,
            match: (p) => p === base,
          },
          {
            href: `${base}/valuation` as Route,
            label: "Avaliação",
            icon: BarChart3,
            match: (p) => p.startsWith(`${base}/valuation`),
          },
          {
            href: `${base}/opportunity` as Route,
            label: "Oportunidade",
            icon: Sparkles,
            match: (p) => p.startsWith(`${base}/opportunity`),
          },
        ]}
      />

      <div>{children}</div>
    </div>
  );
}
