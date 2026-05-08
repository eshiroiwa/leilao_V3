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
  --border:#e2e8f0; --primary:#2563eb; --success:#16a34a;
  --warning:#d97706; --danger:#dc2626; --accent:#1e40af;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--fg);
  font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:24px}
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
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
@media(max-width:720px){.grid-3{grid-template-columns:1fr}}
.field{padding:6px 0}
.field-label{font-size:11px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--muted)}
.field-value{font-size:14px;font-weight:500;margin-top:2px}
.thumb{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:8px;
  border:1px solid var(--border);background:#f1f5f9}
.scenario{border:1px solid var(--border);border-radius:10px;padding:14px;
  background:#fafafa}
.scenario h4{font-size:12px;margin:0 0 10px;text-transform:uppercase;
  letter-spacing:.04em;color:var(--muted)}
.scenario.realista{border-color:var(--accent);background:#eff6ff}
.scenario .row{display:flex;justify-content:space-between;padding:3px 0;
  font-size:13px;border-bottom:1px dashed #e2e8f0}
.scenario .row:last-child{border-bottom:none}
.scenario .row strong{font-weight:600}
.scenario .row.profit strong{color:var(--success)}
.scenario .row.loss strong{color:var(--danger)}
.scenario .roi{font-size:22px;font-weight:700;margin:8px 0 4px}
.scenario .roi.pos{color:var(--success)} .scenario .roi.neg{color:var(--danger)}
.warnings{margin-top:10px;display:flex;flex-direction:column;gap:6px}
.warnings li{list-style:none;padding:6px 10px;border-radius:6px;font-size:12px;
  border:1px solid rgba(217,119,6,.4);background:rgba(217,119,6,.08);
  color:#92400e}
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
  const fields: Array<[string, string]> = [
    ["Tipo", esc(property.property_type ?? "—")],
    [
      "Área total",
      property.area_total_m2 != null
        ? `${property.area_total_m2} m²`
        : "—",
    ],
    [
      "Quartos",
      property.bedrooms != null ? String(property.bedrooms) : "—",
    ],
    [
      "Banheiros",
      property.bathrooms != null ? String(property.bathrooms) : "—",
    ],
    ["Vagas", property.parking_spaces != null ? String(property.parking_spaces) : "—"],
    ["Avaliação (edital)", fmtBRL(property.appraisal_value)],
    ["1ª praça", fmtBRL(property.minimum_bid_first)],
    ["2ª praça", fmtBRL(property.minimum_bid_second)],
    [
      "Ocupação",
      esc(property.occupancy_status ?? "—"),
    ],
    [
      "Riscos / ônus",
      "—",
    ],
  ];

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

function renderScenario(
  s: OpportunityScenario,
  label: string,
  highlight = false,
): string {
  const profitClass = s.net_profit >= 0 ? "profit" : "loss";
  const roiClass = s.net_roi_pct >= 0 ? "pos" : "neg";
  const cls = `scenario${highlight ? " realista" : ""}`;
  return `
<div class="${cls}">
  <h4>${esc(label)}</h4>
  <div class="row"><span>Preço de venda</span><strong>${fmtBRL(
    s.sale_price,
  )}</strong></div>
  <div class="row"><span>Lance</span><strong>${fmtBRL(s.bid)}</strong></div>
  <div class="row"><span>Comissão leiloeiro</span><strong>${fmtBRL(
    s.auctioneer_fee,
  )}</strong></div>
  <div class="row"><span>ITBI</span><strong>${fmtBRL(s.itbi)}</strong></div>
  <div class="row"><span>Reforma</span><strong>${fmtBRL(
    s.renovation_cost,
  )}</strong></div>
  <div class="row"><span>Outros + atrasados</span><strong>${fmtBRL(
    s.other_costs + s.iptu_arrears + s.condo_arrears,
  )}</strong></div>
  <div class="row"><span>Custo total</span><strong>${fmtBRL(
    s.total_acquisition_cost,
  )}</strong></div>
  <div class="row"><span>Imposto de renda</span><strong>${fmtBRL(
    s.income_tax,
  )}</strong></div>
  <div class="row ${profitClass}"><span>Lucro líquido</span><strong>${fmtBRL(
    s.net_profit,
  )}</strong></div>
  <div class="roi ${roiClass}">ROI ${fmtPct(s.net_roi_pct)}</div>
  <div class="muted">ROI bruto ${fmtPct(s.gross_roi_pct)}</div>
</div>`;
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
  return `
<section class="section">
  <h2>Análise de oportunidade
    <span class="tag ${v.cls}" style="margin-left:8px">${esc(v.label)}</span>
  </h2>
  <div class="muted">
    Comprador ${esc(result.input.buyer_type)} · ROI alvo
    ${fmtPct(result.input.target_net_roi_pct, 0)} · Reforma
    ${esc(result.input.renovation_level)} · Imóvel em ${esc(
      property.city ?? "",
    )}/${esc(property.state ?? "")}
  </div>
  <div class="grid-3" style="margin-top:14px">
    ${renderScenario(result.pessimista, "Pessimista")}
    ${renderScenario(result.realista, "Realista", true)}
    ${renderScenario(result.otimista, "Otimista")}
  </div>
  <div style="margin-top:14px">
    <h3>Lance máximo para ROI alvo</h3>
    <div class="field-value">${
      result.max_bid_for_target != null
        ? fmtBRL(result.max_bid_for_target)
        : "Inalcançável (reduza custos ou eleve preço de venda)"
    }</div>
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

function renderDeep(deep: DeepAnalysisRow): string {
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
      deep.city_population != null
        ? `${deep.city_population.toLocaleString("pt-BR")} hab.`
        : undefined,
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

  ${flagsBlock("Pontos a favor", deep.green_flags, "green")}
  ${flagsBlock("Pontos de atenção", deep.red_flags, "red")}
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
      (c.sourceUrl? '<div style="margin-top:6px"><a href="'+escHtml(c.sourceUrl)+'" target="_blank" rel="noreferrer" style="color:#2563eb;font-weight:500">Abrir anúncio ↗</a></div>':'')+
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
  ${deepAnalysis && deepAnalysis.status === "completed" ? renderDeep(deepAnalysis) : ""}
  <p class="muted" style="text-align:center;margin-top:18px">
    Relatório gerado automaticamente · ${esc(new Date().toLocaleString("pt-BR"))}
  </p>
</div>
</body>
</html>`;
}
