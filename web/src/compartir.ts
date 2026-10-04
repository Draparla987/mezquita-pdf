/** Compartir (menú del sistema: WhatsApp, Mail, AirDrop…) y descargar («Guardar en Archivos»). */
import { compartirNativo, esNativo } from './nativo';
import { abrirHoja, el, toast } from './ui/componentes';

export function descargar(bytes: Uint8Array, nombre: string): void {
  if (esNativo) {
    // En la app de iPhone no hay «descargas»: el menú Compartir incluye «Guardar en Archivos».
    void compartirNativo(bytes, nombre).catch(() => toast('No se pudo guardar el documento.', { tipo: 'error' }));
    return;
  }
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: 'application/pdf' }));
  const a = el('a', { href: url, download: nombre, style: { display: 'none' } });
  document.body.append(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Comparte con el menú del sistema (WhatsApp, Mail, AirDrop…) o, si no se puede, descarga. */
export async function compartirBytes(bytes: Uint8Array, nombre: string): Promise<void> {
  if (esNativo) {
    try {
      await compartirNativo(bytes, nombre);
    } catch (e) {
      console.error(e);
      toast('No se pudo compartir el documento.', { tipo: 'error' });
    }
    return;
  }
  const archivo = new File([bytes as BlobPart], nombre, { type: 'application/pdf' });
  const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean };
  if (nav.share && nav.canShare?.({ files: [archivo] })) {
    try {
      await nav.share({ files: [archivo] });
      return;
    } catch (e) {
      const nombreError = (e as Error).name;
      if (nombreError === 'AbortError') return;
      if (nombreError === 'NotAllowedError') {
        // Safari exige un toque reciente: se ofrece un botón para compartir ya preparado.
        abrirHoja({
          titulo: 'El documento está listo',
          subtitulo: nombre,
          botones: [
            { texto: 'Guardar en Archivos', tipo: 'secundario', icono: 'descargar', accion: () => descargar(bytes, nombre) },
            { texto: 'Compartir…', tipo: 'primario', icono: 'compartir', accion: () => void nav.share({ files: [archivo] }).catch(() => undefined) },
          ],
        });
        return;
      }
      console.warn('No se pudo compartir', e);
    }
  }
  descargar(bytes, nombre);
  toast('Este navegador no permite compartir archivos: se ha descargado el PDF.', { segundos: 5 });
}

