"use client";

import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { EmptyState } from "@/components/EmptyState";
import type { Property } from "@/lib/api";
import { isAuctionExpired, normalizeText } from "@/lib/utils";

import { PropertiesFilterBar } from "./PropertiesFilterBar";
import { PropertyCard } from "./PropertyCard";
import { PropertyMap } from "./PropertyMap";

/** Campos do imóvel que entram no índice de busca livre. */
function buildSearchHaystack(p: Property): string {
  return normalizeText(
    [
      p.title,
      p.property_type,
      p.address_full,
      p.street,
      p.neighborhood,
      p.city,
      p.state,
      p.postal_code,
      p.complement,
    ]
      .filter(Boolean)
      .join(" "),
  );
}

export function PropertiesView({
  properties,
  nowIso,
}: {
  properties: Property[];
  /** ISO timestamp do servidor — usado para classificar leilões
   *  encerrados sem causar hydration mismatch. */
  nowIso: string;
}) {
  // Lista local (otimista) — sincroniza com a do servidor sempre que o
  // Server Component recarregar (ex.: após router.refresh()).
  const [items, setItems] = useState<Property[]>(properties);
  useEffect(() => {
    setItems(properties);
  }, [properties]);

  const [query, setQuery] = useState<string>("");
  const [showExpired, setShowExpired] = useState<boolean>(false);

  // Marca expiração uma vez por item, evita recomputar a cada render.
  const annotated = useMemo(
    () => items.map((p) => ({ p, expired: isAuctionExpired(p, nowIso) })),
    [items, nowIso],
  );
  const expiredCount = useMemo(
    () => annotated.filter((a) => a.expired).length,
    [annotated],
  );

  // Aplica filtros: busca + toggle encerrados.
  const visible = useMemo(() => {
    const q = normalizeText(query);
    return annotated.filter(({ p, expired }) => {
      if (!showExpired && expired) return false;
      if (!q) return true;
      return buildSearchHaystack(p).includes(q);
    });
  }, [annotated, query, showExpired]);

  // Seleção: começa com o primeiro item visível.
  const [selectedId, setSelectedId] = useState<string | null>(
    properties[0]?.id ?? null,
  );

  // Se o item selecionado some da lista visível (filtro/busca/exclusão),
  // pula para o primeiro visível para manter o mapa coerente.
  useEffect(() => {
    if (visible.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!visible.some(({ p }) => p.id === selectedId)) {
      setSelectedId(visible[0].p.id);
    }
  }, [visible, selectedId]);

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
    setItems((curr) => curr.filter((p) => p.id !== id));
    setSelectedId((curr) => (curr === id ? null : curr));
    startTransition(() => router.refresh());
  }

  // Subset de itens visíveis para alimentar o mapa (mantém os marcadores
  // alinhados aos cards filtrados).
  const visibleProperties = visible.map(({ p }) => p);

  return (
    <div className="space-y-4">
      <PropertiesFilterBar
        query={query}
        onQueryChange={setQuery}
        showExpired={showExpired}
        onShowExpiredChange={setShowExpired}
        totalCount={items.length}
        visibleCount={visible.length}
        expiredCount={expiredCount}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(360px,420px)_1fr]">
        {/* Lista de cards */}
        <div className="space-y-3 lg:max-h-[calc(100vh-220px)] lg:overflow-y-auto lg:pr-2">
          {visible.length === 0 ? (
            <EmptyState
              icon={Search}
              title="Nenhum imóvel encontrado"
              description={
                query
                  ? `Nada combina com "${query}". Tente outros termos ou limpe a busca.`
                  : "Ajuste os filtros para ver os imóveis."
              }
            />
          ) : (
            visible.map(({ p, expired }) => (
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
                  expired={expired}
                  onSelect={(id) =>
                    setSelectedId((curr) => (curr === id ? null : id))
                  }
                  onDeleted={handleDeleted}
                />
              </div>
            ))
          )}
        </div>

        {/* Mapa */}
        <div className="lg:sticky lg:top-6 lg:h-[calc(100vh-220px)]">
          <PropertyMap
            properties={visibleProperties}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>
      </div>
    </div>
  );
}
