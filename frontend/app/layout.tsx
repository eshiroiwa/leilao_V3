import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { AppShell } from "@/components/AppShell";
import { themeBootstrapScript } from "@/components/ThemeToggle";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Leilão IA — Precificação de Imóveis",
  description:
    "Sistema multi-agente para coleta, normalização e precificação de imóveis de leilão.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning className={inter.variable}>
      <head>
        <script
          dangerouslySetInnerHTML={{ __html: themeBootstrapScript }}
        />
      </head>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
