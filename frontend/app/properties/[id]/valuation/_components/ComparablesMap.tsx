"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  GoogleMap,
  InfoWindowF,
  MarkerF,
  PolylineF,
  useJsApiLoader,
} from "@react-google-maps/api";

import type { Property, ValuationComparable } from "@/lib/api";

const containerStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
  borderRadius: "0.75rem",
};

// =============================================================================
// Ícones (factories — `google` global só existe depois do isLoaded)
// =============================================================================

/** Pin estilo Google Maps clássico (gota com pingo branco no centro). */
function buildTargetPin(): google.maps.Icon {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="34" height="46" viewBox="0 0 34 46">
    <defs>
      <filter id="s" x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="1.5" stdDeviation="1.5" flood-opacity="0.35"/>
      </filter>
    </defs>
    <path filter="url(#s)" d="M17 1.5C9 1.5 2.5 8 2.5 16c0 11.5 14.5 28 14.5 28s14.5-16.5 14.5-28C31.5 8 25 1.5 17 1.5z"
      fill="#dc2626" stroke="#ffffff" stroke-width="2.5"/>
    <circle cx="17" cy="16" r="5.5" fill="#ffffff"/>
  </svg>`;
  return {
    url: `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`,
    scaledSize: new google.maps.Size(34, 46),
    anchor: new google.maps.Point(17, 44), // ponta do pin
    labelOrigin: new google.maps.Point(17, 16),
  };
}

/** Círculo colorido com borda branca — usado para comparables individuais. */
function buildCompIcon(color: string, big = false): google.maps.Symbol {
  return {
    path: google.maps.SymbolPath.CIRCLE,
    scale: big ? 13 : 11,
    fillColor: color,
    fillOpacity: 1,
    strokeColor: "#ffffff",
    strokeWeight: 2.5,
  };
}

/** Pin "cluster" (vários comparables na mesma posição). */
function buildClusterIcon(count: number): google.maps.Icon {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44">
    <defs>
      <filter id="cs" x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="1.5" stdDeviation="1.5" flood-opacity="0.35"/>
      </filter>
    </defs>
    <circle filter="url(#cs)" cx="22" cy="22" r="18" fill="#2563eb" stroke="#ffffff" stroke-width="3"/>
    <text x="22" y="22" text-anchor="middle" dominant-baseline="central"
      font-family="system-ui,-apple-system,Segoe UI,sans-serif"
      font-size="${count > 99 ? 13 : 15}" font-weight="700" fill="#ffffff">${count}</text>
  </svg>`;
  return {
    url: `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`,
    scaledSize: new google.maps.Size(44, 44),
    anchor: new google.maps.Point(22, 22),
  };
}

// =============================================================================
// Spiderfier helpers
// =============================================================================

/** Comparable + índice global (1..N) preservado para a UI. */
type IndexedComp = ValuationComparable & { _idx: number };

/** Grupo de comparables empilhados (mesma lat/lng arredondada). */
type MarkerGroup = {
  key: string;
  items: IndexedComp[];
  center: google.maps.LatLngLiteral;
};

/**
 * Agrupa comparables por posição (precisão ~1 metro = 5 casas decimais).
 * Anúncios com `APPROXIMATE` geocoding caem no MESMO ponto (centroide
 * do bairro), então o agrupamento aqui é o cenário comum, não exceção.
 */
function groupByPosition(comps: IndexedComp[]): MarkerGroup[] {
  const map = new Map<string, IndexedComp[]>();
  comps.forEach((c) => {
    const lat = c.listings.latitude as number;
    const lng = c.listings.longitude as number;
    const key = `${lat.toFixed(5)},${lng.toFixed(5)}`;
    const arr = map.get(key);
    if (arr) arr.push(c);
    else map.set(key, [c]);
  });
  return Array.from(map.entries()).map(([key, items]) => ({
    key,
    items,
    center: {
      lat: items[0].listings.latitude as number,
      lng: items[0].listings.longitude as number,
    },
  }));
}

/**
 * Distribui N markers num círculo de ``radiusPx`` pixels ao redor de ``center``.
 * Usa a curvatura local da Terra para converter pixels → graus, garantindo que
 * o "leque" tem o mesmo tamanho visual em qualquer zoom.
 *
 * Para grupos grandes (>10), usamos uma espiral em vez de um círculo único
 * (evita sobreposição dos próprios pinos expandidos).
 */
function spiderPositions(
  center: google.maps.LatLngLiteral,
  count: number,
  zoom: number,
): google.maps.LatLngLiteral[] {
  if (count <= 1) return [center];

  // metros por pixel na latitude do centro (fórmula padrão Web Mercator).
  const metersPerPx =
    (156543.03392 * Math.cos((center.lat * Math.PI) / 180)) /
    Math.pow(2, zoom);

  const baseRadiusPx = 56;
  // Anel duplo se houver muitos pontos.
  const useTwoRings = count > 10;
  const positions: google.maps.LatLngLiteral[] = [];

  if (!useTwoRings) {
    const radiusM = baseRadiusPx * metersPerPx;
    for (let i = 0; i < count; i++) {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2; // começa em "12h"
      positions.push(offsetLatLng(center, radiusM, angle));
    }
  } else {
    const inner = Math.ceil(count * 0.4);
    const outer = count - inner;
    for (let i = 0; i < inner; i++) {
      const angle = (2 * Math.PI * i) / inner - Math.PI / 2;
      positions.push(offsetLatLng(center, baseRadiusPx * metersPerPx, angle));
    }
    for (let i = 0; i < outer; i++) {
      const angle = (2 * Math.PI * i) / outer - Math.PI / 2 + Math.PI / outer;
      positions.push(
        offsetLatLng(center, baseRadiusPx * 1.85 * metersPerPx, angle),
      );
    }
  }
  return positions;
}

function offsetLatLng(
  center: google.maps.LatLngLiteral,
  meters: number,
  angleRad: number,
): google.maps.LatLngLiteral {
  const earthR = 6378137;
  const dLat = ((meters * Math.cos(angleRad)) / earthR) * (180 / Math.PI);
  const dLng =
    ((meters * Math.sin(angleRad)) /
      (earthR * Math.cos((center.lat * Math.PI) / 180))) *
    (180 / Math.PI);
  return { lat: center.lat + dLat, lng: center.lng + dLng };
}

// =============================================================================
// Componente principal
// =============================================================================

export function ComparablesMap({
  target,
  comparables,
}: {
  target: Property;
  comparables: ValuationComparable[];
}) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";
  const { isLoaded, loadError } = useJsApiLoader({
    id: "leilao-ia-google-maps",
    googleMapsApiKey: apiKey,
    language: "pt-BR",
    region: "BR",
  });

  const mapRef = useRef<google.maps.Map | null>(null);
  const [zoom, setZoom] = useState(14);
  const [openMarker, setOpenMarker] = useState<string | null>(null); // listing.id | "TARGET"
  const [expandedGroupKey, setExpandedGroupKey] = useState<string | null>(null);

  // Comparables válidos com índice global (preserva 1..N visível).
  const indexed: IndexedComp[] = useMemo(
    () =>
      comparables
        .map((c, i) => ({ ...c, _idx: i + 1 }))
        .filter(
          (c) =>
            c.listings &&
            typeof c.listings.latitude === "number" &&
            typeof c.listings.longitude === "number" &&
            Number.isFinite(c.listings.latitude) &&
            Number.isFinite(c.listings.longitude),
        ),
    [comparables],
  );

  const groups = useMemo(() => groupByPosition(indexed), [indexed]);

  // Fit bounds em alvo + comparáveis válidos.
  useEffect(() => {
    if (!isLoaded || !mapRef.current) return;
    if (target.latitude == null || target.longitude == null) return;
    const bounds = new google.maps.LatLngBounds();
    bounds.extend({ lat: target.latitude, lng: target.longitude });
    indexed.forEach((c) => {
      bounds.extend({
        lat: c.listings.latitude as number,
        lng: c.listings.longitude as number,
      });
    });
    mapRef.current.fitBounds(bounds, 64);
  }, [isLoaded, target.latitude, target.longitude, indexed]);

  if (!apiKey) {
    return (
      <Empty>
        Defina <code>NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code> em{" "}
        <code>frontend/.env.local</code>.
      </Empty>
    );
  }
  if (loadError) return <Empty>Falha ao carregar o Google Maps.</Empty>;
  if (!isLoaded) return <Empty>Carregando mapa…</Empty>;
  if (target.latitude == null || target.longitude == null) {
    return <Empty>Imóvel-alvo sem geolocalização.</Empty>;
  }

  const targetPos = { lat: target.latitude, lng: target.longitude };
  const targetIcon = buildTargetPin();

  return (
    <div className="relative h-full">
      <GoogleMap
        mapContainerStyle={containerStyle}
        center={targetPos}
        zoom={zoom}
        onLoad={(m) => {
          mapRef.current = m;
        }}
        onUnmount={() => {
          mapRef.current = null;
        }}
        onZoomChanged={() => {
          if (mapRef.current) setZoom(mapRef.current.getZoom() ?? 14);
        }}
        onClick={() => {
          setOpenMarker(null);
          setExpandedGroupKey(null);
        }}
        options={{
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
          clickableIcons: false,
        }}
      >
        {/* Imóvel-alvo (pin Google Maps clássico) */}
        <MarkerF
          position={targetPos}
          icon={targetIcon}
          zIndex={9999}
          title={target.title ?? "Imóvel do leilão"}
          onClick={() => setOpenMarker("TARGET")}
        />
        {openMarker === "TARGET" && (
          <InfoWindowF
            position={targetPos}
            onCloseClick={() => setOpenMarker(null)}
            options={{ pixelOffset: new google.maps.Size(0, -40) }}
          >
            <div className="space-y-1 p-1 text-sm">
              <div className="font-semibold text-neutral-900">
                {target.title ?? "Imóvel do leilão"}
              </div>
              <div className="text-xs text-neutral-600">
                {target.address_full}
              </div>
              <div className="text-xs text-neutral-700">
                <span className="font-medium">Avaliação:</span>{" "}
                {fmtBRL(target.appraisal_value)}
              </div>
              {target.area_total_m2 != null && (
                <div className="text-xs text-neutral-700">
                  <span className="font-medium">Área:</span>{" "}
                  {target.area_total_m2} m²
                </div>
              )}
            </div>
          </InfoWindowF>
        )}

        {/* Grupos: cluster colapsado OU pinos individuais (eventualmente
            distribuídos em "aranha" se o grupo está expandido) */}
        {groups.map((g) => {
          const isExpanded = expandedGroupKey === g.key;
          const isCluster = g.items.length > 1;

          // Caso 1 — grupo com 1 só ponto: render direto.
          if (!isCluster) {
            return (
              <CompMarker
                key={g.key}
                comp={g.items[0]}
                position={g.center}
                isOpen={openMarker === g.items[0].listings.id}
                onSelect={() => setOpenMarker(g.items[0].listings.id)}
                onClose={() => setOpenMarker(null)}
              />
            );
          }

          // Caso 2 — cluster colapsado: 1 marker azul com badge "+N".
          if (!isExpanded) {
            return (
              <MarkerF
                key={g.key}
                position={g.center}
                icon={buildClusterIcon(g.items.length)}
                zIndex={500}
                title={`${g.items.length} anúncios neste ponto — clique para expandir`}
                onClick={() => {
                  setOpenMarker(null);
                  setExpandedGroupKey(g.key);
                }}
              />
            );
          }

          // Caso 3 — cluster EXPANDIDO: distribui em círculo + linhas até o centro.
          const positions = spiderPositions(g.center, g.items.length, zoom);
          return (
            <span key={g.key}>
              {/* Linhas de conexão (raios da "aranha") */}
              {positions.map((p, i) => (
                <PolylineF
                  key={`${g.key}-line-${i}`}
                  path={[g.center, p]}
                  options={{
                    strokeColor: "#2563eb",
                    strokeOpacity: 0.5,
                    strokeWeight: 1.5,
                    clickable: false,
                    zIndex: 400,
                  }}
                />
              ))}
              {/* Pininho central indicando o ponto original */}
              <MarkerF
                position={g.center}
                icon={{
                  path: google.maps.SymbolPath.CIRCLE,
                  scale: 5,
                  fillColor: "#2563eb",
                  fillOpacity: 1,
                  strokeColor: "#ffffff",
                  strokeWeight: 2,
                }}
                zIndex={401}
                title="Posição original (clique fora para colapsar)"
                onClick={() => setExpandedGroupKey(null)}
              />
              {/* Markers expandidos */}
              {g.items.map((c, i) => (
                <CompMarker
                  key={c.listings.id}
                  comp={c}
                  position={positions[i]}
                  isOpen={openMarker === c.listings.id}
                  onSelect={() => setOpenMarker(c.listings.id)}
                  onClose={() => setOpenMarker(null)}
                />
              ))}
            </span>
          );
        })}
      </GoogleMap>

      {/* Legenda + ação para colapsar tudo */}
      <Legend
        nUsed={indexed.filter((c) => c.used).length}
        nRejected={indexed.filter((c) => !c.used).length}
        nClusters={groups.filter((g) => g.items.length > 1).length}
        anyExpanded={expandedGroupKey !== null}
        onCollapseAll={() => {
          setExpandedGroupKey(null);
          setOpenMarker(null);
        }}
      />
    </div>
  );
}

// =============================================================================
// Subcomponentes
// =============================================================================

function CompMarker({
  comp,
  position,
  isOpen,
  onSelect,
  onClose,
}: {
  comp: IndexedComp;
  position: google.maps.LatLngLiteral;
  isOpen: boolean;
  onSelect: () => void;
  onClose: () => void;
}) {
  const ppm2 =
    comp.listings.listed_price && comp.listings.area_total_m2
      ? comp.listings.listed_price / comp.listings.area_total_m2
      : null;

  return (
    <span>
      <MarkerF
        position={position}
        icon={buildCompIcon(comp.used ? "#16a34a" : "#9ca3af")}
        opacity={comp.used ? 1 : 0.65}
        zIndex={comp.used ? 600 : 550}
        label={{
          text: String(comp._idx),
          color: "#ffffff",
          fontSize: "11px",
          fontWeight: "700",
        }}
        title={`#${comp._idx} · ${fmtBRL(comp.listings.listed_price)}`}
        onClick={onSelect}
      />
      {isOpen && (
        <InfoWindowF
          position={position}
          onCloseClick={onClose}
          options={{ pixelOffset: new google.maps.Size(0, -22) }}
        >
          <div className="space-y-1 p-1 text-sm">
            <div className="font-semibold text-neutral-900">
              Comparável #{comp._idx}{" "}
              {!comp.used && (
                <span className="text-xs font-normal text-red-600">
                  (rejeitado)
                </span>
              )}
            </div>
            <div className="text-xs text-neutral-600">
              {comp.listings.neighborhood ?? "—"} ·{" "}
              {comp.listings.city ?? "—"}/{comp.listings.state ?? "—"}
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-neutral-700">
              <span>Preço</span>
              <span className="text-right font-medium">
                {fmtBRL(comp.listings.listed_price)}
              </span>
              <span>R$/m²</span>
              <span className="text-right">{fmtBRL(ppm2)}</span>
              <span>Área</span>
              <span className="text-right">
                {comp.listings.area_total_m2 ?? "—"} m²
              </span>
              <span>Quartos / Vagas</span>
              <span className="text-right">
                {comp.listings.bedrooms ?? "—"} /{" "}
                {comp.listings.parking_spaces ?? "—"}
              </span>
              <span>Distância</span>
              <span className="text-right">
                {comp.distance_m != null
                  ? `${Math.round(comp.distance_m)} m`
                  : "—"}
              </span>
              <span>Similaridade</span>
              <span className="text-right">
                {comp.similarity_score != null
                  ? comp.similarity_score.toFixed(2)
                  : "—"}
              </span>
            </div>
            {!comp.used && comp.rejection_reason && (
              <div className="text-xs italic text-red-600">
                Motivo: {comp.rejection_reason}
              </div>
            )}
            <a
              href={comp.listings.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-block pt-1 text-xs font-medium text-blue-600 hover:underline"
            >
              Abrir anúncio ↗
            </a>
          </div>
        </InfoWindowF>
      )}
    </span>
  );
}

function Legend({
  nUsed,
  nRejected,
  nClusters,
  anyExpanded,
  onCollapseAll,
}: {
  nUsed: number;
  nRejected: number;
  nClusters: number;
  anyExpanded: boolean;
  onCollapseAll: () => void;
}) {
  return (
    <div className="absolute bottom-3 left-3 rounded-md border bg-white/95 px-3 py-2 text-xs shadow-md backdrop-blur">
      <div className="mb-1 font-medium text-neutral-700">Legenda</div>
      <div className="flex items-center gap-2">
        <span className="inline-block h-4 w-3 rounded-t-full bg-red-600 ring-1 ring-white" />
        <span>Imóvel do leilão</span>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span className="inline-block size-3 rounded-full border-2 border-white bg-green-600 ring-1 ring-neutral-300" />
        <span>Comparável usado ({nUsed})</span>
      </div>
      {nRejected > 0 && (
        <div className="mt-1 flex items-center gap-2">
          <span className="inline-block size-3 rounded-full border-2 border-white bg-neutral-400 ring-1 ring-neutral-300" />
          <span>Rejeitado ({nRejected})</span>
        </div>
      )}
      {nClusters > 0 && (
        <div className="mt-1 flex items-center gap-2">
          <span className="inline-flex size-4 items-center justify-center rounded-full border-2 border-white bg-blue-600 text-[9px] font-bold text-white ring-1 ring-neutral-300">
            N
          </span>
          <span>Vários no mesmo ponto ({nClusters})</span>
        </div>
      )}
      {anyExpanded && (
        <button
          type="button"
          onClick={onCollapseAll}
          className="mt-2 w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-[11px] font-medium text-neutral-700 transition hover:bg-neutral-100"
        >
          Recolher grupo
        </button>
      )}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full min-h-[300px] items-center justify-center rounded-xl border bg-muted/20 p-6 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

function fmtBRL(v: number | null | undefined): string {
  if (v == null) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(v);
}
