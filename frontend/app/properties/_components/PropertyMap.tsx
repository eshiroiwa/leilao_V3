"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  GoogleMap,
  InfoWindowF,
  MarkerF,
  useJsApiLoader,
} from "@react-google-maps/api";
import { Loader2, MapPinOff } from "lucide-react";

import type { Property } from "@/lib/api";
import { formatBRL } from "@/lib/utils";

const containerStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
  minHeight: "500px",
  borderRadius: "0.75rem",
};

// Centro inicial: São Paulo (substituído ao primeiro fit/select).
const DEFAULT_CENTER = { lat: -23.5505, lng: -46.6333 };

const MAP_OPTIONS: google.maps.MapOptions = {
  disableDefaultUI: false,
  streetViewControl: false,
  mapTypeControl: false,
  fullscreenControl: true,
  zoomControl: true,
  clickableIcons: false,
};

type Geolocated = Property & { latitude: number; longitude: number };

function isGeolocated(p: Property): p is Geolocated {
  // Aceita apenas números finitos. Imóveis com status="geo_unconfirmed"
  // (validation rejected, sem CEP) chegam com null/undefined e devem
  // ficar fora do mapa para não crashar o Marker/InfoWindow do Google.
  return (
    typeof p.latitude === "number" &&
    Number.isFinite(p.latitude) &&
    typeof p.longitude === "number" &&
    Number.isFinite(p.longitude)
  );
}

export type PropertyMapProps = {
  properties: Property[];
  selectedId: string | null;
  onSelect?: (id: string | null) => void;
};

export function PropertyMap({ properties, selectedId, onSelect }: PropertyMapProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

  const { isLoaded, loadError } = useJsApiLoader({
    id: "leilao-ia-google-maps",
    googleMapsApiKey: apiKey,
    language: "pt-BR",
    region: "BR",
  });

  const mapRef = useRef<google.maps.Map | null>(null);
  const [internalSelected, setInternalSelected] = useState<string | null>(null);

  const geo = useMemo(() => properties.filter(isGeolocated), [properties]);

  const activeId = selectedId ?? internalSelected;
  const active = geo.find((p) => p.id === activeId) ?? null;

  // Fit bounds inicial ou foco no selecionado.
  useEffect(() => {
    if (!isLoaded || !mapRef.current || geo.length === 0) return;

    if (active) {
      mapRef.current.panTo({ lat: active.latitude, lng: active.longitude });
      const currentZoom = mapRef.current.getZoom() ?? 0;
      if (currentZoom < 14) mapRef.current.setZoom(15);
      return;
    }

    if (geo.length === 1) {
      mapRef.current.setCenter({ lat: geo[0].latitude, lng: geo[0].longitude });
      mapRef.current.setZoom(15);
      return;
    }

    const bounds = new google.maps.LatLngBounds();
    geo.forEach((p) => bounds.extend({ lat: p.latitude, lng: p.longitude }));
    mapRef.current.fitBounds(bounds, 64);
  }, [isLoaded, geo, active]);

  if (!apiKey) {
    return (
      <MapMessage>
        <p className="font-medium">Chave do Google Maps ausente.</p>
        <p className="text-sm text-muted-foreground">
          Defina <code>NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code> em{" "}
          <code>frontend/.env.local</code>.
        </p>
      </MapMessage>
    );
  }

  if (loadError) {
    return (
      <MapMessage>
        <p className="font-medium text-destructive">Falha ao carregar o Google Maps.</p>
        <p className="text-sm text-muted-foreground">
          Verifique se a <strong>Maps JavaScript API</strong> está habilitada no
          Google Cloud para esta chave.
        </p>
      </MapMessage>
    );
  }

  if (!isLoaded) {
    return (
      <MapMessage>
        <Loader2 className="mx-auto size-6 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Carregando mapa…</p>
      </MapMessage>
    );
  }

  if (geo.length === 0) {
    return (
      <MapMessage>
        <MapPinOff className="mx-auto size-6 text-muted-foreground" />
        <p className="font-medium">Nenhum imóvel geolocalizado ainda.</p>
        <p className="text-sm text-muted-foreground">
          Rode o agente em <code>/scrape</code> para popular o mapa.
        </p>
      </MapMessage>
    );
  }

  function handleSelect(id: string | null) {
    setInternalSelected(id);
    onSelect?.(id);
  }

  return (
    <GoogleMap
      mapContainerStyle={containerStyle}
      center={DEFAULT_CENTER}
      zoom={11}
      options={MAP_OPTIONS}
      onLoad={(m) => {
        mapRef.current = m;
      }}
      onUnmount={() => {
        mapRef.current = null;
      }}
      onClick={() => handleSelect(null)}
    >
      {geo.map((p) => {
        const isActive = p.id === activeId;
        return (
          <MarkerF
            key={p.id}
            position={{ lat: p.latitude, lng: p.longitude }}
            title={p.title ?? "Imóvel"}
            onClick={() => handleSelect(p.id)}
            animation={isActive ? google.maps.Animation.BOUNCE : undefined}
            zIndex={isActive ? 999 : undefined}
            // Marker padrão; o `BOUNCE` no selecionado já o destaca.
          />
        );
      })}

      {active && (
        <InfoWindowF
          position={{ lat: active.latitude, lng: active.longitude }}
          onCloseClick={() => handleSelect(null)}
          options={{ pixelOffset: new google.maps.Size(0, -32) }}
        >
          <div className="space-y-1 p-1 text-sm">
            <div className="font-semibold leading-tight text-neutral-900">
              {active.title ?? "Imóvel sem título"}
            </div>
            {active.address_full && (
              <div className="text-xs text-neutral-600">{active.address_full}</div>
            )}
            <div className="pt-1 text-xs text-neutral-700">
              <span className="font-medium">Avaliação:</span>{" "}
              {formatBRL(active.appraisal_value)}
            </div>
            {active.minimum_bid_first != null && (
              <div className="text-xs text-neutral-700">
                <span className="font-medium">1ª praça:</span>{" "}
                {formatBRL(active.minimum_bid_first)}
              </div>
            )}
            <a
              href={active.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-block pt-1 text-xs font-medium text-blue-600 hover:underline"
            >
              Ver fonte ↗
            </a>
          </div>
        </InfoWindowF>
      )}
    </GoogleMap>
  );
}

function MapMessage({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="flex h-full min-h-[500px] flex-col items-center justify-center gap-2 rounded-xl border bg-muted/20 p-6 text-center"
    >
      {children}
    </div>
  );
}
