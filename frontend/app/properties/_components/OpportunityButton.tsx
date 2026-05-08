"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

export type OpportunityButtonProps = {
  propertyId: string;
  variant?: "default" | "compact";
};

export function OpportunityButton({
  propertyId,
  variant = "default",
}: OpportunityButtonProps) {
  return (
    <Button
      asChild
      size={variant === "compact" ? "sm" : "default"}
      variant="default"
      onClick={(e) => e.stopPropagation()}
    >
      <Link
        href={`/properties/${encodeURIComponent(propertyId)}/opportunity`}
      >
        Analisar oportunidade
      </Link>
    </Button>
  );
}
