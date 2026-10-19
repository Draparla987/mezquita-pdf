/**
 * Combinar varios PDF (o fotos y escaneos) en un documento nuevo. Todo ocurre en el
 * dispositivo con pdf-lib. El resultado se abre como un documento más (y queda en Recientes).
 */
import { PDFDocument } from 'pdf-lib';
import { icono } from './iconos';
import { NOMBRE_APP } from './tema';
import { abrirHoja, campo, el, escapar, ocupado, pintar, tamLegible, toast } from './ui/componentes';

const A4: [number, number] = [595.28, 841.89];
const MARGEN_IMAGEN = 24;
const LADO_MAX_IMAGEN = 2400; // px: suficiente para imprimir y sin agotar la memoria del iPhone

interface Parte {
  nombre: string;
  tipo: 'pdf' | 'imagen' | 'abierto';
  doc: PDFDocument;
  tam: number;
  paginas: number[] | null; // null = todas
  rango: string;
  firmado: boolean;
}

/** Evento con el que se pide abrir el resultado (lo atiende main.ts). */
export const EVENTO_ABRIR = 'mezquita:abrir-archivo';

/** «1-3, 5, 8-» → índices desde 0. Lanza un error si no es válido. */
export function parsearRango(texto: string, total: number): number[] {
  const paginas: number[] = [];
  for (const parte of texto.replace(/\s/g, '').split(',')) {
    if (!parte) continue;
    const m = /^(\d*)-(\d*)$/.exec(parte);
    if (m) {
      let a = m[1] ? Number(m[1]) : 1;
      let b = m[2] ? Number(m[2]) : total;
      if (a > b) [a, b] = [b, a];
      for (let p = a; p <= b; p++) paginas.push(p);
    } else if (/^\d+$/.test(parte)) {
      paginas.push(Number(parte));
    } else {
      throw new Error('rango no válido');
    }
  }
  if (!paginas.length || paginas.some((p) => p < 1 || p > total)) throw new Error('rango no válido');
  return paginas.map((p) => p - 1);
}

function estaFirmado(bytes: Uint8Array): boolean {
  // Las firmas PAdES/CAdES guardan siempre un /ByteRange en el diccionario de firma.
  const trozo = 1 << 20;
  const decodificador = new TextDecoder('latin1');
  for (let i = 0; i < bytes.length; i += trozo - 16) {
    if (decodificador.decode(bytes.subarray(i, i + trozo)).includes('/ByteRange')) return true;
  }
  return false;
}

async function cargarPdf(bytes: Uint8Array): Promise<PDFDocument> {
  try {
    return await PDFDocument.load(bytes, { updateMetadata: false });
  } catch (e) {
    if ((e as Error).name === 'EncryptedPDFError' || /encrypt/i.test((e as Error).message)) {
      throw new Error('está protegido con contraseña (combínalo desde el Mac)');
    }
    throw new Error('no es un PDF válido');
  }
}

/** Coloca una foto en una página A4 (vertical u horizontal según la foto), respetando su orientación. */
async function imagenAPdf(archivo: File): Promise<PDFDocument> {
  const url = URL.createObjectURL(archivo);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const escala = Math.min(1, LADO_MAX_IMAGEN / Math.max(img.naturalWidth, img.naturalHeight));
    const w = Math.max(1, Math.round(img.naturalWidth * escala));
    const h = Math.max(1, Math.round(img.naturalHeight * escala));
    const lienzo = el('canvas', { width: w, height: h });
    const ctx = lienzo.getContext('2d')!;
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);
    const blob = await new Promise<Blob | null>((r) => lienzo.toBlob(r, 'image/jpeg', 0.9));
    if (!blob) throw new Error('no se pudo leer la imagen');
    const doc = await PDFDocument.create();
    const jpg = await doc.embedJpg(new Uint8Array(await blob.arrayBuffer()));
    const [ancho, alto] = w > h ? [A4[1], A4[0]] : A4;
    const pagina = doc.addPage([ancho, alto]);
    const e = Math.min((ancho - 2 * MARGEN_IMAGEN) / w, (alto - 2 * MARGEN_IMAGEN) / h);
    pagina.drawImage(jpg, { x: (ancho - w * e) / 2, y: (alto - h * e) / 2, width: w * e, height: h * e });
    return doc;
  } catch (e) {
    throw new Error((e as Error).message?.startsWith('no se pudo') ? (e as Error).message : 'formato de imagen no compatible');
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function leerArchivo(archivo: File): Promise<Parte> {
  const nombre = archivo.name || 'documento';
  if (archivo.type.startsWith('image/') || /\.(jpe?g|png|heic|heif|webp|gif|bmp|tiff?)$/i.test(nombre)) {
    return { nombre, tipo: 'imagen', doc: await imagenAPdf(archivo), tam: archivo.size, paginas: null, rango: '', firmado: false };
  }
  const bytes = new Uint8Array(await archivo.arrayBuffer());
  return { nombre, tipo: 'pdf', doc: await cargarPdf(bytes), tam: bytes.length, paginas: null, rango: '', firmado: estaFirmado(bytes) };
}

function elegirArchivos(accept: string): Promise<File[]> {
  return new Promise((resolver) => {
    const entrada = el('input', { type: 'file', multiple: true, accept, style: { position: 'fixed', left: '-1000px', top: '0', opacity: '0' } }) as HTMLInputElement;
    let resuelto = false;
    entrada.addEventListener('change', () => {
      resuelto = true;
      resolver([...(entrada.files ?? [])]);
      entrada.remove();
    });
    entrada.addEventListener('cancel', () => {
      if (!resuelto) resolver([]);
      entrada.remove();
    });
    document.body.append(entrada);
    entrada.click();
  });
}

export async function combinarPartes(partes: Parte[]): Promise<Uint8Array> {
  const salida = await PDFDocument.create();
  for (const p of partes) {
    const copiadas = await salida.copyPages(p.doc, p.paginas ?? p.doc.getPageIndices());
    for (const pagina of copiadas) salida.addPage(pagina);
  }
  salida.setCreator(NOMBRE_APP);
  salida.setProducer(NOMBRE_APP);
  return salida.save();
}

const plural = (n: number, s: string) => `${n} ${n === 1 ? s : `${s}s`}`;

/** Abre la hoja «Combinar documentos». `inicial`: el documento abierto ahora, si lo hay. */
export function hojaCombinar(inicial?: { nombre: string; bytes: () => Promise<Uint8Array> }): void {
  const partes: Parte[] = [];
  const lista = el('ol.lista-combinar', { 'aria-label': 'Documentos que se van a combinar' });
  const vacio = el('div.vacio-combinar', { html: `${icono('combinar', 44)}<strong>Añade los documentos que quieres unir</strong><span>PDF o fotos (por ejemplo, el escaneo de un DNI).</span>` });
  const resumen = el('p.resumen-combinar', { 'aria-live': 'polite' });

  const pintarLista = () => {
    lista.replaceChildren();
    vacio.hidden = partes.length > 0;
    partes.forEach((p, i) => {
      const detalle = [{ pdf: 'PDF', imagen: 'Foto', abierto: 'Documento abierto' }[p.tipo], plural(p.doc.getPageCount(), 'página')];
      if (p.tam) detalle.push(tamLegible(p.tam));
      const usadas = p.paginas ? `<span class="acento">Páginas ${escapar(p.rango)} (${p.paginas.length} de ${p.doc.getPageCount()})</span>` : 'Todas las páginas';
      const aviso = p.firmado ? ' · <span class="aviso">la firma digital no se conserva</span>' : '';
      lista.append(el('li.fila-combinar', {},
        el('span.orden-combinar', { 'aria-hidden': 'true' }, String(i + 1)),
        el('button.info-combinar', {
          type: 'button', title: 'Elegir qué páginas se incluyen',
          html: `${icono(p.tipo === 'imagen' ? 'imagen' : 'pdf', 26, 'icono-pdf')}<span><strong>${escapar(p.nombre)}</strong>` +
            `<small>${detalle.join(' · ')}</small><small>${usadas}${aviso}</small></span>`,
          onclick: () => elegirPaginas(p),
        }),
        el('span.acciones-combinar', {},
          el('button.boton-icono', { type: 'button', 'aria-label': `Subir «${p.nombre}»`, html: icono('flechaArriba', 20), disabled: i === 0, onclick: () => mover(i, -1) }),
          el('button.boton-icono', { type: 'button', 'aria-label': `Bajar «${p.nombre}»`, html: icono('flechaAbajo', 20), disabled: i === partes.length - 1, onclick: () => mover(i, 1) }),
          el('button.boton-icono', { type: 'button', 'aria-label': `Quitar «${p.nombre}»`, html: icono('cerrar', 18), onclick: () => { partes.splice(i, 1); pintarLista(); } }),
        ),
      ));
    });
    const total = partes.reduce((s, p) => s + (p.paginas?.length ?? p.doc.getPageCount()), 0);
    resumen.textContent = partes.length >= 2
      ? `${plural(partes.length, 'documento')} · el resultado tendrá ${plural(total, 'página')}`
      : partes.length === 1 ? 'Añade al menos otro documento para combinarlos.' : '';
    const b = hoja.pie.querySelector<HTMLButtonElement>('#boton-combinar');
    if (b) b.disabled = partes.length < 2;
  };

  const mover = (i: number, paso: number) => {
    const j = i + paso;
    if (j < 0 || j >= partes.length) return;
    [partes[i], partes[j]] = [partes[j], partes[i]];
    pintarLista();
  };

  const elegirPaginas = (p: Parte) => {
    const n = p.doc.getPageCount();
    if (n === 1) {
      toast(`«${p.nombre}» solo tiene una página.`);
      return;
    }
    const entrada = el('input', { type: 'text', value: p.rango, placeholder: 'p. ej. 1-3, 5', autocomplete: 'off', autofocus: true, 'aria-label': 'Páginas' }) as HTMLInputElement;
    const aplicar = () => {
      const texto = entrada.value.trim();
      if (!texto) {
        p.paginas = null;
        p.rango = '';
      } else {
        try {
          p.paginas = parsearRango(texto, n);
        } catch {
          toast(`Usa números del 1 al ${n}, separados por comas o guiones.`, { tipo: 'error' });
          return false;
        }
        p.rango = texto.replace(/\s/g, '').replace(/,/g, ', ');
        if (p.paginas.length === n && p.paginas.every((x, k) => x === k)) {
          p.paginas = null;
          p.rango = '';
        }
      }
      pintarLista();
      return true;
    };
    const sub = abrirHoja({
      titulo: 'Elegir páginas',
      subtitulo: p.nombre,
      contenido: el('div.formulario', {}, campo('Páginas que se incluyen', entrada, `Tiene ${n} páginas. Déjalo vacío para incluirlas todas.`)),
      botones: [
        { texto: 'Cancelar', tipo: 'secundario' },
        { texto: 'Aplicar', tipo: 'primario', accion: aplicar },
      ],
    });
    entrada.addEventListener('keydown', (e) => { if (e.key === 'Enter' && aplicar()) sub.cerrar(); });
  };

  const anadir = async () => {
    const archivos = await elegirArchivos('application/pdf,.pdf,image/*');
    if (!archivos.length) return;
    const fin = ocupado('Leyendo…');
    const errores: string[] = [];
    try {
      await pintar();
      for (const a of archivos) {
        try {
          partes.push(await leerArchivo(a));
        } catch (e) {
          errores.push(`«${a.name}»: ${(e as Error).message}`);
        }
      }
    } finally {
      fin();
    }
    pintarLista();
    if (errores.length) toast(`No se ha podido añadir ${errores.join('; ')}.`, { tipo: 'error', segundos: 6 });
  };

  const combinar = async () => {
    if (partes.length < 2) return false;
    const fin = ocupado('Combinando…');
    try {
      await pintar();
      const bytes = await combinarPartes(partes);
      const archivo = new File([bytes as BlobPart], 'Combinado.pdf', { type: 'application/pdf' });
      document.dispatchEvent(new CustomEvent<File>(EVENTO_ABRIR, { detail: archivo }));
      return true;
    } catch (e) {
      console.error(e);
      toast(`No se han podido combinar: ${(e as Error).message}`, { tipo: 'error', segundos: 6 });
      return false;
    } finally {
      fin();
    }
  };

  const hoja = abrirHoja({
    titulo: 'Combinar documentos',
    subtitulo: 'Une varios PDF o fotos en uno nuevo. Toca uno para elegir sus páginas; usa las flechas para ordenarlos.',
    clase: 'hoja-ancha',
    contenido: [
      vacio,
      lista,
      el('button.boton.secundario.anadir-combinar', { type: 'button', html: `${icono('mas2', 20)}<span>Añadir archivos</span>`, onclick: () => void anadir() }),
      resumen,
    ],
    botones: [
      { texto: 'Cancelar', tipo: 'secundario' },
      { texto: 'Combinar', tipo: 'primario', icono: 'combinar', id: 'boton-combinar', accion: combinar },
    ],
  });

  pintarLista();
  if (inicial) {
    void (async () => {
      const fin = ocupado('Preparando el documento…');
      try {
        await pintar();
        const bytes = await inicial.bytes();
        partes.unshift({ nombre: inicial.nombre, tipo: 'abierto', doc: await cargarPdf(bytes), tam: 0, paginas: null, rango: '', firmado: estaFirmado(bytes) });
        pintarLista();
      } catch (e) {
        toast(`No se ha podido añadir el documento abierto: ${(e as Error).message}`, { tipo: 'error', segundos: 6 });
      } finally {
        fin();
      }
    })();
  }
}
