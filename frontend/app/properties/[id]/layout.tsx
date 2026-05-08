import { notFound } from "next/navigation";

import { api, type Property } from "@/lib/api";

import { PropertyHero } from "./_components/PropertyHero";
import { PropertyTabs } from "./_components/PropertyTabs";

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

  return (
    <div className="space-y-6">
      <PropertyHero property={property} />
      <PropertyTabs propertyId={id} />
      <div>{children}</div>
    </div>
  );
}
