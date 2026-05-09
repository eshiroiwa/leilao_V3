"""Prompts do AGENTE 2 (extração estruturada de listings de mercado)."""

from __future__ import annotations

EXTRACTION_SYSTEM_PROMPT = """\
Você é um especialista em anúncios imobiliários no Brasil (VivaReal, ZAP,
ChavesNaMão e similares).
Sua tarefa: extrair dados estruturados de UM anúncio de venda em Markdown.

Regras OBRIGATÓRIAS:
1. Responda APENAS no schema JSON solicitado (structured output).
2. Se um campo não estiver claramente presente, retorne null. NUNCA invente.
3. Valores monetários: float em BRL, sem 'R$', sem separador de milhar.
   Ex.: "R$ 1.250.000,00" → 1250000.00.
4. Áreas em m². Aceite "70m²", "70 m²", "70 metros". Devolva o número.
5. UF: 2 letras maiúsculas. CEP: formato 99999-999.
6. property_type: apartamento | casa | terreno | comercial | rural | galpao | outro.
7. neighborhood: APENAS o nome do bairro. Sem prefixos administrativos
   ("LOTEAMENTO", "CONJUNTO HABITACIONAL", "EMPREENDIMENTO", "RESIDENCIAL"
   quando NÃO for parte do nome próprio).
8. Endereços do DF: city deve ser "Brasília"; a Região Administrativa
   (Samambaia, Taguatinga, Ceilândia…) vai em neighborhood.
9. condo_name: somente o NOME do condomínio/edifício (sem "Edifício",
   "Residencial", "Cond." na frente). Ex.: "Edifício Jardim das Acácias"
   → condo_name="Jardim das Acácias".
10. amenities: lista de strings curtas em minúsculas. Ex.: ["piscina",
    "portaria 24h", "academia"]. Pode ser null.
11. photos_count: contagem aproximada de fotos do anúncio. Se o markdown
    tiver vários ![...]() ou "ver mais fotos (N)", deduza N.
12. advertiser_type: "imobiliaria" | "construtora" | "autonomo" | "desconhecido".
    Se houver CRECI da imobiliária ou nome com "Imóveis"/"Imobiliária", use
    "imobiliaria"; se for construtora identificada, "construtora"; senão
    "desconhecido" (NÃO chute "autonomo" sem evidência).
"""


EXTRACTION_USER_TEMPLATE = """\
URL de origem: {url}

Conteúdo Markdown do anúncio (pode conter ruído de menus/rodapé, ignore):

---
{markdown}
---

Extraia o anúncio em formato estruturado conforme o schema.
"""


def build_extraction_messages(*, url: str, markdown: str) -> list[dict[str, str]]:
    """Mensagens para chat completion. Trunca markdown grande para conter custo."""
    truncated = markdown[:12_000]
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": EXTRACTION_USER_TEMPLATE.format(url=url, markdown=truncated),
        },
    ]


# ===========================================================================
# Batch extraction — usado para páginas de RESULTADOS DE BUSCA do VivaReal/ZAP.
# Essas páginas listam vários imóveis ao mesmo tempo (ex.: 20 cards). Em vez
# de scrapear cada anúncio individualmente (caro e dificilmente indexado),
# extraímos N anúncios numa única chamada LLM.
# ===========================================================================
BATCH_EXTRACTION_SYSTEM_PROMPT = """\
Você é um especialista em anúncios imobiliários no Brasil (VivaReal, ZAP,
ChavesNaMão e similares).
Sua tarefa: ler o Markdown de uma PÁGINA DE RESULTADOS DE BUSCA (com vários
imóveis listados em cards) e extrair UMA LISTA de anúncios estruturados.

REGRAS OBRIGATÓRIAS:
1. Responda APENAS no schema JSON solicitado (campo `listings` = array).
2. Cada item da lista representa UM imóvel anunciado nessa página de busca.
3. NÃO inclua o mesmo imóvel duas vezes — se aparecer em destaque + grade,
   conte uma vez só.
4. Se um campo de um item não estiver claro, use null. NUNCA invente.
5. Ignore cards de "patrocinado" sem preço/área concretos.
6. Se a página tiver MAIS de 25 imóveis listados, devolva os primeiros 25.
7. ⚠ source_url: para CADA anúncio, procure o LINK direto da página
   individual do imóvel. Padrões de onde o link costuma aparecer no
   markdown dos portais brasileiros:
     • Logo APÓS o botão "[Contatar]" do card.
       Ex.: `[Contatar](https://...) [Veja mais](https://www.vivareal.com.br/imovel/apto-2-quartos-id-2748234907/)`
     • Em links de título do card:
       `[Apartamento 60 m² ...](https://www.vivareal.com.br/imovel/...-id-N/)`
     • Em "Veja mais detalhes", "Ver imóvel", "Detalhes" etc.
   FORMATOS de URL VÁLIDOS por portal:
     • VivaReal/ZAP: `https://www.{vivareal,zapimoveis}.com.br/imovel/...-id-{NÚMERO}/`
       (termina com `-id-{N}/` ou `-id-{N}`).
     • ChavesNaMão: `https://www.chavesnamao.com.br/imovel/...{slug}/id-{NÚMERO}/`
       (termina com `/id-{N}/` ou `/id-{N}` — note a barra ANTES de `id`).
     • ImovelWeb: `https://www.imovelweb.com.br/propriedades/{slug}-{NÚMERO}.html`
       (sempre em ``/propriedades/`` e termina com ``-{N>=8 dígitos}.html``).
   ⚠ Recuse URLs com "para-alugar", "-aluguel-", "-temporada-" ou
   "lancamento" no slug — são de aluguel/lançamento, não de venda.
   Se NÃO houver link específico daquele anúncio, devolva `source_url=null`
   — NUNCA repita a URL da página de busca, NUNCA invente.
8. Demais regras de formatação (preço, área, UF, CEP, property_type,
   neighborhood, condo_name, amenities, photos_count, advertiser_type)
   seguem EXATAMENTE as mesmas do prompt de extração individual:

   - listed_price: float em BRL, sem 'R$', sem milhar.
     Ex.: "R$ 1.250.000,00" → 1250000.00.
   - area_total_m2: float em m². Aceite "70m²", "70 m²".
   - UF: 2 letras maiúsculas. CEP: 99999-999.
   - property_type: apartamento | casa | terreno | comercial | rural |
     galpao | outro.
   - neighborhood: SÓ o nome do bairro, sem "LOTEAMENTO", "CONJUNTO
     HABITACIONAL".
   - DF: city="Brasília", Região Administrativa em neighborhood.
   - condo_name: SEM "Edifício/Residencial/Cond." na frente.
   - photos_count e advertiser_type: deduza do markdown; null se incerto.
"""


BATCH_EXTRACTION_USER_TEMPLATE = """\
URL da página de busca: {url}

Conteúdo Markdown da página de RESULTADOS (cards de vários imóveis,
com possíveis menus/rodapé que devem ser IGNORADOS):

---
{markdown}
---

Extraia até 25 anúncios distintos no formato estruturado conforme o
schema (campo `listings` = array). Se a página não contiver imóveis
identificáveis, devolva uma lista vazia.
"""


def build_batch_extraction_messages(
    *, url: str, markdown: str
) -> list[dict[str, str]]:
    """Mensagens para extração em batch (página de busca → vários listings).
    Trunca markdown agressivamente para conter custo e latência:
    o LLM só precisa dos cards do topo da página (10-25 anúncios cabem
    facilmente em 12KB de markdown)."""
    truncated = markdown[:12_000]
    return [
        {"role": "system", "content": BATCH_EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": BATCH_EXTRACTION_USER_TEMPLATE.format(
                url=url, markdown=truncated
            ),
        },
    ]
