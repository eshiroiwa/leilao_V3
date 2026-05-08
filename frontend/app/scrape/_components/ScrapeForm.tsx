"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";

import { PropertyImage } from "@/components/PropertyImage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type ScraperRunResponse } from "@/lib/api";
import { formatBRL } from "@/lib/utils";

export function ScrapeForm() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<ScraperRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    startTransition(async () => {
      try {
        const data = await api.runScraper(url.trim());
        setResult(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erro desconhecido");
      }
    });
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>URL do lote</CardTitle>
          <CardDescription>
            Apenas URLs públicas são suportadas. O processamento síncrono pode levar ~10–30s.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="url">URL</Label>
              <Input
                id="url"
                name="url"
                type="url"
                required
                placeholder="https://www.zuk.com.br/leiloes/imoveis/..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={isPending}
              />
            </div>
            <Button type="submit" disabled={isPending || !url.trim()}>
              {isPending && <Loader2 className="size-4 animate-spin" />}
              {isPending ? "Processando…" : "Executar Agente 1"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive/50">
          <CardHeader>
            <div className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="size-5" />
              <CardTitle>Falha na requisição</CardTitle>
            </div>
            <CardDescription className="text-destructive">{error}</CardDescription>
          </CardHeader>
        </Card>
      )}

      {result && <ScrapeResult result={result} />}
    </div>
  );
}

function ScrapeResult({ result }: { result: ScraperRunResponse }) {
  const ok = result.status === "success";
  const property = result.saved_property;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {ok ? (
              <CheckCircle2 className="size-5 text-success-700" />
            ) : (
              <AlertTriangle className="size-5 text-warning-700" />
            )}
            <CardTitle>{ok ? "Sucesso" : "Concluído com erros"}</CardTitle>
          </div>
          <Badge variant={ok ? "success" : "warning"}>{result.status}</Badge>
        </div>
        <CardDescription>
          {result.duration_ms} ms · run <code>{result.run_id ?? "—"}</code>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {property && (
          <>
            <PropertyImage
              src={property.image_url}
              alt={property.title ?? "Foto do imóvel"}
              className="rounded-md border"
            />
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Título" value={property.title} />
              <Field label="Tipo" value={property.property_type} />
              <Field label="Cidade / UF" value={`${property.city ?? "—"} / ${property.state ?? "—"}`} />
              <Field label="Bairro" value={property.neighborhood} />
              <Field label="Endereço" value={property.address_full} className="md:col-span-2" />
              <Field label="Avaliação" value={formatBRL(property.appraisal_value)} />
              <Field label="1ª praça" value={formatBRL(property.minimum_bid_first)} />
              <Field label="2ª praça" value={formatBRL(property.minimum_bid_second)} />
              <Field
                label="Confiança geo"
                value={property.geocoding_confidence ?? "—"}
              />
            </div>
          </>
        )}

        {result.warnings.length > 0 && (
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-warning-700">Avisos</div>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {result.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        {result.errors.length > 0 && (
          <div>
            <div className="mb-1 text-xs font-semibold uppercase text-destructive">Erros</div>
            <ul className="list-disc space-y-1 pl-5 text-sm text-destructive">
              {result.errors.map((er, i) => (
                <li key={i}>{er}</li>
              ))}
            </ul>
          </div>
        )}

        {property && (
          <Button asChild variant="outline" size="sm">
            <Link href="/properties">Ver na lista de imóveis</Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  value,
  className,
}: {
  label: string;
  value: string | number | null | undefined;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-medium">{value || "—"}</div>
    </div>
  );
}
