/**
 * Gera o HTML standalone do relatório de oportunidade.
 *
 * Decisões:
 * - HTML único, sem dependências de runtime (CSS embutido). Isso garante
 *   que o arquivo abre offline, em qualquer navegador, fora do app.
 * - O mapa interativo carrega Google Maps a partir do navegador do
 *   usuário usando a mesma chave pública (NEXT_PUBLIC_GOOGLE_MAPS_API_KEY)
 *   — mesma que o app já usa. Sem ela, o relatório degrada graciosamente
 *   e mostra um aviso na seção do mapa.
 * - Toda a lógica de cluster/spider do ``ComparablesMap`` é portada
 *   abaixo em vanilla JS, dentro do próprio HTML — fora isso, o
 *   relatório é puramente declarativo.
 */

import type {
  DeepAnalysisRow,
  OpportunityResult,
  OpportunityScenario,
  Property,
  ValuationComparable,
  ValuationDetail,
} from "@/lib/api";

// =============================================================================
// Helpers de formatação (espelham frontend/lib/utils.ts mas zero deps).
// =============================================================================
const fmtBRL = (v: number | null | undefined): string => {
  if (v == null || !Number.isFinite(v)) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(v);
};

const fmtPct = (v: number | null | undefined, digits = 1): string => {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
};

/** Escapa string para uso seguro em HTML (text content). */
const esc = (s: unknown): string => {
  if (s == null) return "";
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
};

// =============================================================================
// Estilos embutidos
// =============================================================================
const STYLES = `
:root{
  --bg:#fafafa; --card:#ffffff; --fg:#0f172a; --muted:#64748b;
  --border:#e2e8f0; --primary:#2563eb; --primary-50:#eff6ff;
  --primary-100:#dbeafe; --primary-700:#1d4ed8;
  --success:#16a34a; --success-50:#f0fdf4; --success-100:#dcfce7;
  --success-700:#15803d;
  --warning:#d97706; --warning-50:#fffbeb;
  --danger:#dc2626; --danger-50:#fef2f2; --danger-100:#fee2e2;
  --danger-700:#b91c1c;
  --accent:#1e40af;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--fg);
  font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  font-feature-settings:"tnum" 1}
.wrap{max-width:1180px;margin:0 auto;padding:24px}
.section{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:20px;margin-bottom:18px;box-shadow:0 1px 2px rgba(15,23,42,.04)}
h1{font-size:24px;margin:0 0 4px;font-weight:600}
h2{font-size:18px;margin:0 0 12px;font-weight:600}
h3{font-size:14px;margin:0 0 6px;font-weight:600;text-transform:uppercase;
  letter-spacing:.04em;color:var(--muted)}
.muted{color:var(--muted);font-size:12px}
.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;
  font-weight:600;border:1px solid currentColor}
.tag.success{color:var(--success);background:rgba(22,163,74,.08)}
.tag.warning{color:var(--warning);background:rgba(217,119,6,.08)}
.tag.danger{color:var(--danger);background:rgba(220,38,38,.08)}
.tag.muted{color:var(--muted);background:#f1f5f9}
.grid-2{display:grid;grid-template-columns:280px 1fr;gap:18px}
@media(max-width:720px){.grid-2{grid-template-columns:1fr}}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:980px){.grid-3{grid-template-columns:repeat(2,1fr)}}
@media(max-width:720px){.grid-3{grid-template-columns:1fr}}
.field{padding:6px 0}
.field-label{font-size:11px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted)}
.field-value{font-size:14px;font-weight:500;margin-top:2px}
.thumb{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:8px;
  border:1px solid var(--border);background:#f1f5f9}

/* ============================================================
   Cenários — espelham o ScenarioCards do frontend
   ============================================================ */
.scenario{position:relative;overflow:hidden;background:var(--card);
  border:1px solid var(--border);border-radius:12px;padding:14px 14px 14px 18px;
  box-shadow:0 1px 2px rgba(15,23,42,.04)}
.scenario.highlight{box-shadow:0 4px 12px rgba(37,99,235,.10),0 1px 2px rgba(15,23,42,.04);
  border-color:rgba(37,99,235,.30)}
.scenario .bar{position:absolute;left:0;top:0;bottom:0;width:4px}
.scenario.s-pessimista .bar{background:var(--danger)}
.scenario.s-realista   .bar{background:var(--primary)}
.scenario.s-otimista   .bar{background:var(--success)}
.scenario .header{display:flex;flex-wrap:wrap;align-items:baseline;
  justify-content:space-between;gap:8px;margin-bottom:10px}
.scenario .chip{display:inline-flex;padding:2px 8px;border-radius:999px;
  font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.scenario.s-pessimista .chip{color:var(--danger-700);background:var(--danger-100)}
.scenario.s-realista   .chip{color:var(--primary-700);background:var(--primary-100)}
.scenario.s-otimista   .chip{color:var(--success-700);background:var(--success-100)}
.scenario .ref-tag{font-size:10px;font-weight:500;text-transform:uppercase;
  letter-spacing:.06em;color:var(--primary-700)}
.scenario .sale{font-size:12px;color:var(--muted)}
.scenario .summary{border:1px solid;border-radius:10px;padding:10px 12px;margin-top:4px}
.scenario.profit .summary{background:var(--success-50);border-color:rgba(22,163,74,.20)}
.scenario.loss   .summary{background:var(--danger-50);border-color:rgba(220,38,38,.20)}
.scenario .summary .line{display:flex;align-items:baseline;justify-content:space-between}
.scenario .summary .line + .line{margin-top:2px}
.scenario .summary .lbl{font-size:11px;color:var(--muted)}
.scenario .summary .val{font-weight:600;font-size:18px}
.scenario .summary .val.small{font-size:13px;font-weight:500}
.scenario.profit .summary .val{color:var(--success-700)}
.scenario.loss   .summary .val{color:var(--danger-700)}
.scenario .block{margin-top:10px;padding-top:10px;border-top:1px solid var(--border)}
.scenario .block .row{display:flex;align-items:baseline;justify-content:space-between;
  font-size:12px;padding:1px 0}
.scenario .block .row .lbl{color:var(--muted)}
.scenario .block .row .val{font-weight:500;color:var(--fg)}
.scenario .block .row.bold .val{font-weight:700}
.scenario .block.muted-block .row .val{color:var(--muted);font-weight:400}
.warnings{margin-top:10px;display:flex;flex-direction:column;gap:6px}
.warnings li{list-style:none;padding:6px 10px;border-radius:6px;font-size:12px;
  border:1px solid rgba(217,119,6,.4);background:rgba(217,119,6,.08);
  color:#92400e}
.assumptions{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:10px;margin-top:12px}
.assumptions .tile{border:1px solid var(--border);border-radius:8px;
  padding:8px 10px;background:#fafafa}
.assumptions .tile .lbl{font-size:10px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted)}
.assumptions .tile .val{font-size:14px;font-weight:600;margin-top:2px}
.assumptions .tile .src{font-size:10px;color:var(--muted);margin-top:1px}
.maxbid{margin-top:14px;padding:12px 14px;border:1px solid rgba(37,99,235,.25);
  background:var(--primary-50);border-radius:10px;display:flex;
  align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.maxbid .lbl{font-size:11px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--primary-700);font-weight:600}
.maxbid .val{font-size:20px;font-weight:700;color:var(--primary-700)}
.maxbid .sub{font-size:11px;color:var(--muted);margin-top:2px}
.maxbid.unreached{background:#fff7ed;border-color:rgba(217,119,6,.30)}
.maxbid.unreached .lbl,.maxbid.unreached .val{color:#9a3412}
#map{width:100%;height:520px;border-radius:8px;background:#e2e8f0;
  position:relative;overflow:hidden}
.map-fallback{display:flex;align-items:center;justify-content:center;
  height:100%;color:var(--muted);text-align:center;padding:20px}
.legend{position:absolute;bottom:12px;left:12px;background:rgba(255,255,255,.95);
  border:1px solid var(--border);border-radius:8px;padding:8px 10px;
  font-size:11px;line-height:1.4;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.legend .row{display:flex;align-items:center;gap:6px;margin-top:3px}
.legend .dot{width:10px;height:10px;border-radius:50%;border:2px solid #fff;
  box-shadow:0 0 0 1px #cbd5e1}
.flag-list{margin:6px 0 0;padding:0;list-style:none;display:flex;
  flex-direction:column;gap:6px}
.flag-list li{padding:6px 10px;border-radius:6px;font-size:12px;border:1px solid}
.flag-list li.green{border-color:rgba(22,163,74,.4);background:rgba(22,163,74,.08);color:#14532d}
.flag-list li.red{border-color:rgba(217,119,6,.4);background:rgba(217,119,6,.08);color:#7c2d12}
.score-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:10px}
@media(max-width:720px){.score-grid{grid-template-columns:repeat(2,1fr)}}
.score-tile{border:1px solid var(--border);border-radius:8px;padding:10px;background:#fafafa}
.score-tile .lbl{font-size:10px;text-transform:uppercase;color:var(--muted);
  letter-spacing:.04em}
.score-tile .val{font-size:18px;font-weight:700;margin-top:4px}
.score-tile .sub{font-size:11px;color:var(--muted);margin-top:2px}
.report-link{color:var(--primary);text-decoration:none;font-weight:500}
.report-link:hover{text-decoration:underline}
table.kvt{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
table.kvt td{padding:4px 6px;border-bottom:1px dashed #e2e8f0}
table.kvt td:first-child{color:var(--muted);width:160px}
.print-hide{}
@media print{
  body{background:#fff}
  .section{break-inside:avoid;border:none;box-shadow:none}
  .wrap{max-width:100%;padding:0}
  #map{height:380px}
}
`;

// =============================================================================
// Templates HTML
// =============================================================================
function renderProperty(property: Property): string {
  const fmtArea = (v: number | null | undefined): string =>
    v != null && Number.isFinite(v) ? `${v} m²` : "—";
  const fmtDate = (iso: string | null | undefined): string => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
      });
    } catch {
      return iso;
    }
  };

  // Mostra "Construída / Total" só quando os dois valores existem e
  // diferem (caso típico de apartamento Caixa). Caso contrário usa o
  // que estiver disponível.
  const areaLabel =
    property.area_built_m2 != null &&
    property.area_total_m2 != null &&
    property.area_built_m2 !== property.area_total_m2
      ? `${fmtArea(property.area_built_m2)} construída · ${fmtArea(property.area_total_m2)} total`
      : fmtArea(property.area_total_m2 ?? property.area_built_m2);

  const fields: Array<[string, string]> = [
    ["Tipo", esc(property.property_type ?? "—")],
    ["Área", areaLabel],
    ["Quartos", property.bedrooms != null ? String(property.bedrooms) : "—"],
    ["Banheiros", property.bathrooms != null ? String(property.bathrooms) : "—"],
    [
      "Vagas",
      property.parking_spaces != null ? String(property.parking_spaces) : "—",
    ],
    ["Avaliação (edital)", fmtBRL(property.appraisal_value)],
    ["1ª praça", fmtBRL(property.minimum_bid_first)],
    ["2ª praça", fmtBRL(property.minimum_bid_second)],
    ["Data 1ª praça", esc(fmtDate(property.first_auction_at))],
    ["Data 2ª praça", esc(fmtDate(property.second_auction_at))],
    ["Ocupação", esc(property.occupancy_status ?? "—")],
    ["Status legal", esc(property.legal_status ?? "—")],
  ];
  if (property.condo_name) {
    fields.unshift(["Condomínio", esc(property.condo_name)]);
  }
  if (property.auctioneer_name) {
    fields.push(["Leiloeiro", esc(property.auctioneer_name)]);
  }
  if (property.auctioneer_lot_id) {
    fields.push(["Nº do lote", esc(property.auctioneer_lot_id)]);
  }
  if (property.iptu_arrears && property.iptu_arrears > 0) {
    fields.push(["IPTU em atraso (edital)", fmtBRL(property.iptu_arrears)]);
  }
  if (property.condo_arrears && property.condo_arrears > 0) {
    fields.push(["Condomínio em atraso (edital)", fmtBRL(property.condo_arrears)]);
  }

  return `
<section class="section">
  <h1>Relatório de Oportunidade</h1>
  <div class="muted">Gerado em ${esc(
    new Date().toLocaleString("pt-BR"),
  )}</div>
  <div style="margin-top:14px" class="grid-2">
    ${
      property.image_url
        ? `<img src="${esc(property.image_url)}" alt="${esc(
            property.title ?? "Foto do imóvel",
          )}" class="thumb" referrerpolicy="no-referrer" onerror="this.style.display='none'">`
        : `<div class="thumb" style="display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px">Sem foto</div>`
    }
    <div>
      <h2>${esc(property.title ?? "Imóvel")}</h2>
      <div class="muted">${esc(property.address_full ?? "")}</div>
      <table class="kvt">
        ${fields
          .map(
            ([k, v]) =>
              `<tr><td>${esc(k)}</td><td>${v}</td></tr>`,
          )
          .join("")}
      </table>
      ${
        property.source_url
          ? `<p style="margin-top:12px"><a class="report-link" href="${esc(
              property.source_url,
            )}" target="_blank" rel="noreferrer noopener">Abrir anúncio no leiloeiro ↗</a></p>`
          : ""
      }
    </div>
  </div>
</section>`;
}

/**
 * Renderiza um card de cenário no MESMO formato do ``ScenarioCards``
 * do frontend:
 *
 *   1. Header: chip do cenário, tag "referência" para o realista, e
 *      "Venda R$ X" à direita.
 *   2. Caixa colorida (verde/vermelha) com Lucro líquido + ROI líquido.
 *   3. Bloco de custos: Lance, Comissão, ITBI, Registro, IPTU/condo
 *      atrasados (apenas quando > 0), Reforma e Outros (idem), e o
 *      Custo de aquisição em negrito.
 *   4. Bloco "muted" pós-venda: Corretor, IR, Lucro bruto, ROI bruto.
 */
function renderScenario(s: OpportunityScenario, highlight = false): string {
  const META: Record<
    OpportunityScenario["label"],
    { label: string; cls: string }
  > = {
    pessimista: { label: "Pessimista", cls: "s-pessimista" },
    realista: { label: "Realista", cls: "s-realista" },
    otimista: { label: "Otimista", cls: "s-otimista" },
  };
  const m = META[s.label];
  const isProfit = s.net_profit >= 0;
  const profitCls = isProfit ? "profit" : "loss";
  const cls = `scenario ${m.cls} ${profitCls}${highlight ? " highlight" : ""}`;

  // Linha condicional ("só mostra se > 0") espelhando o frontend.
  const optRow = (label: string, value: number): string =>
    value > 0
      ? `<div class="row"><span class="lbl">${esc(label)}</span><span class="val">${fmtBRL(value)}</span></div>`
      : "";

  return `
<div class="${cls}">
  <span class="bar" aria-hidden="true"></span>
  <div class="header">
    <div style="display:flex;align-items:center;gap:8px">
      <span class="chip">${esc(m.label)}</span>
      ${highlight ? '<span class="ref-tag">referência</span>' : ""}
    </div>
    <span class="sale">Venda ${fmtBRL(s.sale_price)}</span>
  </div>

  <div class="summary">
    <div class="line">
      <span class="lbl">Lucro líquido</span>
      <span class="val">${fmtBRL(s.net_profit)}</span>
    </div>
    <div class="line">
      <span class="lbl">ROI líquido</span>
      <span class="val small">${fmtPct(s.net_roi_pct)}</span>
    </div>
  </div>

  <div class="block">
    <div class="row"><span class="lbl">Lance</span><span class="val">${fmtBRL(s.bid)}</span></div>
    <div class="row"><span class="lbl">Comissão leiloeiro</span><span class="val">${fmtBRL(s.auctioneer_fee)}</span></div>
    <div class="row"><span class="lbl">ITBI</span><span class="val">${fmtBRL(s.itbi)}</span></div>
    <div class="row"><span class="lbl">Registro</span><span class="val">${fmtBRL(s.registration)}</span></div>
    ${optRow("IPTU atrasado", s.iptu_arrears)}
    ${optRow("Condomínio atrasado", s.condo_arrears)}
    ${optRow("Reforma", s.renovation_cost)}
    ${optRow("Outros", s.other_costs)}
    <div class="row bold"><span class="lbl">Custo aquisição</span><span class="val">${fmtBRL(s.total_acquisition_cost)}</span></div>
  </div>

  <div class="block muted-block">
    <div class="row"><span class="lbl">Corretor (venda)</span><span class="val">${fmtBRL(s.realtor_fee)}</span></div>
    <div class="row"><span class="lbl">Imposto de renda</span><span class="val">${fmtBRL(s.income_tax)}</span></div>
    <div class="row"><span class="lbl">Lucro bruto</span><span class="val">${fmtBRL(s.gross_profit)}</span></div>
    <div class="row"><span class="lbl">ROI bruto</span><span class="val">${fmtPct(s.gross_roi_pct)}</span></div>
  </div>

  ${renderFinancingInline(s)}
</div>`;
}

const REPORT_FINANCING_LABEL: Record<string, string> = {
  financed_bank: "Financiamento bancário",
  installments_judicial: "Parcelamento judicial",
};

function renderFinancingInline(s: OpportunityScenario): string {
  const f = s.financing;
  if (!f || f.mode === "cash") return "";
  const leverage = f.entry > 0 ? s.bid / f.entry : null;
  const label = REPORT_FINANCING_LABEL[f.mode] ?? f.mode;
  const leverageBadge =
    leverage != null && leverage > 1
      ? `<span class="ref-tag" style="margin-left:6px">Alavancado ${leverage.toFixed(1)}×</span>`
      : "";
  return `
  <div class="block muted-block" style="border-style:dashed">
    <div class="row" style="font-weight:600;text-transform:uppercase;letter-spacing:.04em;font-size:11px">
      <span>${esc(label)}${leverageBadge}</span>
    </div>
    <div class="row"><span class="lbl">Entrada</span><span class="val">${fmtBRL(f.entry)}</span></div>
    <div class="row"><span class="lbl">Parcela mensal</span><span class="val">${fmtBRL(f.pmt)}</span></div>
    <div class="row"><span class="lbl">Pagas no holding</span><span class="val">${fmtBRL(f.holding_payments)}</span></div>
    <div class="row"><span class="lbl">Saldo devedor na venda</span><span class="val">${fmtBRL(f.balance_at_sale)}</span></div>
    <div class="row"><span class="lbl">Juros pagos</span><span class="val">${fmtBRL(f.interest_paid_holding)}</span></div>
  </div>`;
}

function paymentModeLabel(mode: string | null | undefined): string {
  const m = mode ?? "cash";
  if (m === "financed_bank") return "financiado";
  if (m === "installments_judicial") return "parcelado (judicial)";
  return "à vista";
}

function renderOpportunity(
  result: OpportunityResult,
  property: Property,
): string {
  const verdictMap: Record<
    OpportunityResult["verdict"],
    { label: string; cls: string }
  > = {
    BOA_OPORTUNIDADE: { label: "Boa oportunidade", cls: "success" },
    BOA_COM_RESSALVAS: { label: "Boa, com ressalvas", cls: "warning" },
    NEUTRO: { label: "Neutro", cls: "muted" },
    INVIAVEL: { label: "Inviável", cls: "danger" },
    INDETERMINADO: { label: "Indeterminado", cls: "muted" },
  };
  const v = verdictMap[result.verdict];

  // Rótulos das fontes das premissas — espelham o que o usuário vê no
  // formulário de oportunidade (ITBI/registro/comissão/IR).
  const ITBI_SRC: Record<string, string> = {
    city_table: "tabela do município",
    default: "default",
    override: "ajuste manual",
  };
  const FEE_SRC: Record<string, string> = {
    edital: "do edital",
    caixa_zero: "Caixa direta",
    no_auctioneer: "sem leiloeiro",
    default: "default 5%",
    override: "ajuste manual",
  };
  const a = result.assumptions;
  const buyerLabel = result.input.buyer_type === "PJ" ? "PJ" : "PF";
  const taxBasisLabel =
    a.income_tax_basis === "sale_price" ? "sobre venda" : "sobre lucro";

  const maxBidBlock =
    result.max_bid_for_target != null
      ? `<div class="maxbid">
          <div>
            <div class="lbl">Lance máximo para ROI alvo</div>
            <div class="sub">Maior lance que ainda atinge ${fmtPct(result.input.target_net_roi_pct, 0)} líquido no cenário realista.</div>
          </div>
          <div class="val">${fmtBRL(result.max_bid_for_target)}</div>
        </div>`
      : `<div class="maxbid unreached">
          <div>
            <div class="lbl">Lance máximo para ROI alvo</div>
            <div class="sub">ROI alvo de ${fmtPct(result.input.target_net_roi_pct, 0)} inalcançável com as premissas atuais — reduza custos ou eleve o preço de venda esperado.</div>
          </div>
          <div class="val">—</div>
        </div>`;

  return `
<section class="section">
  <h2>Análise de oportunidade
    <span class="tag ${v.cls}" style="margin-left:8px">${esc(v.label)}</span>
  </h2>
  <div class="muted">
    Comprador ${esc(buyerLabel)} · ROI alvo
    ${fmtPct(result.input.target_net_roi_pct, 0)} · Reforma
    ${esc(result.input.renovation_level)} · Pagamento ${esc(
      paymentModeLabel(result.input.payment_mode),
    )} · Imóvel em ${esc(property.city ?? "")}/${esc(property.state ?? "")}
  </div>

  <div class="grid-3" style="margin-top:14px">
    ${renderScenario(result.pessimista)}
    ${renderScenario(result.realista, true)}
    ${renderScenario(result.otimista)}
  </div>

  ${maxBidBlock}

  <div style="margin-top:14px">
    <h3>Premissas usadas</h3>
    <div class="assumptions">
      <div class="tile">
        <div class="lbl">ITBI</div>
        <div class="val">${fmtPct(a.itbi_pct, 2)}</div>
        <div class="src">${esc(ITBI_SRC[a.itbi_source] ?? a.itbi_source)}</div>
      </div>
      <div class="tile">
        <div class="lbl">Comissão leiloeiro</div>
        <div class="val">${fmtPct(a.auctioneer_fee_pct, 2)}</div>
        <div class="src">${esc(FEE_SRC[a.auctioneer_fee_source] ?? a.auctioneer_fee_source)}</div>
      </div>
      <div class="tile">
        <div class="lbl">Registro</div>
        <div class="val">${fmtPct(a.registration_pct, 2)}</div>
        <div class="src">cartório</div>
      </div>
      <div class="tile">
        <div class="lbl">Corretor (venda)</div>
        <div class="val">${fmtPct(a.realtor_fee_pct, 1)}</div>
        <div class="src">comissão padrão</div>
      </div>
      <div class="tile">
        <div class="lbl">Imposto de renda (${esc(buyerLabel)})</div>
        <div class="val">${fmtPct(a.income_tax_pct, 1)}</div>
        <div class="src">${esc(taxBasisLabel)}</div>
      </div>
      <div class="tile">
        <div class="lbl">Reforma (R$/m²)</div>
        <div class="val">${fmtBRL(a.renovation_per_m2)}</div>
        <div class="src">${esc(result.input.renovation_level)}</div>
      </div>
    </div>
  </div>

  ${
    result.warnings.length > 0
      ? `<div style="margin-top:14px"><h3>Pontos de atenção</h3>
         <ul class="warnings">${result.warnings
           .map((w) => `<li>${esc(w)}</li>`)
           .join("")}</ul></div>`
      : ""
  }
</section>`;
}

function renderMap(
  property: Property,
  comparables: ValuationComparable[],
  apiKey: string,
): string {
  if (
    property.latitude == null ||
    property.longitude == null
  ) {
    return `
<section class="section">
  <h2>Mapa</h2>
  <p class="muted">Imóvel sem geolocalização — mapa indisponível.</p>
</section>`;
  }
  if (!apiKey) {
    return `
<section class="section">
  <h2>Mapa</h2>
  <div id="map"><div class="map-fallback">
    Mapa indisponível: defina <code>NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code>
    e regenere o relatório.
  </div></div>
</section>`;
  }

  // Apenas comparables com lat/lng — o resto não pode ir no mapa.
  const indexed = comparables
    .map((c, i) => ({ ...c, _idx: i + 1 }))
    .filter(
      (c) =>
        c.listings &&
        typeof c.listings.latitude === "number" &&
        typeof c.listings.longitude === "number" &&
        Number.isFinite(c.listings.latitude as number) &&
        Number.isFinite(c.listings.longitude as number),
    );

  const reportData = {
    target: {
      lat: property.latitude,
      lng: property.longitude,
      title: property.title,
      address: property.address_full,
      appraisal: property.appraisal_value,
      area: property.area_total_m2,
      sourceUrl: property.source_url,
    },
    comparables: indexed.map((c) => ({
      id: c.listings.id,
      idx: c._idx,
      lat: c.listings.latitude,
      lng: c.listings.longitude,
      used: c.used,
      price: c.listings.listed_price,
      area: c.listings.area_total_m2,
      bedrooms: c.listings.bedrooms,
      parking: c.listings.parking_spaces,
      neighborhood: c.listings.neighborhood,
      city: c.listings.city,
      state: c.listings.state,
      sourceUrl: c.listings.source_url,
      distanceM: c.distance_m,
      similarity: c.similarity_score,
      rejectionReason: c.rejection_reason,
    })),
  };

  // Conta de "used" para legenda.
  const nUsed = indexed.filter((c) => c.used).length;
  const nRejected = indexed.length - nUsed;

  return `
<section class="section">
  <h2>Mapa de comparáveis (${indexed.length})</h2>
  <p class="muted">
    Pin vermelho = imóvel do leilão · círculos verdes = comparáveis usados
    na avaliação · cinzas = rejeitados · azuis = vários no mesmo ponto
    (clique para expandir).
  </p>
  <div id="map">
    <div class="legend" id="legend">
      <div style="font-weight:600;color:#334155">Legenda</div>
      <div class="row">
        <span class="dot" style="background:#dc2626"></span>
        <span>Imóvel do leilão</span>
      </div>
      <div class="row">
        <span class="dot" style="background:#16a34a"></span>
        <span>Comparável usado (${nUsed})</span>
      </div>
      ${
        nRejected > 0
          ? `<div class="row"><span class="dot" style="background:#9ca3af"></span><span>Rejeitado (${nRejected})</span></div>`
          : ""
      }
    </div>
  </div>
  <script>
    window.__REPORT_MAP__ = ${JSON.stringify(reportData)};
  </script>
  <script src="https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(
    apiKey,
  )}&language=pt-BR&region=BR&callback=__initReportMap__&loading=async" async defer></script>
  <script>${MAP_SCRIPT}</script>
</section>`;
}

// -----------------------------------------------------------------------------
// Vision LLM — galeria do ConditionAssessment (Street View + aérea + edital).
// -----------------------------------------------------------------------------
const COND_SLOT_LABEL: Record<string, string> = {
  aerial: "Vista aérea",
  sv_front: "Frente do imóvel",
  sv_left: "Vizinho à esquerda",
  sv_right: "Vizinho à direita",
  sv_back: "Outro lado da rua",
  listing: "Foto do edital",
};
const COND_SLOT_ORDER = [
  "aerial",
  "sv_front",
  "sv_left",
  "sv_right",
  "sv_back",
  "listing",
];
const COND_SV_HEADING_BY_SLOT: Record<string, number> = {
  sv_front: 0,
  sv_left: 90,
  sv_back: 180,
  sv_right: 270,
};
const COND_NEIGHBORHOOD_LABEL: Record<string, string> = {
  uniforme: "Uniforme",
  misto: "Misto",
  precario: "Precário",
};
const COND_VS_LABEL: Record<string, string> = {
  acima: "Acima dos vizinhos",
  igual: "Compatível",
  abaixo: "Abaixo dos vizinhos",
};
const COND_RENO_LABEL: Record<string, string> = {
  none: "Nenhuma",
  cosmetic: "Cosmética",
  light: "Leve",
  basic: "Básica",
  moderate: "Moderada",
  full: "Completa",
  premium: "Premium",
};

function condSlotFromUrl(url: string): string {
  const filename = url.split("/").pop() || "";
  return filename.replace(/\.[^.]+$/, "");
}

function condMapsLinkForSlot(
  slot: string,
  url: string,
  lat: number | null | undefined,
  lng: number | null | undefined,
): string {
  if (slot === "listing") return url;
  if (lat == null || lng == null) return url;
  if (slot === "aerial") {
    return `https://www.google.com/maps?q=${lat},${lng}&t=k&z=19`;
  }
  const heading = COND_SV_HEADING_BY_SLOT[slot];
  if (heading != null) {
    return (
      "https://www.google.com/maps/@?api=1&map_action=pano" +
      `&viewpoint=${lat},${lng}&heading=${heading}&pitch=0&fov=80`
    );
  }
  return url;
}

function renderConditionAssessment(
  deep: DeepAnalysisRow,
  property: Property,
): string {
  const cond = deep.condition_assessment;
  if (!cond) return "";
  const imageUrls = cond.image_urls ?? [];
  const riskFlags = cond.risk_flags ?? [];
  const hasInsights =
    cond.neighborhood_pattern != null ||
    cond.property_vs_neighbors != null ||
    cond.pool_observed_nearby != null ||
    cond.suggested_renovation_level != null ||
    riskFlags.length > 0;
  if (!hasInsights && imageUrls.length === 0) return "";

  const badge = (label: string, value: string): string =>
    `<span style="font-size:12px"><span class="muted">${esc(label)}:</span> <strong>${esc(value)}</strong></span>`;

  const insights: string[] = [];
  if (cond.neighborhood_pattern) {
    insights.push(
      badge(
        "Padrão do bairro",
        COND_NEIGHBORHOOD_LABEL[cond.neighborhood_pattern] ??
          cond.neighborhood_pattern,
      ),
    );
  }
  if (cond.property_vs_neighbors) {
    insights.push(
      badge(
        "Imóvel vs vizinhos",
        COND_VS_LABEL[cond.property_vs_neighbors] ??
          cond.property_vs_neighbors,
      ),
    );
  }
  if (cond.pool_observed_nearby != null) {
    insights.push(
      badge("Piscina próxima", cond.pool_observed_nearby ? "Sim" : "Não"),
    );
  }
  if (cond.suggested_renovation_level) {
    insights.push(
      badge(
        "Reforma sugerida",
        COND_RENO_LABEL[cond.suggested_renovation_level] ??
          cond.suggested_renovation_level,
      ),
    );
  }

  const ordered = [...imageUrls].sort((a, b) => {
    const ai = COND_SLOT_ORDER.indexOf(condSlotFromUrl(a));
    const bi = COND_SLOT_ORDER.indexOf(condSlotFromUrl(b));
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  const gallery =
    ordered.length === 0
      ? ""
      : `
      <div style="margin-top:10px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
        ${ordered
          .map((url) => {
            const slot = condSlotFromUrl(url);
            const label = COND_SLOT_LABEL[slot] ?? slot;
            const href = condMapsLinkForSlot(
              slot,
              url,
              property.latitude,
              property.longitude,
            );
            return `<a href="${esc(href)}" target="_blank" rel="noreferrer"
              style="display:block;border:1px solid var(--border);border-radius:6px;overflow:hidden;text-decoration:none;color:inherit"
              title="${esc(label)} — abrir no Google Maps">
              <img src="${esc(url)}" alt="${esc(label)}"
                style="display:block;width:100%;aspect-ratio:16/9;object-fit:cover"/>
              <div style="padding:4px 8px;font-size:11px;color:var(--muted)">${esc(label)}</div>
            </a>`;
          })
          .join("")}
      </div>`;

  const risks =
    riskFlags.length === 0
      ? ""
      : `
      <div style="margin-top:10px">
        <h3 style="margin:0 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#991b1b">Riscos do entorno observados</h3>
        <ul class="flag-list">
          ${riskFlags.map((f) => `<li class="red">${esc(f)}</li>`).join("")}
        </ul>
      </div>`;

  const notes = cond.notes
    ? `<p style="margin:8px 0 0;font-size:11px;color:var(--muted)">${esc(cond.notes)}</p>`
    : "";

  return `
    <div style="margin-top:14px;border:1px dashed var(--border);border-radius:8px;padding:12px;background:rgba(0,0,0,.02)">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:8px">
        <h3 style="margin:0;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)">
          Análise visual do entorno
        </h3>
        ${cond.confidence ? `<span class="tag muted" style="font-size:10px">confiança ${esc(cond.confidence)}</span>` : ""}
      </div>
      ${insights.length > 0 ? `<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:12px">${insights.join("")}</div>` : ""}
      ${gallery}
      ${risks}
      ${notes}
      <p style="margin:8px 0 0;font-size:10px;color:var(--muted);font-style:italic">
        Sinal informativo — não substitui o nível de reforma informado no Agente 3.
      </p>
    </div>`;
}

// -----------------------------------------------------------------------------
// Liquidez: subtítulo combina densidade (listings/km²) + população
// -----------------------------------------------------------------------------
function condLiquiditySub(deep: DeepAnalysisRow): string | undefined {
  const ev = deep.liquidity_evidence as
    | { listings_per_km2?: number | null }
    | null
    | undefined;
  const density = ev?.listings_per_km2;
  const parts: string[] = [];
  if (typeof density === "number" && Number.isFinite(density)) {
    parts.push(`${density.toFixed(1)} listings/km²`);
  }
  if (deep.city_population != null) {
    parts.push(`${deep.city_population.toLocaleString("pt-BR")} hab.`);
  }
  return parts.length > 0 ? parts.join(" · ") : undefined;
}

// -----------------------------------------------------------------------------
// Classe do bairro + 3 bairros concorrentes
// -----------------------------------------------------------------------------
const COND_TIER_LABEL: Record<string, string> = {
  A: "A · premium",
  B: "B · médio-alto",
  C: "C · médio",
  D: "D · popular",
};
const COND_TIER_CLASS: Record<string, string> = {
  A: "success",
  B: "muted",
  C: "muted",
  D: "warning",
};

function renderNeighborhoodClass(deep: DeepAnalysisRow): string {
  const cls = deep.neighborhood_class;
  if (!cls) return "";
  const competitors = cls.competing_neighborhoods ?? [];
  const tierLabel = cls.tier ? COND_TIER_LABEL[cls.tier] : null;
  const tierCls = cls.tier ? COND_TIER_CLASS[cls.tier] : "muted";
  const ratioPct =
    cls.ratio != null ? `${(cls.ratio * 100).toFixed(0)}% da cidade` : null;

  const header = `
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:8px">
      <h3 style="margin:0;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)">
        Classe do bairro
      </h3>
      ${cls.confidence ? `<span class="tag muted" style="font-size:10px">confiança ${esc(cls.confidence)}</span>` : ""}
    </div>`;

  const body = tierLabel
    ? `
    <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:12px;margin-top:6px">
      <span class="tag ${tierCls}">${esc(tierLabel)}</span>
      ${cls.target_ppm2_median != null ? `<span><span class="muted">ppm² bairro:</span> <strong>${esc(fmtBRL(cls.target_ppm2_median))}</strong></span>` : ""}
      ${cls.city_ppm2_brl != null ? `<span><span class="muted">ppm² cidade:</span> <strong>${esc(fmtBRL(cls.city_ppm2_brl))}</strong></span>` : ""}
      ${ratioPct ? `<span class="muted">${esc(ratioPct)}</span>` : ""}
    </div>`
    : `<p class="muted" style="margin:6px 0 0;font-size:12px">Amostra insuficiente no bairro para classificação.</p>`;

  const compList =
    competitors.length === 0
      ? ""
      : `
    <div style="margin-top:10px">
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px">
        Bairros concorrentes (ppm² semelhante)
      </div>
      <ul style="list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:4px;font-size:12px">
        ${competitors
          .map(
            (c) => `<li style="display:flex;justify-content:space-between;gap:8px;border:1px solid var(--border);border-radius:6px;padding:4px 8px">
            <strong>${esc(c.name)}</strong>
            <span class="muted" style="font-size:11px">${c.distance_km.toFixed(1)} km · ${esc(fmtBRL(c.ppm2_median))}/m² · ${c.n_listings} anúncios</span>
          </li>`,
          )
          .join("")}
      </ul>
    </div>`;

  return `
    <div style="margin-top:14px;border:1px dashed var(--border);border-radius:8px;padding:12px;background:rgba(0,0,0,.02)">
      ${header}
      ${body}
      ${compList}
    </div>`;
}

function renderDeep(deep: DeepAnalysisRow, property: Property): string {
  const score = deep.overall_score;
  const scoreCls =
    score == null
      ? "muted"
      : score >= 4
        ? "success"
        : score === 3
          ? "muted"
          : score === 2
            ? "warning"
            : "danger";

  const tile = (
    label: string,
    value: string,
    sub?: string,
  ): string => `
    <div class="score-tile">
      <div class="lbl">${esc(label)}</div>
      <div class="val">${esc(value)}</div>
      ${sub ? `<div class="sub">${esc(sub)}</div>` : ""}
    </div>`;

  const meters = (m: number | null | undefined): string => {
    if (m == null) return "—";
    return m < 1000 ? `${m} m` : `${(m / 1000).toFixed(2)} km`;
  };

  const flagsBlock = (
    title: string,
    items: string[] | null | undefined,
    kind: "green" | "red",
  ): string => {
    if (!items || items.length === 0) return "";
    return `
      <div style="margin-top:14px">
        <h3>${esc(title)}</h3>
        <ul class="flag-list">
          ${items
            .map((it) => `<li class="${kind}">${esc(it)}</li>`)
            .join("")}
        </ul>
      </div>`;
  };

  const recsBlock =
    deep.recommendations && deep.recommendations.length > 0
      ? `
        <div style="margin-top:14px">
          <h3>Recomendações de diligência</h3>
          <ul style="margin:0;padding-left:18px;font-size:12px">
            ${deep.recommendations.map((r) => `<li>${esc(r)}</li>`).join("")}
          </ul>
        </div>`
      : "";

  const risksBlock =
    deep.urban_risks && deep.urban_risks.length > 0
      ? `
        <div style="margin-top:14px">
          <h3>Riscos urbanos identificados</h3>
          <ul style="margin:0;padding-left:18px;font-size:12px">
            ${deep.urban_risks
              .map(
                (r) =>
                  `<li><strong>${esc(r.type.toUpperCase())}</strong> — ${esc(
                    r.summary,
                  )} <em class="muted">(confiança ${esc(r.confidence)})</em></li>`,
              )
              .join("")}
          </ul>
        </div>`
      : "";

  return `
<section class="section">
  <h2>Análise aprofundada
    ${
      score != null
        ? `<span class="tag ${scoreCls}" style="margin-left:8px">Score ${score}/5</span>`
        : ""
    }
  </h2>
  <div class="muted">
    Concluída em ${esc(
      deep.completed_at
        ? new Date(deep.completed_at).toLocaleString("pt-BR")
        : "—",
    )}
    ${
      deep.duration_ms != null
        ? `· tempo ${(deep.duration_ms / 1000).toFixed(1)}s`
        : ""
    }
    ${
      deep.firecrawl_calls != null
        ? `· ${deep.firecrawl_calls} fontes externas`
        : ""
    }
  </div>

  <div class="score-grid">
    ${tile(
      "Liquidez",
      deep.liquidity_score != null ? `${deep.liquidity_score}/5` : "—",
      condLiquiditySub(deep),
    )}
    ${tile(
      "Flipping",
      deep.flipping_potential_score != null
        ? `${deep.flipping_potential_score}/5`
        : "—",
      deep.neighborhood_price_p90 != null
        ? `p90 ${fmtBRL(deep.neighborhood_price_p90)}`
        : undefined,
    )}
    ${tile(
      "Outlier",
      deep.is_outlier_size || deep.is_outlier_price ? "Atípico" : "Típico",
      `z(área) ${deep.size_zscore?.toFixed(1) ?? "—"} · z(preço) ${
        deep.price_zscore?.toFixed(1) ?? "—"
      }`,
    )}
    ${tile(
      "Tendência 12m",
      deep.price_trend_12m_pct != null
        ? `${deep.price_trend_12m_pct > 0 ? "+" : ""}${deep.price_trend_12m_pct.toFixed(1)}%`
        : "—",
      deep.price_trend_confidence
        ? `confiança ${deep.price_trend_confidence}`
        : undefined,
    )}
  </div>

  <div style="margin-top:10px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px;font-size:12px">
    <div><span class="muted">Metrô / estação:</span> ${esc(
      meters(deep.nearest_metro_m),
    )}</div>
    <div><span class="muted">Escola:</span> ${esc(
      meters(deep.nearest_school_m),
    )}</div>
    <div><span class="muted">Hospital:</span> ${esc(
      meters(deep.nearest_hospital_m),
    )}</div>
  </div>

  ${renderNeighborhoodClass(deep)}

  ${flagsBlock("Pontos a favor", deep.green_flags, "green")}
  ${flagsBlock("Pontos de atenção", deep.red_flags, "red")}
  ${renderConditionAssessment(deep, property)}
  ${risksBlock}
  ${recsBlock}

  ${
    deep.prior_auction_count != null && deep.prior_auction_count > 0
      ? `<p style="margin-top:14px;font-size:12px;color:#7c2d12">
          <strong>Histórico de leilão:</strong> ${deep.prior_auction_count} menção(ões)
          a leilões anteriores deste imóvel (verificação manual recomendada).
        </p>`
      : ""
  }

  ${
    deep.source_documents && deep.source_documents.length > 0
      ? `<details style="margin-top:14px">
          <summary><strong>Fontes consultadas (${deep.source_documents.length})</strong></summary>
          <ul style="margin:8px 0 0;padding-left:18px;font-size:11px">
            ${deep.source_documents
              .map(
                (s) =>
                  `<li><a class="report-link" href="${esc(
                    s.url,
                  )}" target="_blank" rel="noreferrer">${esc(s.title || s.url)}</a></li>`,
              )
              .join("")}
          </ul>
        </details>`
      : ""
  }
</section>`;
}

// =============================================================================
// Map script (vanilla JS, embutido no HTML standalone).
// Reproduz cluster + spider do ComparablesMap em ~120 linhas.
// =============================================================================
const MAP_SCRIPT = `
function __initReportMap__(){
  var data = window.__REPORT_MAP__ || {};
  if (!data.target || data.target.lat == null) return;
  var mapEl = document.getElementById('map');
  // Remove o stub do legend/fallback ao inicializar (vamos re-adicionar depois).
  var legendEl = document.getElementById('legend');

  var map = new google.maps.Map(mapEl, {
    center: { lat: data.target.lat, lng: data.target.lng },
    zoom: 14,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: true,
    clickableIcons: false,
  });
  if (legendEl) mapEl.appendChild(legendEl);

  var bounds = new google.maps.LatLngBounds();
  bounds.extend({ lat: data.target.lat, lng: data.target.lng });

  // Pin do imóvel-alvo (gota vermelha clássica).
  var targetSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="34" height="46" viewBox="0 0 34 46">'+
    '<path d="M17 1.5C9 1.5 2.5 8 2.5 16c0 11.5 14.5 28 14.5 28s14.5-16.5 14.5-28C31.5 8 25 1.5 17 1.5z" fill="#dc2626" stroke="#fff" stroke-width="2.5"/>'+
    '<circle cx="17" cy="16" r="5.5" fill="#fff"/></svg>';
  var targetIcon = {
    url: 'data:image/svg+xml;utf8,' + encodeURIComponent(targetSvg),
    scaledSize: new google.maps.Size(34,46),
    anchor: new google.maps.Point(17,44),
  };
  var targetMarker = new google.maps.Marker({
    position: { lat: data.target.lat, lng: data.target.lng },
    map: map, icon: targetIcon, zIndex: 9999,
    title: data.target.title || 'Imóvel do leilão',
  });
  var info = new google.maps.InfoWindow();
  function fmtBRL(v){ if(v==null) return '—'; return new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0}).format(v); }
  function escHtml(s){ if(s==null) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  targetMarker.addListener('click', function(){
    info.setContent(
      '<div style="font:13px system-ui;padding:2px"><div style="font-weight:600">'+escHtml(data.target.title||'Imóvel do leilão')+'</div>'+
      '<div style="font-size:11px;color:#64748b">'+escHtml(data.target.address||'')+'</div>'+
      '<div style="font-size:12px;margin-top:4px">Avaliação: <strong>'+fmtBRL(data.target.appraisal)+'</strong></div>'+
      (data.target.area? '<div style="font-size:12px">Área: <strong>'+escHtml(data.target.area)+' m²</strong></div>':'')+
      (data.target.sourceUrl? '<div style="margin-top:6px"><a href="'+escHtml(data.target.sourceUrl)+'" target="_blank" rel="noreferrer" style="color:#2563eb">Abrir anúncio ↗</a></div>':'')+
      '</div>'
    );
    info.open(map, targetMarker);
  });

  // Agrupa comparables por (lat,lng) com 5 casas decimais (~1m).
  var groups = {};
  (data.comparables || []).forEach(function(c){
    var key = c.lat.toFixed(5)+','+c.lng.toFixed(5);
    (groups[key] = groups[key] || []).push(c);
    bounds.extend({ lat: c.lat, lng: c.lng });
  });

  function compIcon(used){
    return {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 11, fillColor: used? '#16a34a':'#9ca3af', fillOpacity:1,
      strokeColor:'#ffffff', strokeWeight:2.5,
    };
  }
  function clusterIcon(n){
    var s = '<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44">'+
      '<circle cx="22" cy="22" r="18" fill="#2563eb" stroke="#fff" stroke-width="3"/>'+
      '<text x="22" y="22" text-anchor="middle" dominant-baseline="central" font-family="system-ui" font-size="'+(n>99?13:15)+'" font-weight="700" fill="#fff">'+n+'</text>'+
      '</svg>';
    return { url: 'data:image/svg+xml;utf8,'+encodeURIComponent(s), scaledSize:new google.maps.Size(44,44), anchor:new google.maps.Point(22,22) };
  }
  function offsetLatLng(center, meters, angle){
    var R = 6378137;
    var dLat = meters * Math.cos(angle) / R * (180/Math.PI);
    var dLng = meters * Math.sin(angle) / (R * Math.cos(center.lat*Math.PI/180)) * (180/Math.PI);
    return { lat: center.lat + dLat, lng: center.lng + dLng };
  }
  function spiderPositions(center, count){
    if (count <= 1) return [center];
    var zoom = map.getZoom() || 14;
    var mPerPx = (156543.03392 * Math.cos(center.lat*Math.PI/180)) / Math.pow(2, zoom);
    var R = 56;
    var out = [];
    if (count <= 10){
      for (var i=0;i<count;i++){
        out.push(offsetLatLng(center, R*mPerPx, (2*Math.PI*i)/count - Math.PI/2));
      }
    } else {
      var inner = Math.ceil(count*0.4), outer = count - inner;
      for (var i=0;i<inner;i++){
        out.push(offsetLatLng(center, R*mPerPx, (2*Math.PI*i)/inner - Math.PI/2));
      }
      for (var j=0;j<outer;j++){
        out.push(offsetLatLng(center, R*1.85*mPerPx, (2*Math.PI*j)/outer - Math.PI/2 + Math.PI/outer));
      }
    }
    return out;
  }
  function compInfoHtml(c){
    var ppm2 = (c.price && c.area) ? (c.price/c.area) : null;
    // URLs sintéticas (formato ".../#item=hash") apontam para a página
    // de busca, não para o imóvel — não devem ser clicáveis.
    var isSynth = c.sourceUrl && String(c.sourceUrl).indexOf("#item=") !== -1;
    return '<div style="font:12px system-ui;padding:2px">'+
      '<div style="font-weight:600">Comparável #'+c.idx+(c.used?'':' <span style="color:#dc2626;font-weight:400">(rejeitado)</span>')+'</div>'+
      '<div style="font-size:11px;color:#64748b">'+escHtml(c.neighborhood||'—')+' · '+escHtml(c.city||'—')+'/'+escHtml(c.state||'—')+'</div>'+
      '<table style="margin-top:4px;font-size:11px;border-collapse:collapse">'+
        '<tr><td style="color:#64748b;padding-right:6px">Preço</td><td style="text-align:right;font-weight:500">'+fmtBRL(c.price)+'</td></tr>'+
        '<tr><td style="color:#64748b">R$/m²</td><td style="text-align:right">'+fmtBRL(ppm2)+'</td></tr>'+
        '<tr><td style="color:#64748b">Área</td><td style="text-align:right">'+(c.area!=null?escHtml(c.area)+' m²':'—')+'</td></tr>'+
        '<tr><td style="color:#64748b">Quartos / Vagas</td><td style="text-align:right">'+(c.bedrooms??'—')+' / '+(c.parking??'—')+'</td></tr>'+
        '<tr><td style="color:#64748b">Distância</td><td style="text-align:right">'+(c.distanceM!=null?Math.round(c.distanceM)+' m':'—')+'</td></tr>'+
      '</table>'+
      (c.sourceUrl && !isSynth
        ? '<div style="margin-top:6px"><a href="'+escHtml(c.sourceUrl)+'" target="_blank" rel="noreferrer" style="color:#2563eb;font-weight:500">Abrir anúncio ↗</a></div>'
        : (isSynth
            ? '<div style="margin-top:6px;font-size:10px;color:#92400e" title="Link específico do imóvel não disponível: o anúncio foi extraído de uma página de busca, mas a URL canônica não pôde ser identificada.">⚠ Link específico indisponível</div>'
            : ''))+
      '</div>';
  }
  function makeCompMarker(c, pos){
    var m = new google.maps.Marker({
      position: pos, map: map, icon: compIcon(c.used),
      opacity: c.used? 1 : 0.65, zIndex: c.used? 600 : 550,
      label: { text: String(c.idx), color:'#fff', fontSize:'11px', fontWeight:'700' },
      title: '#'+c.idx+' · '+fmtBRL(c.price),
    });
    m.addListener('click', function(){
      info.setContent(compInfoHtml(c));
      info.open(map, m);
    });
    return m;
  }

  var expandedKey = null;
  var groupRenders = {};   // key -> { collapse, expand, current: 'collapsed'|'expanded' }

  Object.keys(groups).forEach(function(key){
    var items = groups[key];
    var center = { lat: items[0].lat, lng: items[0].lng };
    var renderer = { current: null, markers: [], lines: [] };

    function clearMarkers(){
      renderer.markers.forEach(function(m){ m.setMap(null); });
      renderer.lines.forEach(function(l){ l.setMap(null); });
      renderer.markers = []; renderer.lines = [];
    }
    function collapse(){
      clearMarkers();
      if (items.length === 1){
        renderer.markers.push(makeCompMarker(items[0], center));
      } else {
        var m = new google.maps.Marker({
          position: center, map: map, icon: clusterIcon(items.length), zIndex: 500,
          title: items.length + ' anúncios neste ponto — clique para expandir',
        });
        m.addListener('click', function(){
          if (expandedKey && expandedKey !== key) groupRenders[expandedKey].collapse();
          expand(); expandedKey = key;
        });
        renderer.markers.push(m);
      }
      renderer.current = 'collapsed';
    }
    function expand(){
      clearMarkers();
      var positions = spiderPositions(center, items.length);
      positions.forEach(function(p){
        renderer.lines.push(new google.maps.Polyline({
          path: [center, p], map: map,
          strokeColor: '#2563eb', strokeOpacity: 0.5, strokeWeight: 1.5, clickable: false, zIndex: 400,
        }));
      });
      // pininho central indicando "ponto original".
      var hub = new google.maps.Marker({
        position: center, map: map,
        icon: { path: google.maps.SymbolPath.CIRCLE, scale: 5, fillColor:'#2563eb', fillOpacity:1, strokeColor:'#fff', strokeWeight:2 },
        zIndex: 401, title:'Posição original (clique fora para colapsar)'
      });
      hub.addListener('click', function(){ collapse(); expandedKey = null; });
      renderer.markers.push(hub);
      items.forEach(function(c,i){
        renderer.markers.push(makeCompMarker(c, positions[i]));
      });
      renderer.current = 'expanded';
    }
    groupRenders[key] = { collapse: collapse, expand: expand };
    collapse();
  });

  // Clique no fundo do mapa colapsa qualquer grupo expandido.
  map.addListener('click', function(){
    if (expandedKey && groupRenders[expandedKey]){
      groupRenders[expandedKey].collapse();
      expandedKey = null;
    }
    info.close();
  });

  // Estratégia: fitBounds escolhe um zoom apropriado dado o espalhamento
  // dos comparáveis; clamp do zoom mantém [15..17] (~1 quarteirão);
  // depois RE-CENTRAMOS no imóvel-alvo (não no centroide dos pontos),
  // que é o que o relatório quer destacar.
  if (data.comparables && data.comparables.length > 0){
    map.fitBounds(bounds, 32);
    google.maps.event.addListenerOnce(map, 'idle', function(){
      var z = map.getZoom() || 14;
      if (z < 15) map.setZoom(15);
      if (z > 17) map.setZoom(17);
      map.setCenter({ lat: data.target.lat, lng: data.target.lng });
    });
  } else {
    // Sem comparáveis, fica num zoom de bairro confortável.
    map.setZoom(16);
  }
}
window.__initReportMap__ = __initReportMap__;
`;

// =============================================================================
// Função pública
// =============================================================================
export function generateReportHtml(args: {
  property: Property;
  opportunity: OpportunityResult;
  valuation: ValuationDetail | null;
  deepAnalysis: DeepAnalysisRow | null;
  apiKey: string;
}): string {
  const { property, opportunity, valuation, deepAnalysis, apiKey } = args;
  const comparables = valuation?.comparables ?? [];
  const title = `Relatório · ${property.title ?? property.property_type ?? "imóvel"}`;
  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${esc(title)}</title>
  <style>${STYLES}</style>
</head>
<body>
<div class="wrap">
  ${renderProperty(property)}
  ${renderOpportunity(opportunity, property)}
  ${renderMap(property, comparables, apiKey)}
  ${deepAnalysis && deepAnalysis.status === "completed" ? renderDeep(deepAnalysis, property) : ""}
  <p class="muted" style="text-align:center;margin-top:18px">
    Relatório gerado automaticamente · ${esc(new Date().toLocaleString("pt-BR"))}
  </p>
</div>
</body>
</html>`;
}
