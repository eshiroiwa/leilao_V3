"use client";

import {
  Activity,
  Building2,
  ChevronsLeft,
  ChevronsRight,
  Globe2,
  LayoutDashboard,
  PlusCircle,
  X,
} from "lucide-react";
import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { BackendStatus } from "@/components/BackendStatus";
import { cn } from "@/lib/utils";

type NavItem = {
  href: Route;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  match?: (pathname: string) => boolean;
};

type NavGroup = {
  label?: string;
  items: NavItem[];
};

const GROUPS: NavGroup[] = [
  {
    label: "Principal",
    items: [
      {
        href: "/" as Route,
        label: "Início",
        icon: LayoutDashboard,
        match: (p) => p === "/",
      },
      { href: "/scrape" as Route, label: "Novo scrape", icon: PlusCircle },
    ],
  },
  {
    label: "Pipeline",
    items: [
      {
        href: "/properties" as Route,
        label: "Imóveis",
        icon: Building2,
        match: (p) => p === "/properties" || p.startsWith("/properties/"),
      },
    ],
  },
];

const STORAGE_KEY = "leilao-ia:sidebar-collapsed";

export function Sidebar({
  mobileOpen,
  onMobileClose,
}: {
  mobileOpen: boolean;
  onMobileClose: () => void;
}) {
  const pathname = usePathname() ?? "/";
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "1") setCollapsed(true);
  }, []);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    } catch {
      // ignore
    }
  }

  const widthClass = collapsed ? "lg:w-16" : "lg:w-60";

  return (
    <>
      {mobileOpen && (
        <div
          aria-hidden
          className="fixed inset-0 z-30 bg-foreground/30 backdrop-blur-sm lg:hidden"
          onClick={onMobileClose}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-all duration-200",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          "lg:translate-x-0",
          widthClass,
        )}
      >
        <div
          className={cn(
            "flex h-14 items-center border-b border-sidebar-border px-4",
            collapsed ? "lg:justify-center lg:px-0" : "justify-between",
          )}
        >
          <Link
            href="/"
            className="flex items-center gap-2 text-base font-semibold tracking-tight"
            onClick={onMobileClose}
          >
            <span
              aria-hidden
              className="inline-flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary-700 text-primary-foreground shadow-sm"
            >
              <Globe2 className="size-4" />
            </span>
            <span className={cn("transition-opacity", collapsed && "lg:hidden")}>
              Leilão<span className="text-muted-foreground">IA</span>
            </span>
          </Link>

          <button
            type="button"
            aria-label="Fechar menu"
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden"
            onClick={onMobileClose}
          >
            <X className="size-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 scrollbar-hide">
          {GROUPS.map((group, gi) => (
            <div key={gi} className={cn("mb-6 last:mb-0")}>
              {group.label && (
                <p
                  className={cn(
                    "mb-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground",
                    collapsed && "lg:sr-only",
                  )}
                >
                  {group.label}
                </p>
              )}
              <ul className="space-y-1">
                {group.items.map((item) => {
                  const active = item.match
                    ? item.match(pathname)
                    : pathname === item.href;
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onMobileClose}
                        className={cn(
                          "group relative flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                          active
                            ? "bg-sidebar-accent text-foreground"
                            : "text-muted-foreground hover:bg-muted hover:text-foreground",
                          collapsed && "lg:justify-center lg:px-0",
                        )}
                        title={collapsed ? item.label : undefined}
                      >
                        {active && (
                          <span
                            aria-hidden
                            className="absolute -left-3 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-primary"
                          />
                        )}
                        <Icon
                          className={cn(
                            "size-4 shrink-0",
                            active ? "text-primary" : "text-muted-foreground",
                          )}
                        />
                        <span className={cn(collapsed && "lg:hidden")}>{item.label}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-sidebar-border p-3">
          <div className={cn("mb-2", collapsed && "lg:hidden")}>
            <BackendStatus />
          </div>

          <button
            type="button"
            onClick={toggleCollapsed}
            className={cn(
              "hidden w-full items-center gap-2 rounded-md px-2.5 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground lg:inline-flex",
              collapsed && "lg:justify-center",
            )}
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
          >
            {collapsed ? (
              <ChevronsRight className="size-4" />
            ) : (
              <>
                <ChevronsLeft className="size-4" />
                <span>Recolher</span>
              </>
            )}
          </button>

          <div
            className={cn(
              "mt-2 flex items-center gap-1.5 px-2 text-[11px] text-muted-foreground/70",
              collapsed && "lg:hidden",
            )}
          >
            <Activity className="size-3" />
            <span>v3 · Multi-Agent</span>
          </div>
        </div>
      </aside>
    </>
  );
}

export const SIDEBAR_STORAGE_KEY = STORAGE_KEY;
