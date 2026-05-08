"use client";

import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export type TabsNavItem = {
  href: Route;
  label: string;
  icon?: LucideIcon;
  /** Marcar tab como ativa quando a rota coincide com este predicate ao invés de igualdade exata. */
  match?: (pathname: string) => boolean;
  badge?: React.ReactNode;
};

export function TabsNav({
  items,
  className,
}: {
  items: TabsNavItem[];
  className?: string;
}) {
  const pathname = usePathname() ?? "";

  return (
    <nav
      role="tablist"
      aria-label="Seções do imóvel"
      className={cn(
        "relative flex flex-wrap items-center gap-1 border-b border-border",
        className,
      )}
    >
      {items.map((item) => {
        const active = item.match
          ? item.match(pathname)
          : pathname === item.href;
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            role="tab"
            aria-selected={active}
            className={cn(
              "relative -mb-px inline-flex items-center gap-1.5 rounded-t-md border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {Icon && (
              <Icon
                className={cn(
                  "size-4",
                  active ? "text-primary" : "text-muted-foreground",
                )}
              />
            )}
            <span>{item.label}</span>
            {item.badge}
          </Link>
        );
      })}
    </nav>
  );
}
