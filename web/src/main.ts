/**
 * Mezquita PDF (web): punto de entrada. Todo ocurre en el dispositivo: no hay servidor,
 * ni analítica, ni recursos externos. El service worker deja la app lista sin conexión.
 */
import './estilos.css';
import { registerSW } from 'virtual:pwa-register';
import * as almacen from './almacen';
import { crearBienvenida } from './bienvenida';
import type { Editor } from './editor';
import { nuevoId } from './modelo';
import { aHex, sha256 } from './pdf/util';
import { esNativo, escucharAperturas } from './nativo';
import { elegirArchivo, ocupado, pintar, toast } from './ui/componentes';

const app = document.getElementById('app')!;
let editor: Editor | null = null;
let bienvenida: (HTMLElement & { refrescar?: () => void }) | null = null;
let ignorarPop = false;

function mostrarBienvenida(): void {
  editor = null;
  if (!bienvenida) bienvenida = crearBienvenida({ abrir: () => void abrirDesdeSelector(), abrirReciente: (id) => void abrirReciente(id) });
  else bienvenida.refrescar?.();
  app.replaceChildren(bienvenida);
  document.title = 'Mezquita PDF';
}

async function mostrarEditor(d: { id: string; nombre: string; bytes: Uint8Array; anotaciones?: import('./modelo').Anotacion[] }): Promise<void> {
  // El editor (pdf.js, pdf-lib, node-forge) se carga bajo demanda: la bienvenida aparece antes.
  const { Editor } = await import('./editor');
  const ed = new Editor(() => {
    if (history.state?.pantalla === 'editor') {
      ignorarPop = true;
      history.back();
    }
    mostrarBienvenida();
  });
  app.replaceChildren(ed.elemento);
  editor = ed;
  const ok = await ed.abrir(d);
  if (!ok) {
    ed.cerrar();
    return;
  }
  document.title = `${d.nombre} · Mezquita PDF`;
  if (history.state?.pantalla !== 'editor') history.pushState({ pantalla: 'editor' }, '');
}

function esPdf(bytes: Uint8Array): boolean {
  const cabecera = String.fromCharCode(...bytes.subarray(0, Math.min(1024, bytes.length)));
  return cabecera.includes('%PDF-');
}

async function abrirArchivo(archivo: File): Promise<void> {
  const fin = ocupado('Abriendo…');
  try {
    await pintar();
    const bytes = new Uint8Array(await archivo.arrayBuffer());
    if (!esPdf(bytes)) {
      toast('Ese archivo no es un PDF.', { tipo: 'error' });
      return;
    }
    // Si es el mismo archivo que uno reciente, se reutiliza (y se recuperan sus anotaciones).
    const huella = aHex((await sha256(bytes)).subarray(0, 16));
    let previo: almacen.DocReciente | undefined;
    try {
      previo = (await almacen.recientes()).find((d) => d.huella === huella);
    } catch {
      /* sin almacenamiento */
    }
    const id = previo?.id ?? nuevoId();
    const meta: almacen.DocReciente = { ...(previo ?? {}), id, nombre: archivo.name || 'documento.pdf', tam: bytes.length, fecha: Date.now(), huella };
    try {
      await almacen.guardarDocumento(meta, previo ? undefined : bytes);
    } catch {
      toast('No hay espacio para guardarlo en Recientes, pero puedes trabajar con él.', { segundos: 4 });
    }
    fin();
    await mostrarEditor({ id, nombre: meta.nombre, bytes, anotaciones: previo?.anotaciones });
  } catch (e) {
    console.error(e);
    toast('No se pudo leer el archivo.', { tipo: 'error' });
  } finally {
    fin();
  }
}

async function abrirDesdeSelector(): Promise<void> {
  const archivo = await elegirArchivo('application/pdf,.pdf');
  if (archivo) await abrirArchivo(archivo);
}

async function abrirReciente(id: string): Promise<void> {
  const fin = ocupado('Abriendo…');
  try {
    await pintar();
    const r = await almacen.obtenerDocumento(id);
    fin();
    if (!r) {
      toast('Ese documento ya no está disponible.', { tipo: 'error' });
      bienvenida?.refrescar?.();
      return;
    }
    await almacen.guardarDocumento(r.meta).catch(() => undefined); // actualiza la fecha
    await mostrarEditor({ id, nombre: r.meta.nombre, bytes: r.bytes, anotaciones: r.meta.anotaciones });
  } finally {
    fin();
  }
}

/* --- Arrastrar y soltar (Mac) ---------------------------------------------------------- */
document.addEventListener('dragover', (e) => {
  if (e.dataTransfer?.types.includes('Files')) {
    e.preventDefault();
    document.body.classList.add('soltando');
  }
});
document.addEventListener('dragleave', (e) => {
  if (!e.relatedTarget) document.body.classList.remove('soltando');
});
document.addEventListener('drop', (e) => {
  document.body.classList.remove('soltando');
  const archivo = [...(e.dataTransfer?.files ?? [])].find((f) => f.type === 'application/pdf' || /\.pdf$/i.test(f.name));
  if (!archivo) return;
  e.preventDefault();
  if (editor) editor.cerrar();
  void abrirArchivo(archivo);
});

/* --- Navegación «atrás» ------------------------------------------------------------------ */
window.addEventListener('popstate', () => {
  if (ignorarPop) {
    ignorarPop = false;
    return;
  }
  if (editor && history.state?.pantalla !== 'editor') editor.cerrar();
});

// Evita el zoom de página de Safari: el zoom lo gestiona el visor.
document.addEventListener('gesturestart', (e) => e.preventDefault());

/* --- Service worker (sin conexión) --------------------------------------------------------- */
// En la app nativa los archivos ya van dentro de la app: no hace falta service worker.
if (!esNativo && 'serviceWorker' in navigator && import.meta.env.PROD) {
  const actualizar = registerSW({
    onNeedRefresh() {
      toast('Hay una versión nueva de Mezquita PDF.', { segundos: 20, accion: { texto: 'Actualizar', fn: () => void actualizar(true) } });
    },
    onOfflineReady() {
      toast('Mezquita PDF ya funciona sin conexión.', { tipo: 'exito' });
    },
  });
}

void almacen.pedirPersistencia();
mostrarBienvenida();
// App de iPhone: PDF abiertos desde Archivos, Mail, WhatsApp… («Abrir en Mezquita PDF»)
void escucharAperturas(async (archivo) => {
  if (editor) editor.cerrar();
  await abrirArchivo(archivo);
});
