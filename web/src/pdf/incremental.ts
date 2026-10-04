/**
 * Escritura de PDF por «actualización incremental».
 *
 * pdf-lib solo sabe reescribir el documento entero, lo que invalidaría las firmas
 * digitales que ya tuviera. Aquí se usa pdf-lib únicamente como modelo de objetos:
 *
 *   1. Se carga el documento y se toma una «instantánea» (huella de cada objeto).
 *   2. Se modifica con la API de pdf-lib (nuevas anotaciones, campos de firma…).
 *   3. Se añaden AL FINAL del archivo original solo los objetos nuevos o cambiados,
 *      con su propia tabla de referencias cruzadas (tabla clásica o flujo XRef, según
 *      el formato del original) y un tráiler con /Prev apuntando a la anterior.
 *
 * Los bytes originales no se tocan, así que las firmas previas siguen siendo válidas.
 */
import {
  PDFArray, PDFDict, PDFDocument, PDFHexString, PDFName, PDFObject, PDFRef, PDFStream,
} from 'pdf-lib';
import { aHex, buscar, buscarUltimo, bytesAleatorios, concatenar, ErrorPdf, latin1 } from './util';

export interface Instantanea {
  huellas: Map<string, string>;
}

export interface InfoCola {
  /** Desplazamiento de la última sección de referencias cruzadas. */
  startxref: number;
  /** true si la última sección es un flujo XRef (PDF 1.5+). */
  esFlujo: boolean;
  /** /Size declarado en el último tráiler. */
  tamano: number;
}

export interface DocumentoEditable {
  doc: PDFDocument;
  instantanea: Instantanea;
  cola: InfoCola;
  original: Uint8Array;
}

export interface ObjetoCrudo {
  ref: PDFRef;
  /** Cuerpo del objeto ya serializado (sin «n g obj» ni «endobj»). */
  datos: Uint8Array;
}

const idsObjetos = new WeakMap<object, number>();
let siguienteId = 1;
function idObjeto(o: object): number {
  let id = idsObjetos.get(o);
  if (id === undefined) {
    id = siguienteId++;
    idsObjetos.set(o, id);
  }
  return id;
}

/** Huella de un objeto para detectar cambios sin serializar el contenido de los flujos. */
function huella(obj: PDFObject): string {
  if (obj instanceof PDFStream) {
    // No se llama a toString() del flujo: actualizaría /Length y copiaría todo su contenido.
    return 'S' + obj.dict.toString() + '#' + idObjeto(obj);
  }
  return obj.toString();
}

export function tomarInstantanea(doc: PDFDocument): Instantanea {
  const huellas = new Map<string, string>();
  for (const [ref, obj] of doc.context.enumerateIndirectObjects()) huellas.set(ref.tag, huella(obj));
  return { huellas };
}

function esBlanco(b: number): boolean {
  return b === 0x20 || b === 0x0a || b === 0x0d || b === 0x09 || b === 0x0c || b === 0x00;
}

function texto(datos: Uint8Array, desde: number, hasta: number): string {
  let s = '';
  for (let i = desde; i < Math.min(hasta, datos.length); i++) s += String.fromCharCode(datos[i]);
  return s;
}

/** Lee el final del archivo: posición de la última tabla XRef, su tipo y /Size. */
export function analizarCola(datos: Uint8Array): InfoCola | null {
  const pos = buscarUltimo(datos, 'startxref');
  if (pos < 0) return null;
  const m = /startxref\s+(\d+)/.exec(texto(datos, pos, pos + 40));
  if (!m) return null;
  const startxref = parseInt(m[1], 10);
  if (!(startxref > 0 && startxref < datos.length)) return null;
  let i = startxref;
  while (i < datos.length && esBlanco(datos[i])) i++;
  if (texto(datos, i, i + 4) === 'xref') {
    const t = buscar(datos, 'trailer', i);
    if (t < 0) return null;
    const fin = buscar(datos, 'startxref', t);
    const dic = texto(datos, t, fin > 0 ? fin : t + 4096);
    const s = /\/Size\s+(\d+)/.exec(dic);
    return { startxref, esFlujo: false, tamano: s ? parseInt(s[1], 10) : 0 };
  }
  const cab = texto(datos, i, i + 4096);
  if (/^\d+\s+\d+\s+obj/.test(cab) && /\/Type\s*\/XRef/.test(cab.split('stream')[0])) {
    const s = /\/Size\s+(\d+)/.exec(cab.split('stream')[0]);
    return { startxref, esFlujo: true, tamano: s ? parseInt(s[1], 10) : 0 };
  }
  return null;
}

/**
 * Carga un PDF para modificarlo de forma incremental.
 * Lanza un error comprensible si el documento está cifrado.
 */
export async function cargarParaEditar(original: Uint8Array): Promise<DocumentoEditable> {
  let doc: PDFDocument;
  try {
    doc = await PDFDocument.load(original, { updateMetadata: false, ignoreEncryption: true });
  } catch (e) {
    throw new ErrorPdf(`No se pudo leer la estructura del PDF: ${(e as Error).message}`);
  }
  if (doc.isEncrypted) {
    throw new ErrorPdf(
      'El documento está protegido con contraseña (cifrado). Se puede ver, pero no modificar ni firmar desde la web.',
    );
  }
  const cola = analizarCola(original) ?? { startxref: 0, esFlujo: false, tamano: 0 };
  // Los flujos XRef y de objetos no se guardan en el contexto de pdf-lib: hay que
  // evitar reutilizar sus números al crear objetos nuevos.
  doc.context.largestObjectNumber = Math.max(doc.context.largestObjectNumber, cola.tamano - 1);
  doc.getPages(); // fuerza el recorrido del árbol de páginas antes de la instantánea
  return { doc, instantanea: tomarInstantanea(doc), cola, original };
}

function serializar(obj: PDFObject): Uint8Array {
  const buf = new Uint8Array(obj.sizeInBytes());
  obj.copyBytesInto(buf, 0);
  return buf;
}

function subsecciones(numeros: number[]): Array<[number, number]> {
  const res: Array<[number, number]> = [];
  for (const n of numeros) {
    const ultimo = res[res.length - 1];
    if (ultimo && ultimo[0] + ultimo[1] === n) ultimo[1]++;
    else res.push([n, 1]);
  }
  return res;
}

export interface ResultadoEscritura {
  bytes: Uint8Array;
  /** Número de objeto → desplazamiento absoluto en el archivo resultante. */
  desplazamientos: Map<number, number>;
  objetosEscritos: number;
}

/**
 * Añade al final de `ed.original` los objetos nuevos o modificados del documento,
 * más los objetos crudos indicados (p. ej. el diccionario de firma).
 */
export async function escribirIncremental(ed: DocumentoEditable, extras: ObjetoCrudo[] = []): Promise<ResultadoEscritura> {
  const { doc, instantanea, cola, original } = ed;
  await doc.flush();

  const partes: Uint8Array[] = [original];
  let pos = original.length;
  const ultimo = original[original.length - 1];
  if (ultimo !== 0x0a && ultimo !== 0x0d) {
    partes.push(latin1('\n'));
    pos += 1;
  }
  const entradas = new Map<number, { despl: number; gen: number }>();
  const anadir = (cabecera: string, cuerpo: Uint8Array, numero: number, gen: number) => {
    const ini = latin1(cabecera);
    const fin = latin1('\nendobj\n');
    entradas.set(numero, { despl: pos, gen });
    partes.push(ini, cuerpo, fin);
    pos += ini.length + cuerpo.length + fin.length;
  };

  const cambiados = doc.context
    .enumerateIndirectObjects()
    .filter(([ref, obj]) => instantanea.huellas.get(ref.tag) !== huella(obj))
    .sort((a, b) => a[0].objectNumber - b[0].objectNumber);
  for (const [ref, obj] of cambiados) {
    anadir(`${ref.objectNumber} ${ref.generationNumber} obj\n`, serializar(obj), ref.objectNumber, ref.generationNumber);
  }
  for (const extra of extras) {
    anadir(`${extra.ref.objectNumber} ${extra.ref.generationNumber} obj\n`, extra.datos, extra.ref.objectNumber,
      extra.ref.generationNumber);
  }

  let maximo = 0;
  for (const n of entradas.keys()) maximo = Math.max(maximo, n);
  const info = doc.context.trailerInfo;
  const raiz = info.Root instanceof PDFRef ? info.Root.toString() : null;
  if (!raiz) throw new ErrorPdf('El PDF no tiene catálogo (/Root) válido.');
  const infoDoc = info.Info ? ` /Info ${info.Info.toString()}` : '';
  let id0 = '';
  const ids = info.ID instanceof PDFArray ? info.ID : (info.ID ? doc.context.lookup(info.ID) : undefined);
  if (ids instanceof PDFArray && ids.size() > 0) id0 = ids.get(0).toString();
  if (!id0) id0 = '<' + aHex(bytesAleatorios(16)) + '>';
  const id = ` /ID [${id0} <${aHex(bytesAleatorios(16))}>]`;
  const prev = cola.startxref > 0 ? ` /Prev ${cola.startxref}` : '';

  if (cola.esFlujo) {
    // Sección como flujo XRef (el original usa flujos XRef: se mantiene el formato).
    const numXref = Math.max(cola.tamano, maximo + 1, doc.context.largestObjectNumber + 1);
    const despXref = pos;
    entradas.set(numXref, { despl: despXref, gen: 0 });
    const numeros = [...entradas.keys()].sort((a, b) => a - b);
    const datos = new Uint8Array(numeros.length * 7);
    numeros.forEach((n, i) => {
      const e = entradas.get(n)!;
      const o = i * 7;
      datos[o] = 1;
      datos[o + 1] = (e.despl >>> 24) & 255;
      datos[o + 2] = (e.despl >>> 16) & 255;
      datos[o + 3] = (e.despl >>> 8) & 255;
      datos[o + 4] = e.despl & 255;
      datos[o + 5] = (e.gen >> 8) & 255;
      datos[o + 6] = e.gen & 255;
    });
    const indice = subsecciones(numeros).map(([a, b]) => `${a} ${b}`).join(' ');
    const dic = `<< /Type /XRef /Size ${numXref + 1} /Index [${indice}] /W [1 4 2] /Root ${raiz}${infoDoc}${id}${prev}` +
      ` /Length ${datos.length} >>\nstream\n`;
    partes.push(latin1(`${numXref} 0 obj\n${dic}`), datos, latin1(`\nendstream\nendobj\nstartxref\n${despXref}\n%%EOF\n`));
  } else {
    const numeros = [...entradas.keys()].sort((a, b) => a - b);
    let tabla = 'xref\n';
    for (const [inicio, cantidad] of subsecciones(numeros)) {
      tabla += `${inicio} ${cantidad}\n`;
      for (let n = inicio; n < inicio + cantidad; n++) {
        const e = entradas.get(n)!;
        tabla += `${String(e.despl).padStart(10, '0')} ${String(e.gen).padStart(5, '0')} n\r\n`;
      }
    }
    const tamano = Math.max(cola.tamano, maximo + 1, doc.context.largestObjectNumber + 1);
    tabla += `trailer\n<< /Size ${tamano} /Root ${raiz}${infoDoc}${id}${prev} >>\nstartxref\n${pos}\n%%EOF\n`;
    partes.push(latin1(tabla));
  }

  const desplazamientos = new Map<number, number>();
  for (const [n, e] of entradas) desplazamientos.set(n, e.despl);
  return { bytes: concatenar(partes), desplazamientos, objetosEscritos: cambiados.length + extras.length };
}

/* ------------------------------------------------------------------------ */
/* Ayudas para modificar páginas sin alterar objetos compartidos             */
/* ------------------------------------------------------------------------ */

/** Añade una anotación a /Annots de la página (respetando si el array es indirecto). */
export function anadirAnotacionAPagina(doc: PDFDocument, paginaDict: PDFDict, ref: PDFRef): void {
  const actual = paginaDict.get(PDFName.of('Annots'));
  if (actual instanceof PDFRef) {
    const arr = doc.context.lookup(actual);
    if (arr instanceof PDFArray) {
      arr.push(ref);
      return;
    }
  }
  if (actual instanceof PDFArray) {
    actual.push(ref);
    return;
  }
  paginaDict.set(PDFName.of('Annots'), doc.context.obj([ref]));
}

/** Copia superficial de un diccionario (los valores indirectos siguen siendo referencias). */
export function copiarDict(doc: PDFDocument, dict: PDFDict | undefined): PDFDict {
  const nuevo = doc.context.obj({});
  if (dict) for (const [k, v] of dict.entries()) nuevo.set(k, v);
  return nuevo;
}

export function textoHex(s: string): PDFHexString {
  return PDFHexString.fromText(s);
}
