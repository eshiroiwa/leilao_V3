"use client";

import { Menu } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Breadcrumbs } from "@/components/Breadcrumbs";
import { Sidebar, SIDEBAR_STORAGE_KEY } from "@/components/Sidebar";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    setCollapsed(stored === "1");

    function onStorage(e: StorageEvent) {
      if (e.key === SIDEBAR_STORAGE_KEY) {
        setCollapsed(e.newValue === "1");
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Sidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />

      <div
        className={cn(
          "flex min-h-screen flex-col transition-[padding] duration-200",
          collapsed ? "lg:pl-16" : "lg:pl-60",
        )}
      >
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 sm:px-6">
          <button
            type="button"
            aria-label="Abrir menu"
            className="-ml-1 inline-flex size-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden"
            onClick={() => setMobileOpen(true)}
          >
            <Menu className="size-5" />
          </button>

          <Breadcrumbs className="min-w-0 flex-1 overflow-hidden" />

          <div className="flex items-center gap-1.5">
            <ThemeToggle />
          </div>
        </header>

        <main className="flex-1">
          <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 sm:py-10">
            {children}
          </div>
        </main>

        <footer className="border-t border-border/60">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 text-xs text-muted-foreground sm:px-6">
            <span>Leilão IA v3 — Multi-Agent Pricing Platform</span>
            <span className="hidden sm:inline">
              Indigo · Emerald · Amber · Sky
            </span>
          </div>
        </footer>
      </div>
    </div>
  );
}
