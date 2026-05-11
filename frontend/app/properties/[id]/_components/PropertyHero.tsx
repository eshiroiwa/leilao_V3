import {
  Bath,
  BedDouble,
  Building2,
  Calendar,
  Car,
  ExternalLink,
  FileText,
  Gavel,
  Home,
  IdCard,
  Landmark,
  MapPin,
  MapPinOff,
  Ruler,
} from "lucide-react";

import { PropertyImage } from "@/components/PropertyImage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Property } from "@/lib/api";
import { cn, formatBRL, formatDateTimeBR } from "@/lib/utils";

const confidenceVariant: Record<
  string,
  "success" | "warning" | "danger" | "secondary"
> = {
  HIGH: "success",
  MEDIUM: "warning",
  LOW: "danger",
  POSTAL_CODE: "warning",
  REJECTED: "danger",
};

const confidenceLabel: Record<string, string> = {
  HIGH: "geo alta",
  MEDIUM: "geo média",
  LOW: "geo baixa",
  POSTAL_CODE: "geo CEP",
  REJECTED: "geo rejeitada",
};

const ONR_URL = "https://www.registradores.onr.org.br/";

/** Formata área "construída / total" quando ambas diferem; cai para uma só
 *  quando faltam ou são iguais. */
function formatAreaDual(
  built: number | null,
  total: number | null,
): { value: string; tooltip: string | null } | null {
  const b = built && built > 0 ? Math.round(built) : null;
  const t = total && total > 0 ? Math.round(total) : null;
  if (b == null && t == null) return null;
  if (b != null && t != null && b !== t) {
    return { value: `${b}/${t} m²`, tooltip: "construída / total" };
  }
  return { value: `${b ?? t} m²`, tooltip: null };
}

export function PropertyHero({ property }: { property: Property }) {
  const cityState = [property.city, property.state].filter(Boolean).join(" / ");
  const hasGeo = property.latitude !== null && property.longitude !== null;
  const area = formatAreaDual(property.area_built_m2, property.area_total_m2);
  const hasCurrentBid =
    property.current_bid != null &&
    property.current_bid !== property.minimum_bid_first;
  const hasArrears =
    (property.iptu_arrears ?? 0) > 0 || (property.condo_arrears ?? 0) > 0;
  const hasRegistry =
    !!property.matricula ||
    !!property.registry_office ||
    !!property.inscricao_municipal ||
    !!property.owner_cpf_cnpj;

  return (
    <section className="overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,260px)_1fr]">
        {/* ============================================================ */}
        {/* BLOCO 1 — Header com foto + badges                            */}
        {/* ============================================================ */}
        <div className="relative md:max-h-[260px]">
          <PropertyImage
            src={property.image_url}
            alt={property.title ?? "Foto do imóvel"}
            aspect="aspect-[16/10] md:aspect-auto md:h-full"
          />
          <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
            {property.property_type && (
              <Badge
                variant="secondary"
                className="bg-card/85 capitalize backdrop-blur-sm"
              >
                {property.property_type}
              </Badge>
            )}
            {property.legal_status && (
              <Badge
                variant="secondary"
                className="bg-card/85 capitalize backdrop-blur-sm"
                title="Modalidade do leilão"
              >
                <Gavel className="mr-1 size-3" /> {property.legal_status}
              </Badge>
            )}
            {property.occupancy_status === "ocupado" && (
              <Badge variant="warning" className="backdrop-blur-sm">
                Ocupado
              </Badge>
            )}
            {property.occupancy_status === "desocupado" && (
              <Badge variant="success" className="backdrop-blur-sm">
                Desocupado
              </Badge>
            )}
            {property.geocoding_confidence && (
              <Badge
                variant={
                  confidenceVariant[property.geocoding_confidence] ??
                  "secondary"
                }
                className="backdrop-blur-sm"
              >
                {confidenceLabel[property.geocoding_confidence] ??
                  property.geocoding_confidence}
              </Badge>
            )}
          </div>
        </div>

        {/* Informações */}
        <div className="flex flex-col gap-4 p-5 sm:p-6">
          {/* Título + endereço */}
          <div>
            <h1 className="text-xl font-semibold leading-snug tracking-tight sm:text-2xl">
              {property.title ?? "Imóvel sem título"}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {hasGeo ? (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="size-3.5 text-primary" />
                  {cityState || "—"}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <MapPinOff className="size-3.5" />
                  {cityState || "Localização não informada"}
                </span>
              )}
              {property.neighborhood && (
                <>
                  <span aria-hidden>·</span>
                  <span className="font-medium text-foreground">
                    {property.neighborhood}
                  </span>
                </>
              )}
              {property.address_full && (
                <>
                  <span aria-hidden>·</span>
                  <span className="line-clamp-1 max-w-md">
                    {property.address_full}
                  </span>
                </>
              )}
            </div>
            {property.condo_name && (
              <p className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Building2 className="size-3.5" /> {property.condo_name}
              </p>
            )}
          </div>

          {/* ========================================================== */}
          {/* BLOCO 2 — Atributos físicos                                 */}
          {/* ========================================================== */}
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
            {area && (
              <span
                className="inline-flex items-center gap-1"
                title={area.tooltip ?? undefined}
              >
                <Ruler className="size-3.5" /> {area.value}
              </span>
            )}
            {property.bedrooms != null && (
              <span className="inline-flex items-center gap-1">
                <BedDouble className="size-3.5" /> {property.bedrooms} quarto(s)
              </span>
            )}
            {property.bathrooms != null && (
              <span className="inline-flex items-center gap-1">
                <Bath className="size-3.5" /> {property.bathrooms} banheiro(s)
              </span>
            )}
            {property.parking_spaces != null && property.parking_spaces > 0 && (
              <span className="inline-flex items-center gap-1">
                <Car className="size-3.5" /> {property.parking_spaces} vaga(s)
              </span>
            )}
          </div>

          {/* ========================================================== */}
          {/* BLOCO 3 — Leilão (valores + datas + leiloeiro + custos)     */}
          {/* ========================================================== */}
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <PriceTile
                label="Avaliação"
                value={formatBRL(property.appraisal_value)}
                emptyWhenZero
              />
              <PriceTile
                label="1ª praça"
                value={formatBRL(property.minimum_bid_first)}
                sub={
                  property.first_auction_at
                    ? formatDateTimeBR(property.first_auction_at)
                    : null
                }
                emptyWhenZero
              />
              <PriceTile
                label="2ª praça"
                value={formatBRL(property.minimum_bid_second)}
                sub={
                  property.second_auction_at
                    ? formatDateTimeBR(property.second_auction_at)
                    : null
                }
                highlight
                emptyWhenZero
              />
              {hasCurrentBid && (
                <PriceTile
                  label="Lance atual"
                  value={formatBRL(property.current_bid)}
                  tone="warning"
                  sub="já arrematado"
                />
              )}
            </div>

            {/* Linha auxiliar com leiloeiro + custos do edital */}
            {(property.auctioneer_name ||
              property.auctioneer_lot_id ||
              hasArrears) && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                {property.auctioneer_name && (
                  <span className="inline-flex items-center gap-1">
                    <Gavel className="size-3" />
                    {property.auctioneer_name}
                  </span>
                )}
                {property.auctioneer_lot_id && (
                  <span>Lote {property.auctioneer_lot_id}</span>
                )}
                {(property.iptu_arrears ?? 0) > 0 && (
                  <span className="text-warning-700">
                    IPTU atrasado {formatBRL(property.iptu_arrears)}
                  </span>
                )}
                {(property.condo_arrears ?? 0) > 0 && (
                  <span className="text-warning-700">
                    Condomínio atrasado {formatBRL(property.condo_arrears)}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* ========================================================== */}
          {/* BLOCO 4 — Registro e identificação (expansível)             */}
          {/* ========================================================== */}
          {hasRegistry && (
            <details className="rounded-md border border-dashed bg-muted/20 p-2.5 text-xs">
              <summary className="cursor-pointer font-medium text-foreground hover:text-primary">
                <span className="inline-flex items-center gap-1.5">
                  <FileText className="size-3.5" />
                  Registro e identificação
                </span>
              </summary>
              <div className="mt-2 space-y-2">
                {(property.matricula || property.registry_office) && (
                  <div className="space-y-0.5">
                    {property.matricula && (
                      <div>
                        <span className="text-muted-foreground">Matrícula:</span>{" "}
                        <strong className="font-mono">
                          {property.matricula}
                        </strong>
                      </div>
                    )}
                    {property.registry_office && (
                      <div>
                        <span className="text-muted-foreground">Cartório:</span>{" "}
                        {property.registry_office}
                      </div>
                    )}
                    <div className="pt-1">
                      <Button
                        size="sm"
                        variant="outline"
                        asChild
                        className="h-7 text-[11px]"
                      >
                        <a
                          href={ONR_URL}
                          target="_blank"
                          rel="noreferrer"
                          title="Operador Nacional do Registro de Imóveis — solicite a certidão digital"
                        >
                          <Landmark className="mr-1 size-3" />
                          Abrir ONR
                          <ExternalLink className="ml-1 size-3" />
                        </a>
                      </Button>
                    </div>
                  </div>
                )}

                {property.inscricao_municipal && (
                  <div>
                    <span className="text-muted-foreground">
                      Inscrição municipal (IPTU):
                    </span>{" "}
                    <strong className="font-mono">
                      {property.inscricao_municipal}
                    </strong>
                  </div>
                )}

                {property.owner_cpf_cnpj && (
                  <div className="inline-flex items-center gap-1.5">
                    <IdCard className="size-3.5 text-muted-foreground" />
                    <span className="text-muted-foreground">
                      CPF/CNPJ do proprietário:
                    </span>{" "}
                    <strong className="font-mono">
                      {property.owner_cpf_cnpj}
                    </strong>
                  </div>
                )}
              </div>
            </details>
          )}

          {/* ========================================================== */}
          {/* BLOCO 5 — Descrição livre (expansível)                      */}
          {/* ========================================================== */}
          {property.description && property.description.trim() && (
            <details className="rounded-md border border-dashed bg-muted/20 p-2.5 text-xs">
              <summary className="cursor-pointer font-medium text-foreground hover:text-primary">
                <span className="inline-flex items-center gap-1.5">
                  <Home className="size-3.5" />
                  Descrição do anúncio
                </span>
              </summary>
              <p className="mt-2 whitespace-pre-line text-muted-foreground">
                {property.description}
              </p>
            </details>
          )}

          {/* Footer */}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <Calendar className="size-3.5" />
              Atualizado {formatDateTimeBR(property.updated_at)}
            </span>
            <a
              href={property.source_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 hover:text-primary"
            >
              Ver no leiloeiro <ExternalLink className="size-3" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

function PriceTile({
  label,
  value,
  sub,
  highlight,
  tone,
  emptyWhenZero,
}: {
  label: string;
  value: string;
  sub?: string | null;
  highlight?: boolean;
  tone?: "warning";
  /** Quando true, esconde o tile inteiro se o valor for "R$ 0,00" / "—". */
  emptyWhenZero?: boolean;
}) {
  // O `formatBRL` devolve "—" quando o valor é null/0; nesses casos
  // ocultamos o tile inteiro em vez de mostrar placeholder vazio.
  if (emptyWhenZero && (value === "—" || value === "R$ 0,00")) return null;

  const toneClasses =
    tone === "warning"
      ? "border-warning/40 bg-warning-50 text-warning-700"
      : highlight
        ? "border-primary/40 bg-primary-50 text-primary-700"
        : "bg-muted/30 text-foreground";

  return (
    <div className={cn("rounded-lg border p-2.5", toneClasses)}>
      <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums">{value}</div>
      {sub && (
        <div className="mt-0.5 text-[10px] text-muted-foreground tabular-nums">
          {sub}
        </div>
      )}
    </div>
  );
}
