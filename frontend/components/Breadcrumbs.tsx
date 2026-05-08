"use client";

import { ChevronRight, Home } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import { useMemo } from "react";

import { cn } from "@/lib/utils";

type Crumb = { href: Route | null; label: string };

const SEGMENT_LABELS: Record<string, string> = {
  scrape: "Novo scrape",
  properties: "Imóveis",
  valuation: "Avaliação",
  opportunity: "Análise de oportunidade",
};

function isUuidLike(s: string): boolean {
  return /^[0-9a-f]{8}-/i.test(s);
}

function prettify(seg: string): string {
  if (!seg) return "";
  if (isUuidLike(seg)) return "Imóvel";
  return seg.charAt(0).toUpperCase() + seg.slice(1);
}

export function Breadcrumbs({ className }: { className?: string }) {
  const pathname = usePathname();

  const crumbs = useMemo<Crumb[]>(() => {
    const parts = (pathname ?? "/").split("/").filter(Boolean);
    const out: Crumb[] = [{ href: "/" as Route, label: "Início" }];
    let acc = "";
    parts.forEach((seg, idx) => {
      acc += `/${seg}`;
      const last = idx === parts.length - 1;
      const label = SEGMENT_LABELS[seg] ?? prettify(seg);
      out.push({ href: last ? null : (acc as Route), label });
    });
    return out;
  }, [pathname]);

  if (crumbs.length <= 1) return null;

  return (
    <nav
      aria-label="Trilha de navegação"
      className={cn("flex items-center gap-1 text-sm text-muted-foreground", className)}
    >
      {crumbs.map((c, i) => (
        <span key={`${c.label}-${i}`} className="flex items-center gap-1">
          {i === 0 ? (
            c.href ? (
              <Link
                href={c.href}
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-muted hover:text-foreground"
              >
                <Home className="size-3.5" />
                <span className="sr-only">Início</span>
              </Link>
            ) : (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-foreground">
                <Home className="size-3.5" />
              </span>
            )
          ) : c.href ? (
            <Link
              href={c.href}
              className="rounded-md px-1.5 py-0.5 hover:bg-muted hover:text-foreground"
            >
              {c.label}
            </Link>
          ) : (
            <span className="px-1.5 py-0.5 font-medium text-foreground">{c.label}</span>
          )}
          {i < crumbs.length - 1 && (
            <ChevronRight className="size-3.5 text-muted-foreground/60" />
          )}
        </span>
      ))}
    </nav>
  );
}
