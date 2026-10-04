/**
 * Almacenamiento local en IndexedDB (nada sale del dispositivo).
 *
 *  - documentos:  metadatos de los recientes + anotaciones pendientes
 *  - contenidos:  bytes de cada documento (separados para listar rápido)
 *  - firmas:      rúbricas manuscritas (PNG con transparencia)
 *  - certificados: archivos .p12/.pfx tal cual (ya van cifrados con su contraseña;
 *                  la contraseña NUNCA se guarda)
 *  - ajustes:     preferencias (motivo, lugar, colores…)
 *
 * Se guardan ArrayBuffer en vez de Blob por los fallos históricos de Safari con Blob.
 */
import type { Anotacion } from './modelo';

const NOMBRE_BD = 'mezquita-pdf';
const VERSION_BD = 1;
const MAX_RECIENTES = 12;

export interface DocReciente {
  id: string;
  nombre: string;
  tam: number;
  fecha: number;
  paginas?: number;
  firmado?: boolean;
  anotaciones?: Anotacion[];
  /** SHA-256 abreviado del contenido, para reconocer el mismo archivo al reabrirlo. */
  huella?: string;
}

export interface FirmaGuardada {
  id: string;
  png: string;
  ancho: number;
  alto: number;
  fecha: number;
}

export interface CertGuardado {
  id: string;
  nombreArchivo: string;
  p12: ArrayBuffer;
  titular: string;
  emisor: string;
  validoDesde: number;
  validoHasta: number;
  numeroSerie: string;
  nif?: string;
  fecha: number;
}

let bd: Promise<IDBDatabase> | null = null;

function abrir(): Promise<IDBDatabase> {
  if (bd) return bd;
  bd = new Promise((resolver, rechazar) => {
    if (!('indexedDB' in globalThis)) {
      rechazar(new Error('Este navegador no permite guardar datos (IndexedDB).'));
      return;
    }
    const pet = indexedDB.open(NOMBRE_BD, VERSION_BD);
    pet.onupgradeneeded = () => {
      const db = pet.result;
      for (const almacen of ['documentos', 'contenidos', 'firmas', 'certificados', 'ajustes']) {
        if (!db.objectStoreNames.contains(almacen)) db.createObjectStore(almacen);
      }
    };
    pet.onsuccess = () => {
      const db = pet.result;
      db.onversionchange = () => db.close();
      resolver(db);
    };
    pet.onerror = () => rechazar(pet.error);
    pet.onblocked = () => rechazar(new Error('La base de datos está bloqueada por otra pestaña.'));
  });
  bd.catch(() => { bd = null; });
  return bd;
}

function promesa<T>(pet: IDBRequest<T>): Promise<T> {
  return new Promise((resolver, rechazar) => {
    pet.onsuccess = () => resolver(pet.result);
    pet.onerror = () => rechazar(pet.error);
  });
}

async function tx<T>(almacen: string, modo: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
  const db = await abrir();
  return new Promise((resolver, rechazar) => {
    const t = db.transaction(almacen, modo);
    const s = t.objectStore(almacen);
    let resultado: T | undefined;
    const pet = fn(s);
    if (pet) pet.onsuccess = () => { resultado = pet.result; };
    t.oncomplete = () => resolver(resultado);
    t.onerror = () => rechazar(t.error);
    t.onabort = () => rechazar(t.error ?? new Error('Operación cancelada (¿sin espacio?).'));
  });
}

async function todos<T>(almacen: string): Promise<T[]> {
  const db = await abrir();
  return promesa(db.transaction(almacen, 'readonly').objectStore(almacen).getAll() as IDBRequest<T[]>);
}

/* --- Documentos recientes ------------------------------------------------------- */

export async function recientes(): Promise<DocReciente[]> {
  const docs = await todos<DocReciente>('documentos');
  return docs.sort((a, b) => b.fecha - a.fecha);
}

export async function obtenerDocumento(id: string): Promise<{ meta: DocReciente; bytes: Uint8Array } | null> {
  const meta = await tx<DocReciente>('documentos', 'readonly', (s) => s.get(id));
  const datos = await tx<ArrayBuffer>('contenidos', 'readonly', (s) => s.get(id));
  if (!meta || !datos) return null;
  return { meta, bytes: new Uint8Array(datos) };
}

export async function guardarDocumento(meta: DocReciente, bytes?: Uint8Array): Promise<void> {
  const db = await abrir();
  await new Promise<void>((resolver, rechazar) => {
    const t = db.transaction(['documentos', 'contenidos'], 'readwrite');
    t.objectStore('documentos').put({ ...meta, fecha: Date.now() }, meta.id);
    if (bytes) {
      const copia = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
      t.objectStore('contenidos').put(copia, meta.id);
    }
    t.oncomplete = () => resolver();
    t.onerror = () => rechazar(t.error);
    t.onabort = () => rechazar(t.error ?? new Error('No hay espacio suficiente para guardar el documento.'));
  });
  await recortarRecientes();
}

export async function guardarAnotaciones(id: string, anotaciones: Anotacion[]): Promise<void> {
  const meta = await tx<DocReciente>('documentos', 'readonly', (s) => s.get(id));
  if (!meta) return;
  await tx('documentos', 'readwrite', (s) => s.put({ ...meta, anotaciones }, id));
}

export async function borrarDocumento(id: string): Promise<void> {
  const db = await abrir();
  await new Promise<void>((resolver, rechazar) => {
    const t = db.transaction(['documentos', 'contenidos'], 'readwrite');
    t.objectStore('documentos').delete(id);
    t.objectStore('contenidos').delete(id);
    t.oncomplete = () => resolver();
    t.onerror = () => rechazar(t.error);
  });
}

async function recortarRecientes(): Promise<void> {
  const docs = await recientes();
  for (const d of docs.slice(MAX_RECIENTES)) await borrarDocumento(d.id);
}

/* --- Firmas manuscritas ------------------------------------------------------------ */

export async function firmas(): Promise<FirmaGuardada[]> {
  return (await todos<FirmaGuardada>('firmas')).sort((a, b) => b.fecha - a.fecha);
}
export async function guardarFirma(f: FirmaGuardada): Promise<void> {
  await tx('firmas', 'readwrite', (s) => s.put(f, f.id));
}
export async function borrarFirma(id: string): Promise<void> {
  await tx('firmas', 'readwrite', (s) => s.delete(id));
}

/* --- Certificados ---------------------------------------------------------------- */

export async function certificados(): Promise<CertGuardado[]> {
  return (await todos<CertGuardado>('certificados')).sort((a, b) => b.fecha - a.fecha);
}
export async function guardarCertificado(c: CertGuardado): Promise<void> {
  await tx('certificados', 'readwrite', (s) => s.put(c, c.id));
}
export async function borrarCertificado(id: string): Promise<void> {
  await tx('certificados', 'readwrite', (s) => s.delete(id));
}

/* --- Ajustes --------------------------------------------------------------------- */

export async function ajuste<T>(clave: string, porDefecto: T): Promise<T> {
  try {
    const v = await tx<T>('ajustes', 'readonly', (s) => s.get(clave));
    return v === undefined ? porDefecto : v;
  } catch {
    return porDefecto;
  }
}
export async function fijarAjuste<T>(clave: string, valor: T): Promise<void> {
  try {
    await tx('ajustes', 'readwrite', (s) => s.put(valor, clave));
  } catch {
    /* sin almacenamiento: se ignora */
  }
}

/** Pide al navegador que no borre los datos si falta espacio (Safari 17+, Chrome…). */
export async function pedirPersistencia(): Promise<void> {
  try {
    if (navigator.storage?.persist && !(await navigator.storage.persisted())) await navigator.storage.persist();
  } catch {
    /* no disponible */
  }
}
