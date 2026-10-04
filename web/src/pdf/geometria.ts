/**
 * Geometría de página. Las anotaciones se guardan en «unidades de página»: las
 * coordenadas de la vista de pdf.js a escala 1 (con la rotación de la página ya
 * aplicada y el eje Y hacia abajo). Aquí se reproduce exactamente la transformación
 * de `PageViewport` de pdf.js para poder pasar de esas unidades al espacio PDF sin
 * depender de pdf.js (así el mismo código funciona en Node).
 */
import type { PDFPage } from 'pdf-lib';

export type Matriz = [number, number, number, number, number, number];
export type Caja = [number, number, number, number]; // x0, y0, x1, y1 (espacio PDF)

/** Composición: primero se aplica `m2` y luego `m1` (igual que Util.transform de pdf.js). */
export function componer(m1: Matriz, m2: Matriz): Matriz {
  return [
    m1[0] * m2[0] + m1[2] * m2[1],
    m1[1] * m2[0] + m1[3] * m2[1],
    m1[0] * m2[2] + m1[2] * m2[3],
    m1[1] * m2[2] + m1[3] * m2[3],
    m1[0] * m2[4] + m1[2] * m2[5] + m1[4],
    m1[1] * m2[4] + m1[3] * m2[5] + m1[5],
  ];
}

export function invertir(m: Matriz): Matriz {
  const d = m[0] * m[3] - m[1] * m[2];
  return [
    m[3] / d,
    -m[1] / d,
    -m[2] / d,
    m[0] / d,
    (m[2] * m[5] - m[4] * m[3]) / d,
    (m[4] * m[1] - m[5] * m[0]) / d,
  ];
}

export function aplicar(m: Matriz, x: number, y: number): [number, number] {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

export interface Vista {
  /** Transformación espacio PDF → unidades de página (escala 1). */
  transform: Matriz;
  /** Inversa: unidades de página → espacio PDF. */
  inversa: Matriz;
  ancho: number;
  alto: number;
}

/** Igual que `new PageViewport({ viewBox, scale: 1, rotation })` de pdf.js. */
export function vistaDePagina(viewBox: Caja, rotacion: number): Vista {
  const centroX = (viewBox[2] + viewBox[0]) / 2;
  const centroY = (viewBox[3] + viewBox[1]) / 2;
  let rot = rotacion % 360;
  if (rot < 0) rot += 360;
  let a = 1, b = 0, c = 0, d = -1;
  switch (rot) {
    case 180: a = -1; b = 0; c = 0; d = 1; break;
    case 90: a = 0; b = 1; c = 1; d = 0; break;
    case 270: a = 0; b = -1; c = -1; d = 0; break;
    default: a = 1; b = 0; c = 0; d = -1;
  }
  let despX: number, despY: number, ancho: number, alto: number;
  if (a === 0) {
    despX = Math.abs(centroY - viewBox[1]);
    despY = Math.abs(centroX - viewBox[0]);
    ancho = viewBox[3] - viewBox[1];
    alto = viewBox[2] - viewBox[0];
  } else {
    despX = Math.abs(centroX - viewBox[0]);
    despY = Math.abs(centroY - viewBox[1]);
    ancho = viewBox[2] - viewBox[0];
    alto = viewBox[3] - viewBox[1];
  }
  const transform: Matriz = [a, b, c, d, despX - a * centroX - c * centroY, despY - b * centroX - d * centroY];
  return { transform, inversa: invertir(transform), ancho, alto };
}

function normalizar(r: Caja): Caja {
  return [Math.min(r[0], r[2]), Math.min(r[1], r[3]), Math.max(r[0], r[2]), Math.max(r[1], r[3])];
}

/** Caja visible de la página, con la misma lógica que `Page.view` de pdf.js. */
export function cajaVisible(pagina: PDFPage): Caja {
  const mb = pagina.getMediaBox();
  let media: Caja = normalizar([mb.x, mb.y, mb.x + mb.width, mb.y + mb.height]);
  if (!(media[2] - media[0] > 0 && media[3] - media[1] > 0)) media = [0, 0, 612, 792];
  const cb = pagina.getCropBox();
  const recorte: Caja = normalizar([cb.x, cb.y, cb.x + cb.width, cb.y + cb.height]);
  if (recorte.some((v, i) => v !== media[i])) {
    const x0 = Math.max(recorte[0], media[0]);
    const y0 = Math.max(recorte[1], media[1]);
    const x1 = Math.min(recorte[2], media[2]);
    const y1 = Math.min(recorte[3], media[3]);
    if (x1 - x0 > 0 && y1 - y0 > 0) return [x0, y0, x1, y1];
  }
  return media;
}

export function vistaDePaginaPdfLib(pagina: PDFPage): Vista {
  return vistaDePagina(cajaVisible(pagina), pagina.getRotation().angle);
}

/** Caja envolvente (espacio PDF) de un rectángulo dado en unidades de página. */
export function cajaPdf(vista: Vista, x: number, y: number, w: number, h: number, margen = 0): Caja {
  const puntos = [
    aplicar(vista.inversa, x - margen, y - margen),
    aplicar(vista.inversa, x + w + margen, y - margen),
    aplicar(vista.inversa, x - margen, y + h + margen),
    aplicar(vista.inversa, x + w + margen, y + h + margen),
  ];
  const xs = puntos.map((p) => p[0]);
  const ys = puntos.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
