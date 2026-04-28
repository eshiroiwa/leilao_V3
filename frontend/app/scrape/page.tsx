import { ScrapeForm } from "./_components/ScrapeForm";

export default function ScrapePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Novo scrape</h1>
        <p className="text-muted-foreground">
          Cole a URL pública de um lote em um leiloeiro brasileiro (Zuk, Mega Leilões, Sodré
          Santoro, Biasi…). O Agente 1 cuida de extrair, validar e persistir o registro.
        </p>
      </div>
      <ScrapeForm />
    </div>
  );
}
