import { Globe2, Sparkles, Workflow } from "lucide-react";

import { Badge } from "@/components/ui/badge";

import { ScrapeForm } from "./_components/ScrapeForm";

export default function ScrapePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-3">
        <Badge variant="info" className="w-fit">
          Agente 1 · Scraper + Normalizador
        </Badge>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Novo scrape
        </h1>
        <p className="text-sm text-muted-foreground sm:text-base">
          Cole a URL pública de um lote em um leiloeiro brasileiro (Zuk, Mega
          Leilões, Sodré Santoro, Biasi…). O pipeline cuida de extrair, validar
          e persistir o registro.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <Step n="01" icon={Globe2} label="Firecrawl" desc="URL → Markdown" />
        <Step n="02" icon={Sparkles} label="OpenAI" desc="Extração estruturada" />
        <Step n="03" icon={Workflow} label="Google Maps" desc="Validação + Geo" />
      </div>

      <ScrapeForm />
    </div>
  );
}

function Step({
  n,
  icon: Icon,
  label,
  desc,
}: {
  n: string;
  icon: typeof Globe2;
  label: string;
  desc: string;
}) {
  return (
    <div className="rounded-lg border bg-card p-2.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] text-muted-foreground">{n}</span>
        <Icon className="size-3.5 text-primary" />
        <span className="font-semibold">{label}</span>
      </div>
      <p className="mt-0.5 text-[10px] text-muted-foreground">{desc}</p>
    </div>
  );
}
