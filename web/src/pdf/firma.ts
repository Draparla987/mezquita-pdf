/**
 * Firma digital PAdES (ETSI.CAdES.detached, SHA-256) de un PDF.
 *
 * La firma se añade SIEMPRE como actualización incremental: se crea un campo de
 * firma nuevo (FirmaN) con su widget y su diccionario /Sig, se reserva el hueco de
 * /Contents, se calcula el SHA-256 de todo el archivo salvo ese hueco (/ByteRange)
 * y se incrusta la firma CMS. Si el documento ya tenía firmas, sus bytes no cambian,
 * por lo que siguen siendo válidas.
 */
import { PDFArray, PDFDict, PDFName, PDFRef, PDFString, PDFHexString } from 'pdf-lib';
import { construirCms } from './cms';
import { anadirAnotacionAPagina, cargarParaEditar, escribirIncremental } from './incremental';
import type { Credencial } from './p12';
import { crearAparienciaSello, type CajaPagina } from './sello';
import { buscar, ErrorPdf, fechaPdf, latin1, sha256, textoPdf, aHex, concatenar } from './util';

export interface OpcionesFirma {
  credencial: Credencial;
  /** Página (0 = primera) y recuadro del sello en unidades de página. Sin ellos, firma invisible. */
  pagina?: number;
  caja?: CajaPagina;
  motivo?: string;
  lugar?: string;
  contacto?: string;
  /** PNG de la rúbrica para el sello visible. */
  rubricaPng?: Uint8Array;
  fecha?: Date;
  urlTsa?: string;
  /** Incluir signingTime entre los atributos firmados (por defecto, sí). */
  incluirHoraFirma?: boolean;
}

export interface ResultadoFirma {
  bytes: Uint8Array;
  campo: string;
  firmasPrevias: number;
}

const SUBFILTER = 'ETSI.CAdES.detached';
const ANCHO_BYTERANGE = 3 * 11 + 1; // «0» + tres números de hasta 10 cifras con su espacio

function nombresCampos(doc: import('pdf-lib').PDFDocument, campos: PDFArray | undefined): { nombres: Set<string>; firmas: number } {
  const nombres = new Set<string>();
  let firmas = 0;
  const visitar = (arr: PDFArray | undefined, prefijo: string, profundidad: number) => {
    if (!arr || profundidad > 20) return;
    for (let i = 0; i < arr.size(); i++) {
      const campo = doc.context.lookup(arr.get(i));
      if (!(campo instanceof PDFDict)) continue;
      const t = campo.lookup(PDFName.of('T'));
      const parte = t instanceof PDFString || t instanceof PDFHexString ? t.decodeText() : '';
      const nombre = prefijo && parte ? `${prefijo}.${parte}` : parte || prefijo;
      if (nombre) nombres.add(nombre);
      if (campo.lookup(PDFName.of('FT')) === PDFName.of('Sig') && campo.lookup(PDFName.of('V'))) firmas++;
      visitar(campo.lookupMaybe(PDFName.of('Kids'), PDFArray), nombre, profundidad + 1);
    }
  };
  visitar(campos, '', 0);
  return { nombres, firmas };
}

/** Tamaño reservado para la firma CMS (en bytes; en el PDF ocupa el doble en hexadecimal). */
function tamanoReservado(c: Credencial, conTsa: boolean): number {
  const certs = c.certificadoDer.length + c.cadenaDer.reduce((s, d) => s + d.length, 0);
  return Math.ceil((certs + 4096 + (conTsa ? 12288 : 0)) / 1024) * 1024;
}

export async function firmarPdf(original: Uint8Array, o: OpcionesFirma): Promise<ResultadoFirma> {
  const ed = await cargarParaEditar(original);
  const { doc } = ed;
  const ctx = doc.context;
  const fecha = o.fecha ?? new Date();
  const paginas = doc.getPages();
  if (!paginas.length) throw new ErrorPdf('El documento no tiene páginas.');

  // --- Formulario (AcroForm) y nombre del campo -------------------------------
  const catalogo = doc.catalog;
  let acroForm = catalogo.lookupMaybe(PDFName.of('AcroForm'), PDFDict);
  const { nombres, firmas } = nombresCampos(doc, acroForm?.lookupMaybe(PDFName.of('Fields'), PDFArray));
  let n = 1;
  while (nombres.has(`Firma${n}`)) n++;
  const campo = `Firma${n}`;

  // --- Apariencia y widget ----------------------------------------------------
  const visible = o.pagina !== undefined && o.caja !== undefined && o.caja.w > 2 && o.caja.h > 2;
  const pagina = paginas[visible ? Math.min(Math.max(0, o.pagina!), paginas.length - 1) : 0];
  const titular = o.credencial.info.titular;
  let rect: number[] = [0, 0, 0, 0];
  let apRef: PDFRef;
  if (visible) {
    const sello = await crearAparienciaSello(doc, pagina, o.caja!, {
      titular, fecha, motivo: o.motivo, lugar: o.lugar, rubricaPng: o.rubricaPng,
    });
    apRef = sello.ref;
    rect = sello.rect;
  } else {
    apRef = ctx.register(ctx.stream('', { Type: 'XObject', Subtype: 'Form', BBox: [0, 0, 0, 0] } as never));
  }

  const refFirma = ctx.nextRef(); // el diccionario /Sig se escribe a mano (hay que rellenarlo después)
  const widget = ctx.obj({
    Type: 'Annot',
    Subtype: 'Widget',
    FT: 'Sig',
    T: PDFString.of(campo),
    V: refFirma,
    F: 132, // Imprimir + Bloqueado
    P: pagina.ref,
    Rect: rect,
    AP: { N: apRef },
  } as never) as unknown as PDFDict;
  const refWidget = ctx.register(widget);
  anadirAnotacionAPagina(doc, pagina.node, refWidget);

  if (!acroForm) {
    const nuevo = ctx.obj({ Fields: [refWidget], SigFlags: 3 } as never) as unknown as PDFDict;
    catalogo.set(PDFName.of('AcroForm'), ctx.register(nuevo));
    acroForm = nuevo;
  } else {
    const camposRaw = acroForm.get(PDFName.of('Fields'));
    const campos = camposRaw instanceof PDFRef ? ctx.lookup(camposRaw) : camposRaw;
    if (campos instanceof PDFArray) campos.push(refWidget);
    else acroForm.set(PDFName.of('Fields'), ctx.obj([refWidget]));
    const flags = acroForm.lookup(PDFName.of('SigFlags'));
    const actual = flags && 'asNumber' in flags ? (flags as unknown as { asNumber(): number }).asNumber() : 0;
    if ((actual & 3) !== 3) acroForm.set(PDFName.of('SigFlags'), ctx.obj(actual | 3));
  }

  // --- Diccionario de firma con huecos para /ByteRange y /Contents --------------
  const reservado = tamanoReservado(o.credencial, !!o.urlTsa);
  let dic = '<<\n/Type /Sig\n/Filter /Adobe.PPKLite\n/SubFilter /' + SUBFILTER + '\n';
  dic += '/ByteRange [' + ' '.repeat(ANCHO_BYTERANGE) + ']\n';
  dic += '/Contents <' + '0'.repeat(reservado * 2) + '>\n';
  dic += `/M ${textoPdf(fechaPdf(fecha))}\n`;
  dic += `/Name ${textoPdf(titular)}\n`;
  if (o.motivo) dic += `/Reason ${textoPdf(o.motivo)}\n`;
  if (o.lugar) dic += `/Location ${textoPdf(o.lugar)}\n`;
  if (o.contacto) dic += `/ContactInfo ${textoPdf(o.contacto)}\n`;
  dic += '/Prop_Build << /App << /Name /MezquitaPDF /REx (1.0) >> /Filter << /Name /Adobe.PPKLite >> >>\n>>';

  const { bytes, desplazamientos } = await escribirIncremental(ed, [{ ref: refFirma, datos: latin1(dic) }]);

  // --- Rellenar /ByteRange --------------------------------------------------------
  const inicioObj = desplazamientos.get(refFirma.objectNumber)!;
  const posBR = buscar(bytes, '/ByteRange [', inicioObj) + '/ByteRange ['.length;
  const posContenido = buscar(bytes, '/Contents <', inicioObj) + '/Contents '.length; // apunta a «<»
  const finContenido = posContenido + reservado * 2 + 2; // justo después de «>»
  if (posBR < inicioObj || posContenido < inicioObj || bytes[finContenido - 1] !== 0x3e) {
    throw new ErrorPdf('No se pudo preparar el hueco de la firma.');
  }
  const rangos = [0, posContenido, finContenido, bytes.length - finContenido];
  const textoRangos = rangos.join(' ').padEnd(ANCHO_BYTERANGE, ' ');
  if (textoRangos.length > ANCHO_BYTERANGE) throw new ErrorPdf('El documento es demasiado grande para firmarlo.');
  bytes.set(latin1(textoRangos), posBR);

  // --- Resumen, CMS e incrustación --------------------------------------------------
  const resumen = await sha256(concatenar([bytes.subarray(0, posContenido), bytes.subarray(finContenido)]));
  const cms = await construirCms({
    resumen, credencial: o.credencial, fecha, urlTsa: o.urlTsa, incluirHoraFirma: o.incluirHoraFirma,
  });
  if (cms.length > reservado) throw new ErrorPdf('La firma no cabe en el espacio reservado.');
  bytes.set(latin1(aHex(cms)), posContenido + 1);

  return { bytes, campo, firmasPrevias: firmas };
}
