"use client";

import { BarChart3, FileText, Sparkles } from "lucide-react";
import type { Route } from "next";

import { TabsNav } from "@/components/ui/tabs";

export function PropertyTabs({ propertyId }: { propertyId: string }) {
  const base = `/properties/${encodeURIComponent(propertyId)}`;

  return (
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
  );
}
