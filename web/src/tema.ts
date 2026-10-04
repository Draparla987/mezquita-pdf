/**
 * Identidad visual: arcos de herradura de la Mezquita de Córdoba (dovelas alternas
 * rojo ladrillo y crema). Traducción a SVG de `dibujar_arco` de visor/tema.py.
 */

export const NOMBRE_APP = 'Mezquita PDF';
export const VERSION = '1.0.0';

export const COLORES_RESALTADO = ['#FFD60A', '#8CE99A', '#74C0FC', '#FFA8C5', '#FFC078'];
export const COLORES_TRAZO = ['#8E1B2C', '#E03131', '#1C7ED6', '#2F9E44', '#212529'];
export const COLORES_FIRMA = ['#0F1E6E', '#111111', '#8E1B2C'];

interface Rect { x: number; y: number; w: number; h: number }

const f = (n: number) => (Math.round(n * 100) / 100).toString();

/**
 * Dibuja un arco de herradura dentro de `r`. Las clases CSS permiten colorearlo
 * según el tema (claro/oscuro): .dovela-a, .dovela-b y .columna.
 */
export function arcoSvg(r: Rect, dovelas = 13, columnas = true): string {
  const cx = r.x + r.w / 2;
  const ext = Math.min(r.w * 0.46, r.h * 0.4);
  const int = ext * 0.66;
  const cy = r.y + ext + r.h * 0.03;
  const extra = 28;
  const inicio = -extra;
  const paso = (180 + 2 * extra) / dovelas;
  const p = (radio: number, grados: number) => {
    const a = (grados * Math.PI) / 180;
    return `${f(cx + radio * Math.cos(a))} ${f(cy - radio * Math.sin(a))}`;
  };
  let svg = '';
  for (let i = 0; i < dovelas; i++) {
    const a0 = inicio + i * paso;
    const a1 = a0 + paso;
    svg += `<path class="${i % 2 === 0 ? 'dovela-a' : 'dovela-b'}" d="M${p(ext, a0)}A${f(ext)} ${f(ext)} 0 0 0 ${p(ext, a1)}` +
      `L${p(int, a1)}A${f(int)} ${f(int)} 0 0 1 ${p(int, a0)}Z"/>`;
  }
  if (columnas) {
    const ang = (extra * Math.PI) / 180;
    const arranque = cy + int * Math.sin(ang);
    const g = (ext - int) * 0.55;
    const abajo = r.y + r.h;
    for (const signo of [-1, 1]) {
      const x = cx + (signo * (ext + int)) / 2 * Math.cos(ang);
      const partes: Rect[] = [
        { x: x - g / 2, y: arranque, w: g, h: abajo - arranque - g * 0.5 },
        { x: x - g * 0.9, y: arranque - g * 0.15, w: g * 1.8, h: g * 0.55 },
        { x: x - g * 0.8, y: abajo - g * 0.6, w: g * 1.6, h: g * 0.6 },
      ];
      for (const q of partes) svg += `<rect class="columna" x="${f(q.x)}" y="${f(q.y)}" width="${f(q.w)}" height="${f(q.h)}"/>`;
    }
  }
  return svg;
}

/** Friso decorativo con una arquería (pantalla de bienvenida). */
export function frisoSvg(ancho: number, alto = 120): string {
  const n = Math.max(4, Math.round(ancho / 150));
  const total = ancho + 40;
  const celda = total / n;
  let arcos = '';
  for (let i = 0; i < n; i++) {
    arcos += arcoSvg({ x: -20 + i * celda + celda * 0.02, y: 0, w: celda * 0.96, h: alto });
  }
  return `<svg class="friso" width="${ancho}" height="${alto}" viewBox="0 0 ${ancho} ${alto}" aria-hidden="true">${arcos}</svg>`;
}
