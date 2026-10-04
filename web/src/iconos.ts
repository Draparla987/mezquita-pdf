/**
 * Iconos SVG en línea, de trazo, en el estilo «outline» de Material Design
 * (cuadrícula de 24 px, extremos redondeados). Sin fuentes ni dependencias externas.
 */
const RUTAS = {
  mano: '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12"/><path d="M11 11.5V4a1.5 1.5 0 0 1 3 0v7.5"/><path d="M14 11.5V5.5a1.5 1.5 0 0 1 3 0v7"/><path d="M17 9.5a1.5 1.5 0 0 1 3 0v4.5a8 8 0 0 1-8 8h-.6a7 7 0 0 1-5.5-2.7l-3.2-4.2a1.6 1.6 0 0 1 2.4-2.1L8 15"/>',
  resaltar: '<path d="m14.2 4.6 5.2 5.2-7.6 7.6H6.6v-5.2z"/><path d="M6.6 17.4 4 20h5.2"/><path d="m9.5 9.3 5.2 5.2"/>',
  texto: '<path d="M5 6.5V5h14v1.5"/><path d="M12 5v14"/><path d="M9.5 19h5"/>',
  dibujar: '<path d="M3.5 15.5c1.8-3.4 3.4-5.1 4.6-5.1 2.2 0-1.2 6.6 1.3 6.6 2 0 3.6-5.6 6-5.6 1.6 0 1.2 3.1 2.6 3.1.8 0 1.6-.6 2.5-1.6"/><path d="M4 20.5h16" opacity=".35"/>',
  rectangulo: '<rect x="4" y="6" width="16" height="12" rx="1.6"/>',
  firma: '<path d="M3 16.5c1.5 0 2.6-8.5 4.6-8.5 1.7 0-.4 9.6 1.8 9.6 1.6 0 1.9-4.6 3.3-4.6 1.2 0 .8 2.8 2.1 2.8 1 0 1.6-1.2 2.6-1.2.7 0 1.2.6 2.6.6"/><path d="M3 20.5h18"/>',
  certificado: '<path d="M13.5 3H6.5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2H11"/><path d="M13.5 3 19 8.5V10"/><path d="M13.5 3v5.5H19"/><path d="M8 12.5h4M8 16h2.5"/><circle cx="16.5" cy="15" r="3"/><path d="m15 17.6-.6 4.4 2.1-1.2 2.1 1.2-.6-4.4"/>',
  deshacer: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
  rehacer: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
  borrarUltima: '<path d="M20 20H9.2"/><path d="M5.4 16.6a2 2 0 0 1 0-2.8l8.4-8.4a2 2 0 0 1 2.8 0l3 3a2 2 0 0 1 0 2.8L12.4 18.4a2 2 0 0 1-1.4.6H8.6a2 2 0 0 1-1.4-.6z"/><path d="m9.5 9.7 4.8 4.8"/>',
  papelera: '<path d="M4 7h16"/><path d="M10 11v6M14 11v6"/><path d="m5.5 7 .9 12.2A2 2 0 0 0 8.4 21h7.2a2 2 0 0 0 2-1.8L18.5 7"/><path d="M9 7V4.5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1V7"/>',
  compartir: '<path d="M12 3.5v11"/><path d="m8 7.5 4-4 4 4"/><path d="M8.5 10.5H6.5a1.5 1.5 0 0 0-1.5 1.5v7a1.5 1.5 0 0 0 1.5 1.5h11a1.5 1.5 0 0 0 1.5-1.5v-7a1.5 1.5 0 0 0-1.5-1.5h-2"/>',
  descargar: '<path d="M12 4v11"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M5 19.5h14"/>',
  carpeta: '<path d="M3.5 18.5V6.5a2 2 0 0 1 2-2h3.8l2 2.2h7.2a2 2 0 0 1 2 2v1.2"/><path d="M3.5 18.5 6 11.6a1.8 1.8 0 0 1 1.7-1.2h12.8a1.2 1.2 0 0 1 1.1 1.6l-2.2 6.4a1.8 1.8 0 0 1-1.7 1.2H5a1.5 1.5 0 0 1-1.5-1.1z"/>',
  pdf: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M8.5 16.5v-4h1.3a1.2 1.2 0 0 1 0 2.4H8.5M12.5 16.5v-4h.9a2 2 0 0 1 0 4zM16.5 12.5h-1.6v4M14.9 14.6h1.3" stroke-width="1.3"/>',
  pluma: '<path d="M4 20h4.2L19.3 8.9a2.6 2.6 0 0 0-3.7-3.7L4.5 16.3z"/><path d="m14.2 6.6 3.7 3.7"/><path d="M13 20h7" opacity=".4"/>',
  mas: '<circle cx="5.5" cy="12" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/><circle cx="18.5" cy="12" r="1.3" fill="currentColor"/>',
  atras: '<path d="m14.5 5-7 7 7 7"/>',
  cerrar: '<path d="M6 6l12 12M18 6 6 18"/>',
  ok: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  zoomMas: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/><path d="M10.5 7.8v5.4M7.8 10.5h5.4"/>',
  zoomMenos: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/><path d="M7.8 10.5h5.4"/>',
  mas2: '<path d="M12 5v14M5 12h14"/>',
  menos: '<path d="M5 12h14"/>',
  ajustar: '<path d="M3.5 12h17"/><path d="m7 8.5-3.5 3.5L7 15.5M17 8.5l3.5 3.5-3.5 3.5"/>',
  escudo: '<path d="M12 3 4.5 6v5.6c0 4.6 3.2 8.4 7.5 9.4 4.3-1 7.5-4.8 7.5-9.4V6z"/><path d="m8.6 12.2 2.4 2.4 4.4-4.6"/>',
  escudoAlerta: '<path d="M12 3 4.5 6v5.6c0 4.6 3.2 8.4 7.5 9.4 4.3-1 7.5-4.8 7.5-9.4V6z"/><path d="M12 8v5"/><circle cx="12" cy="16" r=".6" fill="currentColor"/>',
  candado: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/><circle cx="12" cy="15.5" r="1.3"/>',
  teclado: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h.01M10.3 10h.01M13.6 10h.01M17 10h.01M7 14h.01M17 14h.01M10 14h4" stroke-width="2"/>',
  lapiz: '<path d="m15.2 5.2 3.6 3.6M4 20l1-4.4L15.6 5a1.8 1.8 0 0 1 2.6 0l1 1a1.8 1.8 0 0 1 0 2.6L8.4 19z"/>',
  ojo: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  ojoTachado: '<path d="M3.5 3.5l17 17"/><path d="M10.2 5.7A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-2.6 3.4M6.4 6.9C3.9 8.6 2.5 12 2.5 12s3.5 6.5 9.5 6.5a9 9 0 0 0 4.4-1.1"/><path d="M9.9 10a3 3 0 0 0 4.1 4.1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r=".6" fill="currentColor"/>',
  reloj: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  ajustes: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  subir: '<path d="M12 20V9"/><path d="m7.5 13.5 4.5-4.5 4.5 4.5"/><path d="M5 4.5h14"/>',
  girar: '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/>',
  mover: '<path d="M12 3v18M3 12h18"/><path d="m9 6 3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
} as const;

export type NombreIcono = keyof typeof RUTAS;

export function icono(nombre: NombreIcono, tam = 22, clase = ''): string {
  return `<svg class="icono ${clase}" width="${tam}" height="${tam}" viewBox="0 0 24 24" fill="none" ` +
    `stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ` +
    `aria-hidden="true" focusable="false">${RUTAS[nombre]}</svg>`;
}
