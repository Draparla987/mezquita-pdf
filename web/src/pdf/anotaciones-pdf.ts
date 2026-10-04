/**
 * Escribe las anotaciones del editor en el PDF (con pdf-lib + actualización incremental).
 *
 * Cada anotación se dibuja en un Form XObject (su «apariencia») en el espacio PDF.
 * Después, según la opción elegida:
 *   - aplanar: el XObject se pinta en el contenido de la página (se ve en cualquier
 *     visor, pero ya no se puede borrar como anotación);
 *   - anotaciones: se crea una anotación PDF de verdad (/Highlight, /Ink, /Square,
 *     /FreeText, /Stamp) con esa apariencia, editable en otras aplicaciones.
 * Si el documento ya tiene firmas digitales se usan siempre anotaciones, que es un
 * cambio permitido después de firmar; modificar el contenido de la página no lo es.
 */
import {
  PDFDict, PDFDocument, PDFFont, PDFHexString, PDFImage, PDFName, PDFPage, PDFRef, PDFString,
  StandardFonts, PDFArray,
} from 'pdf-lib';
import {
  type Anotacion, OPACIDAD_RESALTADO, TEXTO_ASCENSO, TEXTO_INTERLINEA, segmentosSuaves,
} from '../modelo';
import { aplicar, cajaPdf, type Caja, type Vista, vistaDePaginaPdfLib } from './geometria';
import { anadirAnotacionAPagina, cargarParaEditar, copiarDict, escribirIncremental } from './incremental';
import { bytesDeDataUrl, colorRgb, fechaPdf, num } from './util';

export interface OpcionesAnotaciones {
  /** true: pintar en el contenido de la página; false: anotaciones PDF editables. */
  aplanar: boolean;
}

/** Sustituye los caracteres que la fuente estándar (WinAnsi) no puede codificar. */
export function sanearTexto(texto: string, fuente: PDFFont): string {
  const soportados = new Set(fuente.getCharacterSet());
  let s = '';
  for (const ch of texto) {
    const cp = ch.codePointAt(0)!;
    if (soportados.has(cp)) {
      s += ch;
      continue;
    }
    const base = ch.normalize('NFD').replace(/[̀-ͯ]/g, '');
    s += base && [...base].every((c) => soportados.has(c.codePointAt(0)!)) ? base : '?';
  }
  return s;
}

interface Apariencia {
  contenido: string;
  recursos: Record<string, unknown>;
  rect: Caja;
}

class Recursos {
  private fuentes = new Map<string, PDFFont>();
  private imagenes = new Map<string, PDFImage>();
  constructor(private doc: PDFDocument) {}

  async fuente(nombre: StandardFonts = StandardFonts.Helvetica): Promise<PDFFont> {
    let f = this.fuentes.get(nombre);
    if (!f) {
      f = await this.doc.embedFont(nombre);
      this.fuentes.set(nombre, f);
    }
    return f;
  }

  async imagen(dataUrl: string): Promise<PDFImage> {
    let img = this.imagenes.get(dataUrl);
    if (!img) {
      const bytes = bytesDeDataUrl(dataUrl);
      img = dataUrl.startsWith('data:image/jp')
        ? await this.doc.embedJpg(bytes)
        : await this.doc.embedPng(bytes);
      this.imagenes.set(dataUrl, img);
    }
    return img;
  }
}

function rgb(color: string): string {
  return colorRgb(color).map(num).join(' ');
}

async function apariencia(a: Anotacion, vista: Vista, rec: Recursos): Promise<Apariencia> {
  switch (a.tipo) {
    case 'resaltado':
      return {
        contenido: `/GS0 gs ${rgb(a.color)} rg ${num(a.x)} ${num(a.y)} ${num(a.w)} ${num(a.h)} re f`,
        recursos: {
          ExtGState: { GS0: { Type: 'ExtGState', BM: 'Multiply', ca: OPACIDAD_RESALTADO, CA: OPACIDAD_RESALTADO } },
        },
        rect: cajaPdf(vista, a.x, a.y, a.w, a.h),
      };
    case 'rectangulo':
      return {
        contenido: `${num(a.grosor)} w 0 j ${rgb(a.color)} RG ${num(a.x)} ${num(a.y)} ${num(a.w)} ${num(a.h)} re S`,
        recursos: {},
        rect: cajaPdf(vista, a.x, a.y, a.w, a.h, a.grosor / 2 + 1),
      };
    case 'trazo': {
      const p = a.puntos;
      let ruta = `${num(p[0])} ${num(p[1])} m\n`;
      const segs = segmentosSuaves(p);
      if (!segs.length) ruta += `${num(p[0])} ${num(p[1])} l\n`;
      for (const [x0, y0, cx, cy, x1, y1] of segs) {
        const c1x = x0 + (2 / 3) * (cx - x0), c1y = y0 + (2 / 3) * (cy - y0);
        const c2x = x1 + (2 / 3) * (cx - x1), c2y = y1 + (2 / 3) * (cy - y1);
        ruta += `${num(c1x)} ${num(c1y)} ${num(c2x)} ${num(c2y)} ${num(x1)} ${num(y1)} c\n`;
      }
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let i = 0; i < p.length; i += 2) {
        x0 = Math.min(x0, p[i]); x1 = Math.max(x1, p[i]);
        y0 = Math.min(y0, p[i + 1]); y1 = Math.max(y1, p[i + 1]);
      }
      return {
        contenido: `${num(a.grosor)} w 1 J 1 j ${rgb(a.color)} RG\n${ruta}S`,
        recursos: {},
        rect: cajaPdf(vista, x0, y0, x1 - x0, y1 - y0, a.grosor / 2 + 1),
      };
    }
    case 'texto': {
      const fuente = await rec.fuente();
      const lineas = a.texto.split('\n').map((l) => sanearTexto(l, fuente));
      let ancho = 0;
      let ops = `BT /F1 ${num(a.tam)} Tf ${rgb(a.color)} rg\n`;
      lineas.forEach((linea, i) => {
        ancho = Math.max(ancho, fuente.widthOfTextAtSize(linea, a.tam));
        const base = a.y + a.tam * (TEXTO_ASCENSO + TEXTO_INTERLINEA * i);
        ops += `1 0 0 -1 ${num(a.x)} ${num(base)} Tm ${fuente.encodeText(linea).toString()} Tj\n`;
      });
      ops += 'ET';
      const alto = a.tam * (TEXTO_INTERLINEA * (lineas.length - 1) + 1.15);
      return {
        contenido: ops,
        recursos: { Font: { F1: fuente.ref } },
        rect: cajaPdf(vista, a.x, a.y, ancho, alto, 2),
      };
    }
    case 'imagen': {
      const img = await rec.imagen(a.png);
      return {
        contenido: `q ${num(a.w)} 0 0 ${num(-a.h)} ${num(a.x)} ${num(a.y + a.h)} cm /Im0 Do Q`,
        recursos: { XObject: { Im0: img.ref } },
        rect: cajaPdf(vista, a.x, a.y, a.w, a.h),
      };
    }
  }
}

function dictAnotacion(
  doc: PDFDocument, a: Anotacion, ap: Apariencia, formRef: PDFRef, pagina: PDFPage, vista: Vista,
): PDFDict {
  const ctx = doc.context;
  const comun: Record<string, unknown> = {
    Type: 'Annot',
    Rect: ap.rect,
    F: 4,
    P: pagina.ref,
    NM: PDFString.of(a.id),
    M: PDFString.of(fechaPdf(new Date())),
    AP: { N: formRef },
  };
  switch (a.tipo) {
    case 'resaltado': {
      const tl = aplicar(vista.inversa, a.x, a.y);
      const tr = aplicar(vista.inversa, a.x + a.w, a.y);
      const bl = aplicar(vista.inversa, a.x, a.y + a.h);
      const br = aplicar(vista.inversa, a.x + a.w, a.y + a.h);
      return ctx.obj({
        ...comun, Subtype: 'Highlight', C: colorRgb(a.color),
        QuadPoints: [...tl, ...tr, ...bl, ...br],
      } as never) as unknown as PDFDict;
    }
    case 'rectangulo':
      return ctx.obj({
        ...comun, Subtype: 'Square', C: colorRgb(a.color), BS: { W: a.grosor, S: 'S' },
      } as never) as unknown as PDFDict;
    case 'trazo': {
      const puntos: number[] = [];
      for (let i = 0; i < a.puntos.length; i += 2) puntos.push(...aplicar(vista.inversa, a.puntos[i], a.puntos[i + 1]));
      return ctx.obj({
        ...comun, Subtype: 'Ink', C: colorRgb(a.color), BS: { W: a.grosor, S: 'S' }, InkList: [puntos],
      } as never) as unknown as PDFDict;
    }
    case 'texto': {
      const [r, g, b] = colorRgb(a.color);
      return ctx.obj({
        ...comun, Subtype: 'FreeText', Contents: PDFHexString.fromText(a.texto),
        DA: PDFString.of(`/Helv ${num(a.tam)} Tf ${num(r)} ${num(g)} ${num(b)} rg`),
        BS: { W: 0 }, Q: 0,
      } as never) as unknown as PDFDict;
    }
    case 'imagen':
      return ctx.obj({
        ...comun, Subtype: 'Stamp', Name: 'MezquitaFirma', Contents: PDFHexString.fromText('Firma manuscrita'),
      } as never) as unknown as PDFDict;
  }
}

/** Pinta los XObject en el contenido de la página, envolviendo el contenido original en q … Q. */
function aplanarEnPagina(doc: PDFDocument, pagina: PDFPage, formularios: PDFRef[]): void {
  const ctx = doc.context;
  const nodo = pagina.node;
  // Copia propia de los recursos: no se tocan diccionarios compartidos con otras páginas.
  const recursos = copiarDict(doc, nodo.Resources());
  const xobj = copiarDict(doc, recursos.lookupMaybe(PDFName.of('XObject'), PDFDict));
  let ops = 'Q\n';
  let k = 0;
  for (const ref of formularios) {
    let nombre: string;
    do nombre = `MzPdf${k++}`; while (xobj.has(PDFName.of(nombre)));
    xobj.set(PDFName.of(nombre), ref);
    ops += `q /${nombre} Do Q\n`;
  }
  recursos.set(PDFName.of('XObject'), xobj);
  nodo.set(PDFName.of('Resources'), recursos);

  const previos: PDFRef[] = [];
  const contenido = nodo.get(PDFName.of('Contents'));
  if (contenido instanceof PDFRef) {
    const o = ctx.lookup(contenido);
    if (o instanceof PDFArray) for (const r of o.asArray()) previos.push(r as PDFRef);
    else previos.push(contenido);
  } else if (contenido instanceof PDFArray) {
    for (const r of contenido.asArray()) previos.push(r as PDFRef);
  }
  const ini = ctx.register(ctx.stream('q\n'));
  const fin = ctx.register(ctx.flateStream(ops));
  nodo.set(PDFName.of('Contents'), ctx.obj([ini, ...previos, fin]));
}

/**
 * Devuelve un PDF nuevo con las anotaciones añadidas como actualización incremental
 * del original (los bytes originales quedan intactos).
 */
export async function aplicarAnotaciones(
  original: Uint8Array, anotaciones: Anotacion[], opciones: OpcionesAnotaciones,
): Promise<Uint8Array> {
  if (!anotaciones.length) return original;
  const ed = await cargarParaEditar(original);
  const { doc } = ed;
  const ctx = doc.context;
  const paginas = doc.getPages();
  const rec = new Recursos(doc);

  const porPagina = new Map<number, Anotacion[]>();
  for (const a of anotaciones) {
    if (!porPagina.has(a.pagina)) porPagina.set(a.pagina, []);
    porPagina.get(a.pagina)!.push(a);
  }
  for (const [indice, lista] of porPagina) {
    const pagina = paginas[indice];
    if (!pagina) continue;
    const vista = vistaDePaginaPdfLib(pagina);
    const cm = `${vista.inversa.map(num).join(' ')} cm`;
    const aplanados: PDFRef[] = [];
    for (const a of lista) {
      const ap = await apariencia(a, vista, rec);
      const formRef = ctx.register(ctx.flateStream(`q ${cm}\n${ap.contenido}\nQ`, {
        Type: 'XObject', Subtype: 'Form', BBox: ap.rect, Resources: ap.recursos,
      } as never));
      if (opciones.aplanar) {
        aplanados.push(formRef);
      } else {
        const ref = ctx.register(dictAnotacion(doc, a, ap, formRef, pagina, vista));
        anadirAnotacionAPagina(doc, pagina.node, ref);
      }
    }
    if (aplanados.length) aplanarEnPagina(doc, pagina, aplanados);
  }
  const resultado = await escribirIncremental(ed);
  return resultado.bytes;
}
