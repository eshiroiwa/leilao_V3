"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import type { Property } from "@/lib/api";

import { PropertyCard } from "./PropertyCard";
import { PropertyMap } from "./PropertyMap";

export function PropertiesView({ properties }: { properties: Property[] }) {
  // Lista local (otimista) — começa com a do servidor e é re-sincronizada
  // sempre que o Server Component recarregar (ex.: após router.refresh()).
  const [items, setItems] = useState<Property[]>(properties);
  useEffect(() => {
    setItems(properties);
  }, [properties]);

  const [selectedId, setSelectedId] = useState<string | null>(properties[0]?.id ?? null);
  const cardRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const router = useRouter();
  const [, startTransition] = useTransition();

  // Quando a seleção muda, rola o card pra dentro da viewport.
  useEffect(() => {
    if (!selectedId) return;
    const el = cardRefs.current.get(selectedId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [selectedId]);

  function handleDeleted(id: string) {
    // 1) atualização otimista — some imediatamente da UI
    setItems((curr) => curr.filter((p) => p.id !== id));
    setSelectedId((curr) => (curr === id ? null : curr));
    // 2) revalida a página no servidor (busca a lista de novo do backend)
    startTransition(() => router.refresh());
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(360px,420px)_1fr]">
      {/* Sidebar: lista de cards (scrollável) */}
      <div className="space-y-3 lg:max-h-[calc(100vh-180px)] lg:overflow-y-auto lg:pr-2">
        {items.map((p) => (
          <div
            key={p.id}
            ref={(el) => {
              if (el) cardRefs.current.set(p.id, el);
              else cardRefs.current.delete(p.id);
            }}
          >
            <PropertyCard
              property={p}
              selected={p.id === selectedId}
              onSelect={(id) => setSelectedId((curr) => (curr === id ? null : id))}
              onDeleted={handleDeleted}
            />
          </div>
        ))}
      </div>

      {/* Mapa: sticky no desktop */}
      <div className="lg:sticky lg:top-6 lg:h-[calc(100vh-180px)]">
        <PropertyMap properties={items} selectedId={selectedId} onSelect={setSelectedId} />
      </div>
    </div>
  );
}
