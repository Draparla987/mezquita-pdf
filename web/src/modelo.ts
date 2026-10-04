/**
 * Modelo de anotaciones. Todas las coordenadas van en «unidades de página»: las de
 * la vista de pdf.js a escala 1, con la rotación de la página aplicada y el eje Y
 * hacia abajo (ver src/pdf/geometria.ts).
 */

interface Base {
  id: string;
  /** Índice de página (0 = primera). */
  pagina: number;
}

export interface AnotResaltado extends Base {
  tipo: 'resaltado';
  x: number; y: number; w: number; h: number;
  color: string;
}

export interface AnotRectangulo extends Base {
  tipo: 'rectangulo';
  x: number; y: number; w: number; h: number;
  color: string;
  grosor: number;
}

export interface AnotTrazo extends Base {
  tipo: 'trazo';
  /** Lista plana x0, y0, x1, y1… */
  puntos: number[];
  color: string;
  grosor: number;
}

export interface AnotTexto extends Base {
  tipo: 'texto';
  /** Esquina superior izquierda del bloque de texto. */
  x: number; y: number;
  texto: string;
  tam: number;
  color: string;
}

export interface AnotImagen extends Base {
  tipo: 'imagen';
  x: number; y: number; w: number; h: number;
  /** Imagen PNG como data URL (normalmente, una firma manuscrita). */
  png: string;
}

export type Anotacion = AnotResaltado | AnotRectangulo | AnotTrazo | AnotTexto | AnotImagen;

/** Métricas de texto compartidas por la vista (SVG) y el PDF para que coincidan. */
export const TEXTO_INTERLINEA = 1.25;
export const TEXTO_ASCENSO = 0.9;
export const OPACIDAD_RESALTADO = 0.45;

export function nuevoId(): string {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c && 'randomUUID' in c) return (c as Crypto).randomUUID();
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

/** Caja envolvente de una anotación en unidades de página (sin contar el grosor). */
export function cajaAnotacion(a: Anotacion, anchoTexto?: (a: AnotTexto) => number): { x: number; y: number; w: number; h: number } {
  switch (a.tipo) {
    case 'resaltado':
    case 'rectangulo':
    case 'imagen':
      return { x: a.x, y: a.y, w: a.w, h: a.h };
    case 'trazo': {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let i = 0; i < a.puntos.length; i += 2) {
        x0 = Math.min(x0, a.puntos[i]); x1 = Math.max(x1, a.puntos[i]);
        y0 = Math.min(y0, a.puntos[i + 1]); y1 = Math.max(y1, a.puntos[i + 1]);
      }
      return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
    }
    case 'texto': {
      const lineas = a.texto.split('\n');
      const w = anchoTexto ? anchoTexto(a) : Math.max(...lineas.map((l) => l.length)) * a.tam * 0.55;
      return { x: a.x, y: a.y, w, h: a.tam * (TEXTO_INTERLINEA * (lineas.length - 1) + 1.15) };
    }
  }
}

/**
 * Suaviza un trazo con curvas cuadráticas por los puntos medios. Devuelve una lista de
 * segmentos [x0,y0, cx,cy, x1,y1] que comparten el SVG de la vista y el PDF.
 */
export function segmentosSuaves(p: number[]): number[][] {
  const n = p.length / 2;
  if (n < 2) return [];
  if (n === 2) return [[p[0], p[1], (p[0] + p[2]) / 2, (p[1] + p[3]) / 2, p[2], p[3]]];
  const seg: number[][] = [];
  let x0 = p[0], y0 = p[1];
  for (let i = 1; i < n - 1; i++) {
    const cx = p[i * 2], cy = p[i * 2 + 1];
    const mx = (cx + p[i * 2 + 2]) / 2, my = (cy + p[i * 2 + 3]) / 2;
    const fx = i === n - 2 ? p[i * 2 + 2] : mx;
    const fy = i === n - 2 ? p[i * 2 + 3] : my;
    seg.push([x0, y0, cx, cy, fx, fy]);
    x0 = fx; y0 = fy;
  }
  return seg;
}

/** Simplificación de Ramer-Douglas-Peucker para no guardar miles de puntos. */
export function simplificar(p: number[], tolerancia: number): number[] {
  const n = p.length / 2;
  if (n <= 2) return p.slice();
  const conservar = new Uint8Array(n);
  conservar[0] = conservar[n - 1] = 1;
  const pila: Array<[number, number]> = [[0, n - 1]];
  const t2 = tolerancia * tolerancia;
  while (pila.length) {
    const [a, b] = pila.pop()!;
    const ax = p[a * 2], ay = p[a * 2 + 1], bx = p[b * 2], by = p[b * 2 + 1];
    const dx = bx - ax, dy = by - ay;
    const l2 = dx * dx + dy * dy;
    let maxD = 0, idx = -1;
    for (let i = a + 1; i < b; i++) {
      const px = p[i * 2], py = p[i * 2 + 1];
      let d: number;
      if (l2 === 0) d = (px - ax) ** 2 + (py - ay) ** 2;
      else {
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2));
        d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2;
      }
      if (d > maxD) { maxD = d; idx = i; }
    }
    if (idx >= 0 && maxD > t2) {
      conservar[idx] = 1;
      pila.push([a, idx], [idx, b]);
    }
  }
  const res: number[] = [];
  for (let i = 0; i < n; i++) if (conservar[i]) res.push(p[i * 2], p[i * 2 + 1]);
  return res;
}
