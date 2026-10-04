/**
 * Apariencia visible de la firma digital, como en la app de escritorio:
 * rúbrica manuscrita a la izquierda y, a la derecha,
 * «Firmado digitalmente por: / <titular> / Fecha: … / Motivo: … / Lugar: …».
 * Se dibuja con texto vectorial (Helvetica), nítido a cualquier zoom.
 */
import { PDFDocument, PDFPage, PDFRef, StandardFonts } from 'pdf-lib';
import { sanearTexto } from './anotaciones-pdf';
import { cajaPdf, type Caja, vistaDePaginaPdfLib } from './geometria';
import { fechaLegible, num } from './util';

export interface DatosSello {
  titular: string;
  fecha: Date;
  motivo?: string;
  lugar?: string;
  /** PNG con fondo transparente de la rúbrica manuscrita (opcional). */
  rubricaPng?: Uint8Array;
}

export interface CajaPagina { x: number; y: number; w: number; h: number }

export function lineasSello(d: DatosSello): Array<{ texto: string; negrita: boolean }> {
  const lineas = [
    { texto: 'Firmado digitalmente por:', negrita: false },
    { texto: d.titular, negrita: true },
    { texto: `Fecha: ${fechaLegible(d.fecha)}`, negrita: false },
  ];
  if (d.motivo) lineas.push({ texto: `Motivo: ${d.motivo}`, negrita: false });
  if (d.lugar) lineas.push({ texto: `Lugar: ${d.lugar}`, negrita: false });
  return lineas;
}

export async function crearAparienciaSello(
  doc: PDFDocument, pagina: PDFPage, caja: CajaPagina, d: DatosSello,
): Promise<{ ref: PDFRef; rect: Caja }> {
  const ctx = doc.context;
  const vista = vistaDePaginaPdfLib(pagina);
  const normal = await doc.embedFont(StandardFonts.Helvetica);
  const negrita = await doc.embedFont(StandardFonts.HelveticaBold);
  const { x, y, w, h } = caja;
  const margen = Math.min(w, h) * 0.06;
  let ops = '';
  const recursos: Record<string, unknown> = { Font: { F1: normal.ref, F2: negrita.ref } };

  let xTexto = x + margen;
  if (d.rubricaPng) {
    const img = await doc.embedPng(d.rubricaPng);
    const anchoZona = w * 0.45;
    const aw = anchoZona - 2 * margen;
    const ah = h - 2 * margen;
    const escala = Math.min(aw / img.width, ah / img.height);
    const iw = img.width * escala;
    const ih = img.height * escala;
    const ix = x + (anchoZona - iw) / 2;
    const iy = y + (h - ih) / 2;
    ops += `q ${num(iw)} 0 0 ${num(-ih)} ${num(ix)} ${num(iy + ih)} cm /Im0 Do Q\n`;
    ops += `0.47 0.47 0.47 RG ${num(Math.max(0.4, h * 0.008))} w ${num(x + anchoZona)} ${num(y + h * 0.12)} m ` +
      `${num(x + anchoZona)} ${num(y + h * 0.88)} l S\n`;
    recursos.XObject = { Im0: img.ref };
    xTexto = x + anchoZona + margen;
  }

  const lineas = lineasSello(d).map((l) => ({
    ...l,
    texto: sanearTexto(l.texto, l.negrita ? negrita : normal),
  }));
  const disponible = x + w - margen - xTexto;
  let tam = h / (lineas.length * 1.3 + 0.5);
  const anchoMax = (t: number) =>
    Math.max(...lineas.map((l) => (l.negrita ? negrita : normal).widthOfTextAtSize(l.texto, t)));
  while (tam > 2 && anchoMax(tam) > disponible) tam -= 0.25;
  const interlinea = tam * 1.25;
  const arriba = y + (h - interlinea * lineas.length) / 2;
  ops += 'BT 0.08 0.08 0.08 rg\n';
  lineas.forEach((l, i) => {
    const base = arriba + interlinea * i + tam * 0.92;
    const f = l.negrita ? negrita : normal;
    ops += `/${l.negrita ? 'F2' : 'F1'} ${num(tam)} Tf 1 0 0 -1 ${num(xTexto)} ${num(base)} Tm ` +
      `${f.encodeText(l.texto).toString()} Tj\n`;
  });
  ops += 'ET';

  const rect = cajaPdf(vista, x, y, w, h);
  const ref = ctx.register(ctx.flateStream(`q ${vista.inversa.map(num).join(' ')} cm\n${ops}\nQ`, {
    Type: 'XObject', Subtype: 'Form', BBox: rect, Resources: recursos,
  } as never));
  return { ref, rect };
}
