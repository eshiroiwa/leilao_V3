"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

export type ValuateButtonProps = {
  propertyId: string;
  variant?: "default" | "compact";
};

export function ValuateButton({ propertyId, variant = "default" }: ValuateButtonProps) {
  return (
    <Button
      asChild
      size={variant === "compact" ? "sm" : "default"}
      variant="secondary"
      onClick={(e) => e.stopPropagation()}
    >
      <Link href={`/properties/${encodeURIComponent(propertyId)}/valuation`}>
        Avaliar
      </Link>
    </Button>
  );
}
