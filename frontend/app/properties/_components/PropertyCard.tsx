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
  "success" | "warning" | "destructive" | "secondary"
> = {
  HIGH: "success",
  MEDIUM: "warning",
  LOW: "destructive",
  POSTAL_CODE: "warning",
  REJECTED: "destructive",
};

const confidenceLabel: Record<string, string> = {
  HIGH: "HIGH",
  MEDIUM: "MEDIUM",
  LOW: "LOW",
  POSTAL_CODE: "CEP",
  REJECTED: "REJ",
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
        "flex h-full flex-col overflow-hidden transition-all",
        interactive && "cursor-pointer hover:border-primary/40 hover:shadow-md",
        selected && "border-primary ring-2 ring-primary/40 shadow-md"
      )}
    >
      <PropertyImage
        src={property.image_url}
        alt={property.title ?? "Foto do imóvel"}
        className="[&_img]:transition-transform [&_img]:duration-300 [&_img:hover]:scale-[1.02]"
      />

      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="line-clamp-2 text-base">
              {property.title ?? "Imóvel sem título"}
            </CardTitle>
            <CardDescription className="flex items-center gap-1">
              {hasGeo ? <MapPin className="size-3.5" /> : <MapPinOff className="size-3.5" />}
              {cityState || "Localização não informada"}
            </CardDescription>
          </div>
          <div className="flex items-center gap-1">
            {property.geocoding_confidence && (
              <Badge
                variant={confidenceVariant[property.geocoding_confidence] ?? "secondary"}
                title={`Confiança da geocodificação: ${property.geocoding_confidence}`}
              >
                {confidenceLabel[property.geocoding_confidence] ?? property.geocoding_confidence}
              </Badge>
            )}
            <DeletePropertyButton
              propertyId={property.id}
              propertyTitle={property.title}
              onDeleted={onDeleted}
            />
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-3">
        {property.address_full && (
          <p className="line-clamp-2 text-xs text-muted-foreground">{property.address_full}</p>
        )}

        <div className="flex flex-wrap gap-3 text-xs">
          {property.area_total_m2 != null && (
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Ruler className="size-3.5" /> {property.area_total_m2} m²
            </span>
          )}
          {property.bedrooms != null && (
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <BedDouble className="size-3.5" /> {property.bedrooms}
            </span>
          )}
          {property.bathrooms != null && (
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Bath className="size-3.5" /> {property.bathrooms}
            </span>
          )}
          {property.property_type && (
            <Badge variant="outline" className="capitalize">
              {property.property_type}
            </Badge>
          )}
        </div>

        <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
          <dt className="text-muted-foreground">Avaliação</dt>
          <dd className="text-right font-medium">{formatBRL(property.appraisal_value)}</dd>

          <dt className="text-muted-foreground">1ª praça</dt>
          <dd className="text-right font-medium">{formatBRL(property.minimum_bid_first)}</dd>

          <dt className="text-muted-foreground">2ª praça</dt>
          <dd className="text-right font-medium">{formatBRL(property.minimum_bid_second)}</dd>

          {property.first_auction_at && (
            <>
              <dt className="text-muted-foreground">Data 1ª</dt>
              <dd className="text-right">{formatDateTimeBR(property.first_auction_at)}</dd>
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

        <div className="flex flex-wrap justify-end gap-2 pt-2">
          <ValuateButton propertyId={property.id} variant="compact" />
          <OpportunityButton propertyId={property.id} variant="compact" />
        </div>
      </CardContent>
    </Card>
  );
}
