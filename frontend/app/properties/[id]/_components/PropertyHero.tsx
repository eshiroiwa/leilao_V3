import {
  Bath,
  BedDouble,
  Calendar,
  ExternalLink,
  Gavel,
  MapPin,
  MapPinOff,
  Ruler,
} from "lucide-react";

import { PropertyImage } from "@/components/PropertyImage";
import { Badge } from "@/components/ui/badge";
import type { Property } from "@/lib/api";
import { cn, formatBRL, formatDateTimeBR } from "@/lib/utils";

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
  REJECTED: "geo rejeitada",
};

export function PropertyHero({ property }: { property: Property }) {
  const cityState = [property.city, property.state].filter(Boolean).join(" / ");
  const hasGeo = property.latitude !== null && property.longitude !== null;

  return (
    <section className="overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,260px)_1fr]">
        {/* Foto */}
        <div className="relative md:max-h-[260px]">
          <PropertyImage
            src={property.image_url}
            alt={property.title ?? "Foto do imóvel"}
            aspect="aspect-[16/10] md:aspect-auto md:h-full"
          />
          <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
            {property.property_type && (
              <Badge
                variant="secondary"
                className="bg-card/85 capitalize backdrop-blur-sm"
              >
                {property.property_type}
              </Badge>
            )}
            {property.geocoding_confidence && (
              <Badge
                variant={
                  confidenceVariant[property.geocoding_confidence] ??
                  "secondary"
                }
                className="backdrop-blur-sm"
              >
                {confidenceLabel[property.geocoding_confidence] ??
                  property.geocoding_confidence}
              </Badge>
            )}
          </div>
        </div>

        {/* Informações */}
        <div className="flex flex-col gap-4 p-5 sm:p-6">
          <div>
            <h1 className="text-xl font-semibold leading-snug tracking-tight sm:text-2xl">
              {property.title ?? "Imóvel sem título"}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {hasGeo ? (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="size-3.5 text-primary" />
                  {cityState || "—"}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <MapPinOff className="size-3.5" />
                  {cityState || "Localização não informada"}
                </span>
              )}
              {property.address_full && (
                <>
                  <span aria-hidden>·</span>
                  <span className="line-clamp-1 max-w-md">
                    {property.address_full}
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Atributos rápidos */}
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
            {property.area_total_m2 != null && (
              <span className="inline-flex items-center gap-1">
                <Ruler className="size-3.5" /> {property.area_total_m2} m²
              </span>
            )}
            {property.bedrooms != null && (
              <span className="inline-flex items-center gap-1">
                <BedDouble className="size-3.5" /> {property.bedrooms} quarto(s)
              </span>
            )}
            {property.bathrooms != null && (
              <span className="inline-flex items-center gap-1">
                <Bath className="size-3.5" /> {property.bathrooms} banheiro(s)
              </span>
            )}
            {property.first_auction_at && (
              <span className="inline-flex items-center gap-1">
                <Calendar className="size-3.5" />
                1ª praça {formatDateTimeBR(property.first_auction_at)}
              </span>
            )}
          </div>

          {/* Valores em destaque */}
          <div className="grid grid-cols-3 gap-3">
            <PriceTile
              label="Avaliação"
              value={formatBRL(property.appraisal_value)}
            />
            <PriceTile
              label="1ª praça"
              value={formatBRL(property.minimum_bid_first)}
            />
            <PriceTile
              label="2ª praça"
              value={formatBRL(property.minimum_bid_second)}
              highlight
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <Gavel className="size-3.5" />
              Atualizado {formatDateTimeBR(property.updated_at)}
            </span>
            <a
              href={property.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 hover:text-primary"
            >
              Ver no leiloeiro <ExternalLink className="size-3" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

function PriceTile({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-muted/30 p-2.5",
        highlight && "border-primary/40 bg-primary-50",
      )}
    >
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 text-sm font-semibold tabular-nums",
          highlight && "text-primary-700",
        )}
      >
        {value}
      </div>
    </div>
  );
}
