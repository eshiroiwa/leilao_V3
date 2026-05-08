"use client";

import {
  Bath,
  BedDouble,
  ExternalLink,
  MapPin,
  MapPinOff,
  Ruler,
} from "lucide-react";

import { PropertyImage } from "@/components/PropertyImage";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Property } from "@/lib/api";
import { cn, formatBRL, formatDateTimeBR } from "@/lib/utils";

import { DeletePropertyButton } from "./DeletePropertyButton";
import { OpportunityButton } from "./OpportunityButton";
import { ValuateButton } from "./ValuateButton";

const confidenceVariant: Record<
  string,
  "success" | "warning" | "danger" | "secondary"
> = {
  HIGH: "success",
  MEDIUM: "warning",
  LOW: "danger",
  POSTAL_CODE: "warning",
  REJECTED: "danger",
};

const confidenceLabel: Record<string, string> = {
  HIGH: "geo alta",
  MEDIUM: "geo média",
  LOW: "geo baixa",
  POSTAL_CODE: "geo CEP",
  REJECTED: "geo rej.",
};

export type PropertyCardProps = {
  property: Property;
  selected?: boolean;
  onSelect?: (id: string) => void;
  onDeleted?: (id: string) => void | Promise<void>;
};

export function PropertyCard({
  property,
  selected = false,
  onSelect,
  onDeleted,
}: PropertyCardProps) {
  const cityState = [property.city, property.state].filter(Boolean).join(" / ");
  const hasGeo = property.latitude !== null && property.longitude !== null;

  const interactive = Boolean(onSelect);

  return (
    <Card
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={interactive ? () => onSelect?.(property.id) : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect?.(property.id);
              }
            }
          : undefined
      }
      className={cn(
        "group relative flex h-full flex-col overflow-hidden rounded-xl border transition-all",
        interactive &&
          "cursor-pointer hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg",
        selected && "border-primary shadow-md ring-2 ring-primary/40",
      )}
    >
      <div className="relative">
        <PropertyImage
          src={property.image_url}
          alt={property.title ?? "Foto do imóvel"}
          className="[&_img]:transition-transform [&_img]:duration-500 group-hover:[&_img]:scale-[1.04]"
        />

        {/* badges sobrepostos no canto superior */}
        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
          {property.property_type && (
            <Badge
              variant="secondary"
              className="bg-card/85 capitalize backdrop-blur-sm"
            >
              {property.property_type}
            </Badge>
          )}
          {!hasGeo && (
            <Badge variant="warning" className="backdrop-blur-sm">
              <MapPinOff className="mr-1 size-3" /> sem geo
            </Badge>
          )}
        </div>

        <div className="absolute right-3 top-3 flex items-center gap-1.5">
          {property.geocoding_confidence && (
            <Badge
              variant={confidenceVariant[property.geocoding_confidence] ?? "secondary"}
              title={`Confiança da geocodificação: ${property.geocoding_confidence}`}
              className="backdrop-blur-sm"
            >
              {confidenceLabel[property.geocoding_confidence] ??
                property.geocoding_confidence}
            </Badge>
          )}
          <div className="rounded-md bg-card/85 backdrop-blur-sm">
            <DeletePropertyButton
              propertyId={property.id}
              propertyTitle={property.title}
              onDeleted={onDeleted}
            />
          </div>
        </div>
      </div>

      <CardHeader className="pb-2">
        <CardTitle className="line-clamp-2 text-base leading-snug">
          {property.title ?? "Imóvel sem título"}
        </CardTitle>
        <CardDescription className="flex items-center gap-1 pt-0.5 text-xs">
          {hasGeo ? (
            <MapPin className="size-3.5 text-primary" />
          ) : (
            <MapPinOff className="size-3.5" />
          )}
          {cityState || "Localização não informada"}
        </CardDescription>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-3 pt-0">
        {property.address_full && (
          <p className="line-clamp-2 text-xs text-muted-foreground">
            {property.address_full}
          </p>
        )}

        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {property.area_total_m2 != null && (
            <span className="inline-flex items-center gap-1">
              <Ruler className="size-3.5" /> {property.area_total_m2} m²
            </span>
          )}
          {property.bedrooms != null && (
            <span className="inline-flex items-center gap-1">
              <BedDouble className="size-3.5" /> {property.bedrooms}
            </span>
          )}
          {property.bathrooms != null && (
            <span className="inline-flex items-center gap-1">
              <Bath className="size-3.5" /> {property.bathrooms}
            </span>
          )}
        </div>

        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 rounded-lg bg-muted/40 p-2.5 text-xs">
          <dt className="text-muted-foreground">Avaliação</dt>
          <dd className="text-right font-semibold tabular-nums">
            {formatBRL(property.appraisal_value)}
          </dd>

          <dt className="text-muted-foreground">1ª praça</dt>
          <dd className="text-right font-medium tabular-nums">
            {formatBRL(property.minimum_bid_first)}
          </dd>

          <dt className="text-muted-foreground">2ª praça</dt>
          <dd className="text-right font-medium tabular-nums text-primary-700">
            {formatBRL(property.minimum_bid_second)}
          </dd>

          {property.first_auction_at && (
            <>
              <dt className="text-muted-foreground">Data 1ª</dt>
              <dd className="text-right">
                {formatDateTimeBR(property.first_auction_at)}
              </dd>
            </>
          )}
        </dl>

        <div className="mt-auto flex items-center justify-between border-t pt-2 text-[11px] text-muted-foreground">
          <span>Atualizado {formatDateTimeBR(property.updated_at)}</span>
          <a
            href={property.source_url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 hover:text-primary"
          >
            Fonte <ExternalLink className="size-3" />
          </a>
        </div>

        <div className="flex flex-wrap justify-end gap-2 pt-1">
          <ValuateButton propertyId={property.id} variant="compact" />
          <OpportunityButton propertyId={property.id} variant="compact" />
        </div>
      </CardContent>
    </Card>
  );
}
