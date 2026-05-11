/**
 * Validação e formatação de CPF / CNPJ.
 *
 * O algoritmo dos dígitos verificadores é fixo na legislação brasileira
 * desde 1970 (CPF) e 1991 (CNPJ); usamos a validação para alertar quando
 * o usuário digitou um número que claramente não existe — antes de
 * gastarmos uma chamada ao DataJud que vai retornar zero hits e dar uma
 * falsa sensação de "imóvel limpo".
 */

/** Mantém apenas dígitos. */
export function digitsOnly(s: string): string {
  return (s || "").replace(/\D/g, "");
}

/** Aplica a máscara de CPF (000.000.000-00) ou CNPJ (00.000.000/0000-00)
 *  conforme o comprimento dos dígitos. */
export function maskCpfCnpj(raw: string): string {
  const d = digitsOnly(raw).slice(0, 14);
  if (d.length <= 11) {
    return d
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1-$2");
  }
  return d
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d)/, "$1-$2");
}

/** Valida dígito verificador de CPF (11 dígitos). */
export function isValidCpf(digits: string): boolean {
  const d = digitsOnly(digits);
  if (d.length !== 11) return false;
  // Sequências repetidas (00000000000, 11111111111…) passam matematicamente
  // mas são CPFs reservados/inválidos.
  if (/^(\d)\1{10}$/.test(d)) return false;

  // Calcula o 1º DV.
  let sum = 0;
  for (let i = 0; i < 9; i++) sum += Number(d[i]) * (10 - i);
  let dv1 = (sum * 10) % 11;
  if (dv1 === 10) dv1 = 0;
  if (dv1 !== Number(d[9])) return false;

  // Calcula o 2º DV.
  sum = 0;
  for (let i = 0; i < 10; i++) sum += Number(d[i]) * (11 - i);
  let dv2 = (sum * 10) % 11;
  if (dv2 === 10) dv2 = 0;
  return dv2 === Number(d[10]);
}

/** Valida dígito verificador de CNPJ (14 dígitos). */
export function isValidCnpj(digits: string): boolean {
  const d = digitsOnly(digits);
  if (d.length !== 14) return false;
  if (/^(\d)\1{13}$/.test(d)) return false;

  // Pesos do 1º DV: 5 4 3 2 9 8 7 6 5 4 3 2
  const w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  let sum1 = 0;
  for (let i = 0; i < 12; i++) sum1 += Number(d[i]) * w1[i];
  let dv1 = sum1 % 11;
  dv1 = dv1 < 2 ? 0 : 11 - dv1;
  if (dv1 !== Number(d[12])) return false;

  // Pesos do 2º DV: 6 5 4 3 2 9 8 7 6 5 4 3 2
  const w2 = [6, ...w1];
  let sum2 = 0;
  for (let i = 0; i < 13; i++) sum2 += Number(d[i]) * w2[i];
  let dv2 = sum2 % 11;
  dv2 = dv2 < 2 ? 0 : 11 - dv2;
  return dv2 === Number(d[13]);
}

/** Resultado consolidado: aceita CPF (11) ou CNPJ (14) — devolve qual é
 *  + se o dígito verificador bate. */
export type CpfCnpjValidation =
  | { kind: "empty" }
  | { kind: "incomplete"; digits: string }
  | { kind: "cpf"; digits: string; dvValid: boolean }
  | { kind: "cnpj"; digits: string; dvValid: boolean };

export function validateCpfCnpj(raw: string): CpfCnpjValidation {
  const d = digitsOnly(raw);
  if (d.length === 0) return { kind: "empty" };
  if (d.length === 11) return { kind: "cpf", digits: d, dvValid: isValidCpf(d) };
  if (d.length === 14)
    return { kind: "cnpj", digits: d, dvValid: isValidCnpj(d) };
  return { kind: "incomplete", digits: d };
}
