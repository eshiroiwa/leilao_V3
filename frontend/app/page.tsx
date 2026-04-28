import Link from "next/link";
import { ArrowRight, Bot, Database, Globe2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function HomePage() {
  return (
    <div className="space-y-12">
      <section className="space-y-4">
        <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Multi-agente · LangGraph · Supabase
        </p>
        <h1 className="text-4xl font-bold tracking-tight md:text-5xl">
          Precificação de imóveis de leilão, automatizada de ponta a ponta.
        </h1>
        <p className="max-w-2xl text-lg text-muted-foreground">
          O <strong>Agente 1</strong> coleta lotes de leiloeiros brasileiros, extrai dados
          estruturados com LLM, valida endereços via Google Maps Platform e persiste tudo
          no Supabase com PostGIS — pronto para os agentes seguintes do pipeline.
        </p>
        <div className="flex gap-3">
          <Button asChild size="lg">
            <Link href="/scrape">
              Iniciar um scrape <ArrowRight className="size-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/properties">Ver imóveis processados</Link>
          </Button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <Globe2 className="size-6 text-primary" />
            <CardTitle>Scraping confiável</CardTitle>
            <CardDescription>
              URL → Markdown limpo via Firecrawl, mesmo em sites com JS pesado.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <Bot className="size-6 text-primary" />
            <CardTitle>Extração estruturada</CardTitle>
            <CardDescription>
              OpenAI com structured output garante JSON validado por Pydantic.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <Database className="size-6 text-primary" />
            <CardTitle>Geo + Postgres + PostGIS</CardTitle>
            <CardDescription>
              Endereços validados e coordenadas indexadas para análises espaciais.
            </CardDescription>
          </CardHeader>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Pipeline do Agente 1</CardTitle>
          <CardDescription>Cada nó é idempotente e auditável.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-3 md:grid-cols-5">
            {[
              { n: "01", t: "scrape_url", d: "Firecrawl → Markdown" },
              { n: "02", t: "extract_data", d: "LLM (structured output)" },
              { n: "03", t: "validate_address", d: "Google Address Validation" },
              { n: "04", t: "geocode", d: "Google Geocoding" },
              { n: "05", t: "persist", d: "Supabase (PostGIS)" },
            ].map((s) => (
              <li
                key={s.n}
                className="rounded-lg border bg-muted/30 p-4 text-sm"
              >
                <div className="text-xs font-mono text-muted-foreground">{s.n}</div>
                <div className="font-semibold">{s.t}</div>
                <div className="text-muted-foreground">{s.d}</div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
