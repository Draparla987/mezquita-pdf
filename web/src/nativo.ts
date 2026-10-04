/**
 * Integración con la app nativa de iPhone (Capacitor). En el navegador no hace nada.
 *
 * - Compartir / guardar: menú del sistema (WhatsApp, Mail, AirDrop, «Guardar en Archivos»…).
 * - «Abrir en Mezquita PDF» desde Archivos, Mail, WhatsApp…: iOS copia el PDF a la carpeta
 *   Inbox de la app y nos pasa su URL file://.
 */
import { App } from '@capacitor/app';
import { Capacitor } from '@capacitor/core';
import { Directory, Filesystem } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';

export const esNativo = Capacitor.isNativePlatform();

function aBase64(bytes: Uint8Array): string {
  let binario = '';
  const trozo = 0x8000;
  for (let i = 0; i < bytes.length; i += trozo) {
    binario += String.fromCharCode(...bytes.subarray(i, i + trozo));
  }
  return btoa(binario);
}

function deBase64(texto: string): Uint8Array {
  const binario = atob(texto);
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
  return bytes;
}

function nombreSeguro(nombre: string): string {
  const limpio = nombre.replace(/[\\/:*?"<>|]+/g, '_').trim() || 'documento.pdf';
  return limpio.toLowerCase().endsWith('.pdf') ? limpio : `${limpio}.pdf`;
}

/** Abre el menú Compartir de iOS con el PDF (incluye «Guardar en Archivos»). */
export async function compartirNativo(bytes: Uint8Array, nombre: string): Promise<void> {
  const ruta = `compartir/${nombreSeguro(nombre)}`;
  const { uri } = await Filesystem.writeFile({
    path: ruta,
    data: aBase64(bytes),
    directory: Directory.Cache,
    recursive: true,
  });
  try {
    await Share.share({ title: nombre, files: [uri] });
  } catch (e) {
    // Cerrar el menú sin elegir nada no es un error.
    if (!/cancel/i.test(String((e as Error)?.message ?? e))) throw e;
  }
}

/** Escucha los PDF que otras apps abren con Mezquita PDF (incluido el arranque en frío). */
export async function escucharAperturas(abrir: (archivo: File) => void | Promise<void>): Promise<void> {
  if (!esNativo) return;
  // El mismo PDF puede llegar dos veces al arrancar (URL de inicio + copia de la parte nativa).
  let ultimo = { clave: '', t: 0 };
  const procesar = async (url: string | undefined) => {
    if (!url || !url.startsWith('file:')) return;
    try {
      const { data } = await Filesystem.readFile({ path: url });
      const bytes = typeof data === 'string' ? deBase64(data) : new Uint8Array(await data.arrayBuffer());
      const nombre = decodeURIComponent(url.split('/').pop() || 'documento.pdf');
      const clave = `${nombre}:${bytes.length}`;
      if (clave === ultimo.clave && Date.now() - ultimo.t < 5000) return;
      ultimo = { clave, t: Date.now() };
      await abrir(new File([bytes as BlobPart], nombre, { type: 'application/pdf' }));
    } catch {
      // URL de otra app sin permiso de lectura: la parte nativa ya envía una copia legible.
    }
  };
  await App.addListener('appUrlOpen', ({ url }) => void procesar(url));
  const inicio = await App.getLaunchUrl();
  await procesar(inicio?.url);
}
