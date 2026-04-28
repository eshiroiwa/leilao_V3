import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Leilão IA — Precificação de Imóveis",
  description:
    "Sistema multi-agente para coleta, normalização e precificação de imóveis de leilão.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <header className="border-b">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Leilão<span className="text-muted-foreground">IA</span>
            </Link>
            <nav className="flex items-center gap-6 text-sm">
              <Link href="/scrape" className="hover:text-primary">
                Novo scrape
              </Link>
              <Link href="/properties" className="hover:text-primary">
                Imóveis
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
        <footer className="mt-20 border-t">
          <div className="mx-auto max-w-6xl px-6 py-6 text-xs text-muted-foreground">
            Leilão IA v3 — Multi-Agent Pricing Platform
          </div>
        </footer>
      </body>
    </html>
  );
}
