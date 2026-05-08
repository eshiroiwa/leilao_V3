/**
 * Geração do nome de arquivo do relatório.
 *
 * Formato pedido pelo usuário: `tipo_estado_cidade_bairro_rua-...html`
 *
 * Regras:
 * - Remove acentos / caracteres não-ASCII.
 * - Mantém somente ``[a-z0-9-]``.
 * - Junta os campos por ``_`` e PULA campos vazios — não emitimos
 *   ``__`` ou ``_-`` desnecessários.
 */
function slug(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // remove acentos
    .toLowerCase()
    .replace(/&/g, "e")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function reportFilename(args: {
  property_type: string | null | undefined;
  state: string | null | undefined;
  city: string | null | undefined;
  neighborhood: string | null | undefined;
  street: string | null | undefined;
}): string {
  const parts = [
    slug(args.property_type),
    slug(args.state),
    slug(args.city),
    slug(args.neighborhood),
    slug(args.street),
  ].filter(Boolean);
  const stem = parts.length ? parts.join("_") : "relatorio-imovel";
  return `${stem}.html`;
}
