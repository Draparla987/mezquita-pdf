/**
 * Utilidades de bajo nivel para trabajar con bytes de PDF.
 * No dependen del DOM: se usan tanto en el navegador como en las pruebas de Node.
 */
const codificador = new TextEncoder();

/** Convierte texto ASCII/latin1 (sintaxis PDF) en bytes. */
export function latin1(texto: string): Uint8Array {
  const salida = new Uint8Array(texto.length);
  for (let i = 0; i < texto.length; i++) salida[i] = texto.charCodeAt(i) & 0xff;
  return salida;
}

export function utf8(texto: string): Uint8Array {
  return codificador.encode(texto);
}

export function concatenar(partes: Uint8Array[]): Uint8Array {
  let total = 0;
  for (const p of partes) total += p.length;
  const salida = new Uint8Array(total);
  let pos = 0;
  for (const p of partes) {
    salida.set(p, pos);
    pos += p.length;
  }
  return salida;
}

/** Busca `patron` en `datos` desde `desde` hacia delante. Devuelve -1 si no aparece. */
export function buscar(datos: Uint8Array, patron: Uint8Array | string, desde = 0, hasta = datos.length): number {
  const p = typeof patron === 'string' ? latin1(patron) : patron;
  const limite = Math.min(hasta, datos.length) - p.length;
  externo: for (let i = Math.max(0, desde); i <= limite; i++) {
    for (let j = 0; j < p.length; j++) if (datos[i + j] !== p[j]) continue externo;
    return i;
  }
  return -1;
}

/** Busca la última aparición de `patron` antes de `hasta`. */
export function buscarUltimo(datos: Uint8Array, patron: Uint8Array | string, hasta = datos.length): number {
  const p = typeof patron === 'string' ? latin1(patron) : patron;
  externo: for (let i = Math.min(hasta, datos.length) - p.length; i >= 0; i--) {
    for (let j = 0; j < p.length; j++) if (datos[i + j] !== p[j]) continue externo;
    return i;
  }
  return -1;
}

export function aHex(bytes: Uint8Array): string {
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += bytes[i].toString(16).padStart(2, '0');
  return s.toUpperCase();
}

export function deHex(hex: string): Uint8Array {
  const limpio = hex.replace(/[^0-9a-fA-F]/g, '');
  const salida = new Uint8Array(limpio.length >> 1);
  for (let i = 0; i < salida.length; i++) salida[i] = parseInt(limpio.substr(i * 2, 2), 16);
  return salida;
}

/** Bytes → «cadena binaria» de node-forge (un carácter por byte). */
export function aBinario(bytes: Uint8Array): string {
  let s = '';
  const bloque = 0x8000;
  for (let i = 0; i < bytes.length; i += bloque) {
    s += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + bloque)));
  }
  return s;
}

/** «Cadena binaria» de node-forge → bytes. */
export function deBinario(s: string): Uint8Array {
  const salida = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) salida[i] = s.charCodeAt(i) & 0xff;
  return salida;
}

function subtle(): SubtleCrypto | undefined {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  return c && c.subtle ? c.subtle : undefined;
}

/**
 * SHA-256. Usa WebCrypto (rápido, nativo) cuando está disponible; si la página no
 * se sirve en un contexto seguro (http en la red local), recurre a node-forge.
 */
export async function sha256(datos: Uint8Array): Promise<Uint8Array> {
  const s = subtle();
  if (s) {
    const copia = datos.byteOffset === 0 && datos.byteLength === datos.buffer.byteLength
      ? datos : datos.slice();
    return new Uint8Array(await s.digest('SHA-256', copia as BufferSource));
  }
  const { default: forge } = await import('node-forge');
  const md = forge.md.sha256.create();
  const bloque = 1 << 20;
  for (let i = 0; i < datos.length; i += bloque) md.update(aBinario(datos.subarray(i, i + bloque)));
  return deBinario(md.digest().getBytes());
}

export function bytesAleatorios(n: number): Uint8Array {
  const salida = new Uint8Array(n);
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c && c.getRandomValues) c.getRandomValues(salida);
  else for (let i = 0; i < n; i++) salida[i] = Math.floor(Math.random() * 256);
  return salida;
}

/** Cadena de texto PDF: literal si es ASCII imprimible, UTF-16BE con BOM si no. */
export function textoPdf(texto: string): string {
  if (/^[\x20-\x7E]*$/.test(texto)) {
    return '(' + texto.replace(/([\\()])/g, '\\$1') + ')';
  }
  let hex = 'FEFF';
  for (let i = 0; i < texto.length; i++) hex += texto.charCodeAt(i).toString(16).padStart(4, '0');
  return '<' + hex.toUpperCase() + '>';
}

/** Fecha en formato PDF: D:AAAAMMDDHHmmSS+hh'mm' (hora local). */
export function fechaPdf(fecha: Date): string {
  const dos = (n: number) => String(n).padStart(2, '0');
  const desfase = -fecha.getTimezoneOffset();
  const signo = desfase >= 0 ? '+' : '-';
  const abs = Math.abs(desfase);
  return `D:${fecha.getFullYear()}${dos(fecha.getMonth() + 1)}${dos(fecha.getDate())}` +
    `${dos(fecha.getHours())}${dos(fecha.getMinutes())}${dos(fecha.getSeconds())}` +
    `${signo}${dos(Math.floor(abs / 60))}'${dos(abs % 60)}'`;
}

/** Fecha legible para el sello: 04/10/2026 18:30:00 +0200 (como en la app de escritorio). */
export function fechaLegible(fecha: Date): string {
  const dos = (n: number) => String(n).padStart(2, '0');
  const desfase = -fecha.getTimezoneOffset();
  const signo = desfase >= 0 ? '+' : '-';
  const abs = Math.abs(desfase);
  return `${dos(fecha.getDate())}/${dos(fecha.getMonth() + 1)}/${fecha.getFullYear()} ` +
    `${dos(fecha.getHours())}:${dos(fecha.getMinutes())}:${dos(fecha.getSeconds())} ` +
    `${signo}${dos(Math.floor(abs / 60))}${dos(abs % 60)}`;
}

/** Color «#RRGGBB» → componentes 0..1. */
export function colorRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

/** Número compacto para operadores PDF. */
export function num(n: number): string {
  if (!Number.isFinite(n)) return '0';
  const r = Math.round(n * 1000) / 1000;
  return Object.is(r, -0) ? '0' : String(r);
}

export class ErrorPdf extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = 'ErrorPdf';
  }
}

/** Convierte un data URL (data:image/png;base64,…) en bytes. */
export function bytesDeDataUrl(url: string): Uint8Array {
  const coma = url.indexOf(',');
  return deBinario(atob(url.slice(coma + 1)));
}
