import {
  ArrowRight,
  Brain,
  Building2,
  ExternalLink,
  Gavel,
  MapPin,
  PlusCircle,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import type { Route } from "next";

import { StatCard } from "@/components/StatCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api, type Property } from "@/lib/api";
import { formatBRL, formatDateTimeBR } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let properties: Property[] = [];
  try {
    properties = await api.listProperties({ limit: 100 });
  } catch {
    // graceful: dashboard funciona com 0 imóveis
  }

  const total = properties.length;
  const geocoded = properties.filter(
    (p) => p.latitude !== null && p.longitude !== null,
  ).length;
  const states = new Set(
    properties.map((p) => p.state).filter(Boolean) as string[],
  );
  const recent = [...properties]
    .sort(
      (a, b) =>
        new Date(b.updated_at ?? 0).getTime() -
        new Date(a.updated_at ?? 0).getTime(),
    )
    .slice(0, 6);

  return (
    <div className="space-y-8">
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_minmax(280px,360px)]">
        <div className="space-y-4 rounded-2xl border bg-gradient-to-br from-primary-50 via-card to-card p-6 sm:p-8">
          <Badge variant="info" className="w-fit">
            Multi-agente · LangGraph · Supabase
          </Badge>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Precificação de imóveis de leilão,{" "}
            <span className="text-primary-700">automatizada</span>.
          </h1>
          <p className="max-w-2xl text-muted-foreground">
            Quatro agentes coordenados extraem o lote, normalizam o endereço,
            buscam comparáveis no mercado, analisam viabilidade financeira e
            enriquecem com contexto de bairro — pronto para decidir o lance.
          </p>
          <div className="flex flex-wrap gap-3 pt-1">
            <Button asChild size="lg">
              <Link href="/scrape">
                <PlusCircle className="size-4" /> Iniciar um scrape
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/properties">
                Ver imóveis processados <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <StatCard
            label="Imóveis cadastrados"
            value={total}
            hint={
              total === 0
                ? "Comece com /scrape"
                : `Em ${states.size} UF${states.size === 1 ? "" : "s"}`
            }
            icon={Building2}
            tone="primary"
          />
          <StatCard
            label="Com geolocalização"
            value={geocoded}
            hint={
              total > 0
                ? `${Math.round((geocoded / total) * 100)}% georreferenciados`
                : "—"
            }
            icon={MapPin}
            tone="success"
          />
        </div>
      </section>

      {recent.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold tracking-tight">
              Imóveis recentes
            </h2>
            <Link
              href="/properties"
              className="text-sm font-medium text-primary-700 hover:underline"
            >
              Ver todos →
            </Link>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {recent.map((p) => (
              <RecentItem key={p.id} property={p} />
            ))}
          </div>
        </section>
      )}

      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <PipelineCard
          n="01"
          title="Coleta + Normalização"
          icon={Gavel}
          color="bg-info"
          desc="URL → Markdown limpo via Firecrawl, extração estruturada com OpenAI, validação de endereço e geocoding via Google Maps."
        />
        <PipelineCard
          n="02"
          title="Avaliação (CMA)"
          icon={TrendingUp}
          color="bg-primary"
          desc="Busca comparáveis em portais imobiliários por raio adaptativo, calcula faixa de preço (P10–P90) com confiança."
        />
        <PipelineCard
          n="03"
          title="Oportunidade"
          icon={Sparkles}
          color="bg-success"
          desc="Calcula custos, ROI bruto/líquido, lance máximo para ROI alvo e veredito (Boa/Ressalvas/Neutro/Inviável)."
        />
        <PipelineCard
          n="04"
          title="Análise profunda"
          icon={Brain}
          color="bg-warning"
          desc="Liquidez, outliers, tendência, riscos urbanos, prior auction — síntese via LLM com sources auditáveis."
        />
      </section>
    </div>
  );
}

function RecentItem({ property }: { property: Property }) {
  const cityState = [property.city, property.state]
    .filter(Boolean)
    .join(" / ");

  return (
    <Card className="group transition-all hover:-translate-y-0.5 hover:shadow-md">
      <CardHeader className="pb-2">
        <CardTitle className="line-clamp-2 text-sm">
          {property.title ?? "Imóvel sem título"}
        </CardTitle>
        <CardDescription className="flex items-center gap-1 text-xs">
          <MapPin className="size-3.5" />
          {cityState || "—"}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between">
        <div className="text-xs">
          <div className="text-muted-foreground">2ª praça</div>
          <div className="font-semibold tabular-nums text-primary-700">
            {formatBRL(property.minimum_bid_second)}
          </div>
        </div>
        <div className="text-right text-[10px] text-muted-foreground">
          <div>{formatDateTimeBR(property.updated_at)}</div>
          <Link
            href={
              `/properties/${encodeURIComponent(property.id)}` as Route
            }
            className="mt-1 inline-flex items-center gap-1 text-primary-700 hover:underline"
          >
            Abrir <ExternalLink className="size-3" />
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

function PipelineCard({
  n,
  title,
  desc,
  icon: Icon,
  color,
}: {
  n: string;
  title: string;
  desc: string;
  icon: typeof Building2;
  color: string;
}) {
  return (
    <Card className="relative overflow-hidden">
      <span aria-hidden className={`absolute inset-x-0 top-0 h-0.5 ${color}`} />
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-muted-foreground">{n}</span>
          <Icon className="size-4 text-muted-foreground" />
        </div>
        <CardTitle className="mt-1 text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </CardContent>
    </Card>
  );
}
