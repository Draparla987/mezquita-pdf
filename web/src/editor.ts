/**
 * Pantalla del editor: barra superior, barra de herramientas (inferior en el móvil,
 * lateral en pantallas anchas), visor de páginas, capa de anotaciones, deshacer/rehacer,
 * compartir y firma.
 */
import * as almacen from './almacen';
import type { FirmaGuardada } from './almacen';
import { type ContextoCapa, CapaAnotaciones, type Herramienta } from './capa';
import { flujoFirmaDigital, hojaCertificados, hojaFirmasDocumento } from './firma-digital-ui';
import { icono, type NombreIcono } from './iconos';
import { type Anotacion, type AnotTexto, nuevoId } from './modelo';
import { elegirFirma } from './pad-firma';
import { aplicarAnotaciones } from './pdf/anotaciones-pdf';
import { compartirBytes, descargar } from './compartir';
import { type EstadoFirma, pareceFirmado, verificarFirmas } from './pdf/verificar';
import { COLORES_RESALTADO, COLORES_TRAZO } from './tema';
import {
  abrirHoja, abrirMenu, el, escapar, esMovil, ocupado, pedirContrasena, pintar, toast,
} from './ui/componentes';
import { ErrorContrasena, Visor } from './visor';

export interface DocumentoParaAbrir {
  id: string;
  nombre: string;
  bytes: Uint8Array;
  anotaciones?: Anotacion[];
}

interface DefHerramienta {
  id: Herramienta | 'deshacer' | 'rehacer' | 'borrarUltima' | 'certificado' | 'sep';
  texto: string;
  icono?: NombreIcono;
  consejo?: string;
  soloEscritorio?: boolean;
}

const HERRAMIENTAS: DefHerramienta[] = [
  { id: 'mano', texto: 'Mano', icono: 'mano', consejo: 'Desplazar y seleccionar anotaciones (Esc)' },
  { id: 'sep', texto: '' },
  { id: 'resaltar', texto: 'Resaltar', icono: 'resaltar', consejo: 'Arrastra sobre el texto para resaltarlo' },
  { id: 'texto', texto: 'Texto', icono: 'texto', consejo: 'Toca donde quieras escribir' },
  { id: 'dibujar', texto: 'Dibujar', icono: 'dibujar', consejo: 'Dibujo a mano alzada' },
  { id: 'rectangulo', texto: 'Rectángulo', icono: 'rectangulo', consejo: 'Arrastra para dibujar un rectángulo' },
  { id: 'sep', texto: '' },
  { id: 'firma', texto: 'Firma', icono: 'firma', consejo: 'Colocar tu firma manuscrita' },
  { id: 'certificado', texto: 'Certificado', icono: 'certificado', consejo: 'Firmar con certificado digital', soloEscritorio: true },
  { id: 'sep', texto: '' },
  { id: 'deshacer', texto: 'Deshacer', icono: 'deshacer', consejo: 'Deshacer (⌘Z)' },
  { id: 'rehacer', texto: 'Rehacer', icono: 'rehacer', consejo: 'Rehacer (⇧⌘Z)' },
  { id: 'borrarUltima', texto: 'Borrar última', icono: 'borrarUltima', consejo: 'Borrar la última anotación' },
];

const NOMBRES: Record<Herramienta, string> = {
  mano: 'Mano', resaltar: 'Resaltar', texto: 'Texto', dibujar: 'Dibujar', rectangulo: 'Rectángulo',
  firma: 'Firma', cajaFirma: 'Sello de la firma digital',
};
const PISTAS: Partial<Record<Herramienta, string>> = {
  resaltar: 'Arrastra sobre el texto',
  texto: 'Toca donde quieras escribir',
  dibujar: 'Dibuja con el dedo o el Pencil',
  rectangulo: 'Arrastra para dibujar',
  firma: 'Toca donde quieras firmar',
  cajaFirma: 'Arrastra para dibujar el recuadro del sello',
};

function estaCifrado(bytes: Uint8Array): boolean {
  // Busca «/Encrypt» en el tráiler (últimos 64 KB) o en todo el archivo si es pequeño.
  const desde = bytes.length > 4_000_000 ? bytes.length - 65536 : 0;
  const p = [0x2f, 0x45, 0x6e, 0x63, 0x72, 0x79, 0x70, 0x74];
  externo: for (let i = desde; i <= bytes.length - p.length; i++) {
    for (let j = 0; j < p.length; j++) if (bytes[i + j] !== p[j]) continue externo;
    return true;
  }
  return false;
}

export class Editor {
  readonly elemento: HTMLElement;
  readonly visor: Visor;
  private capa: CapaAnotaciones;
  private alCerrar: () => void;

  // Documento
  id = '';
  nombre = '';
  bytes: Uint8Array = new Uint8Array();
  private cifrado = false;
  firmas: EstadoFirma[] = [];

  // Anotaciones e historial
  anotaciones: Anotacion[] = [];
  private historial: Anotacion[][] = [[]];
  private posHistorial = 0;
  private seleccionId: string | null = null;
  private antesDeCambio: Anotacion[] | null = null;
  private avisoFirmadoMostrado = false;

  // Herramientas
  herramienta: Herramienta = 'mano';
  private colores: Record<string, string> = { resaltar: COLORES_RESALTADO[0], dibujar: COLORES_TRAZO[1], rectangulo: COLORES_TRAZO[2], texto: '#111111' };
  private grosores: Record<string, number> = { dibujar: 2.5, rectangulo: 2 };
  private tamTexto = 14;
  private firmaActual: FirmaGuardada | null = null;
  private alCajaFirma: ((pagina: number, caja: { x: number; y: number; w: number; h: number }) => void) | null = null;
  aplanar = true;

  // Exportación
  private cache: { anots: Anotacion[]; aplanar: boolean; base: Uint8Array; bytes: Uint8Array } | null = null;
  private temporizadorGuardado = 0;
  private temporizadorExport = 0;

  // Elementos
  private elNombre!: HTMLElement;
  private elInfo!: HTMLElement;
  private elZoom!: HTMLElement;
  private elIndicador!: HTMLElement;
  private elPildora!: HTMLElement;
  private elAviso!: HTMLElement;
  private elBarra!: HTMLElement;
  private botonesHerr = new Map<string, HTMLButtonElement>();
  private teclas = (e: KeyboardEvent) => this.teclado(e);

  constructor(alCerrar: () => void) {
    this.alCerrar = alCerrar;
    this.elemento = el('section.pantalla-editor', { 'aria-label': 'Editor de PDF' });
    const raizVisor = el('main.visor', { tabindex: '-1', 'data-herramienta': 'mano' });
    this.visor = new Visor(raizVisor, {
      alCambiarPagina: (n, total) => this.actualizarIndicador(n, total),
      alCambiarZoom: (z) => { this.elZoom.textContent = `${Math.round(z * 75)} %`; },
      alCrearPagina: (p) => this.capa.prepararPagina(p),
      alPellizcar: () => this.capa.cancelar(),
    });
    this.capa = new CapaAnotaciones(this.contextoCapa());
    this.construir(raizVisor);
    void almacen.ajuste('aplanar', true).then((v) => { this.aplanar = v; });
    void almacen.ajuste<Record<string, string> | null>('colores', null).then((v) => { if (v) Object.assign(this.colores, v); });
    void almacen.ajuste<string | null>('firmaActual', null).then(async (id) => {
      if (!id) return;
      const lista = await almacen.firmas().catch(() => []);
      this.firmaActual = lista.find((f) => f.id === id) ?? null;
    });
    document.addEventListener('keydown', this.teclas);
  }

  /* ------------------------------------------------------------------------ */
  /* Construcción de la interfaz                                               */
  /* ------------------------------------------------------------------------ */

  private construir(raizVisor: HTMLElement): void {
    const volver = el('button.boton-icono.volver', { type: 'button', 'aria-label': 'Volver al inicio', title: 'Inicio', html: icono('atras', 24), onclick: () => this.cerrar() });
    const marca = el('div.marca-barra', {}, el('img', { src: './icons/logo-256.png', alt: '', width: '26', height: '26' }), el('span.nombre-app', {}, 'Mezquita PDF'), el('span.separador-v'));
    this.elNombre = el('span.nombre-doc');
    this.elInfo = el('span.info-doc');
    const titulo = el('div.titulo-doc', {}, this.elNombre, this.elInfo);
    this.elZoom = el('span.valor-zoom', {}, '100 %');
    const zoom = el('div.grupo-zoom', {},
      el('button.boton-icono', { type: 'button', 'aria-label': 'Reducir', title: 'Reducir (⌘−)', html: icono('zoomMenos', 21), onclick: () => this.visor.ampliar(1 / 1.2) }),
      el('button.valor-zoom-boton', { type: 'button', title: 'Ajustar al ancho', onclick: () => this.visor.ajustarAncho() }, this.elZoom),
      el('button.boton-icono', { type: 'button', 'aria-label': 'Ampliar', title: 'Ampliar (⌘+)', html: icono('zoomMas', 21), onclick: () => this.visor.ampliar(1.2) }),
      el('button.boton-icono', { type: 'button', 'aria-label': 'Ajustar a la página', title: 'Ajustar a la página', html: icono('ajustar', 21), onclick: () => this.visor.ajustarPagina() }),
    );
    const compartir = el('button.boton.secundario.boton-compartir', { type: 'button', title: 'Compartir el PDF', html: `${icono('compartir', 20)}<span>Compartir</span>`, onclick: () => void this.compartir() });
    const firmar = el('button.boton.primario.boton-firmar', { type: 'button', title: 'Firmar el documento', html: `${icono('pluma', 20)}<span>Firmar</span>`, onclick: () => this.menuFirmar() });
    const mas = el('button.boton-icono.boton-mas', { type: 'button', 'aria-label': 'Más opciones', title: 'Más opciones', html: icono('mas', 24) });
    mas.addEventListener('click', () => this.menuMas(mas));
    const cabecera = el('header.barra-superior', {}, volver, marca, titulo, zoom, compartir, firmar, mas);

    // Barra de herramientas
    this.elBarra = el('nav.barra-herramientas', { 'aria-label': 'Herramientas' });
    const lista = el('div.lista-herramientas', { role: 'toolbar' });
    for (const d of HERRAMIENTAS) {
      if (d.id === 'sep') {
        lista.append(el('span.separador-herr', { 'aria-hidden': 'true' }));
        continue;
      }
      const esHerr = !['deshacer', 'rehacer', 'borrarUltima', 'certificado'].includes(d.id);
      const b = el('button.boton-herr', {
        type: 'button', title: d.consejo ?? d.texto, 'aria-label': d.texto,
        html: `${icono(d.icono!, 23)}<span>${d.texto}</span>`,
        onclick: () => this.pulsarHerramienta(d.id as string),
      });
      if (esHerr) b.setAttribute('aria-pressed', 'false');
      if (d.soloEscritorio) b.classList.add('solo-escritorio');
      this.botonesHerr.set(d.id, b);
      lista.append(b);
    }
    this.elBarra.append(lista);

    this.elIndicador = el('div.indicador-pagina', {},
      el('button.boton-icono.pequeno', { type: 'button', 'aria-label': 'Reducir', html: icono('menos', 18), onclick: () => this.visor.ampliar(1 / 1.25) }),
      el('button.texto-pagina', { type: 'button', 'aria-label': 'Ir a una página', onclick: () => this.irAPagina() }, '1 / 1'),
      el('button.boton-icono.pequeno', { type: 'button', 'aria-label': 'Ampliar', html: icono('mas2', 18), onclick: () => this.visor.ampliar(1.25) }),
    );
    this.elPildora = el('div.pildora', { role: 'toolbar', 'aria-label': 'Opciones de la herramienta', hidden: true });
    this.elAviso = el('button.aviso-firmas', { type: 'button', hidden: true, onclick: () => hojaFirmasDocumento(this.firmas) });
    const zonaVisor = el('div.zona-visor', {}, raizVisor, this.elAviso, this.elPildora, this.elIndicador);
    this.elemento.append(el('div.franja-estado', { 'aria-hidden': 'true' }), cabecera, this.elBarra, zonaVisor);
    this.marcarHerramienta();
  }

  /* ------------------------------------------------------------------------ */
  /* Documento                                                                 */
  /* ------------------------------------------------------------------------ */

  async abrir(d: DocumentoParaAbrir): Promise<boolean> {
    this.id = d.id;
    this.nombre = d.nombre;
    this.bytes = d.bytes;
    this.cifrado = false;
    this.firmas = [];
    this.cache = null;
    this.seleccionId = null;
    this.capa.reiniciar();
    try {
      await this.visor.abrir(d.bytes);
    } catch (e) {
      if (!(e instanceof ErrorContrasena)) {
        console.error(e);
        toast('No se pudo abrir el PDF: el archivo está dañado o no es un PDF.', { tipo: 'error', segundos: 5 });
        return false;
      }
      this.cifrado = true;
      let abierto = false;
      await pedirContrasena({
        titulo: 'Documento protegido',
        mensaje: `«${d.nombre}» está protegido con contraseña.`,
        textoBoton: 'Abrir',
        validar: async (c) => {
          try {
            await this.visor.abrir(d.bytes, c);
            abierto = true;
            return null;
          } catch (e2) {
            return e2 instanceof ErrorContrasena ? 'La contraseña no es correcta. Inténtalo de nuevo.' : 'No se pudo abrir el PDF.';
          }
        },
      });
      if (!abierto) return false;
    }
    this.cifrado ||= estaCifrado(d.bytes);
    this.elNombre.textContent = d.nombre;
    this.elNombre.title = d.nombre;
    this.historial = [d.anotaciones ?? []];
    this.posHistorial = 0;
    this.anotaciones = this.historial[0];
    this.avisoFirmadoMostrado = false;
    this.capa.dibujar();
    this.setHerramienta('mano');
    this.actualizarInfo();
    this.actualizarBotones();
    if (d.anotaciones?.length) toast(`Se han recuperado ${d.anotaciones.length} anotación(es) sin compartir.`);
    if (this.cifrado) toast('Documento protegido: puedes verlo, pero no modificarlo ni firmarlo.', { segundos: 5 });
    void this.comprobarFirmas();
    return true;
  }

  private actualizarInfo(): void {
    const n = this.visor.total;
    const partes = [`${n} ${n === 1 ? 'página' : 'páginas'}`];
    if (this.firmas.length) partes.push(this.firmas.length === 1 ? 'firmado' : `${this.firmas.length} firmas`);
    if (this.anotaciones.length) partes.push(`${this.anotaciones.length} ${this.anotaciones.length === 1 ? 'anotación' : 'anotaciones'}`);
    this.elInfo.textContent = partes.join(' · ');
  }

  private async comprobarFirmas(): Promise<void> {
    this.elAviso.hidden = true;
    if (this.cifrado || !pareceFirmado(this.bytes)) return;
    try {
      this.firmas = await verificarFirmas(this.bytes);
    } catch (e) {
      console.warn('No se pudieron comprobar las firmas', e);
      this.firmas = [];
    }
    this.actualizarInfo();
    if (!this.firmas.length) return;
    const todasBien = this.firmas.every((f) => f.integra);
    const ultimo = this.firmas[this.firmas.length - 1];
    this.elAviso.className = `aviso-firmas ${todasBien ? 'bien' : 'mal'}`;
    this.elAviso.innerHTML = `${icono(todasBien ? 'escudo' : 'escudoAlerta', 20)}<span>${todasBien
      ? `Firmado digitalmente por <strong>${escapar(ultimo.firmante)}</strong>${this.firmas.length > 1 ? ` y ${this.firmas.length - 1} más` : ''}`
      : 'Alguna firma digital <strong>no es válida</strong>'}</span><span class="aviso-detalle">Detalles</span>`;
    this.elAviso.hidden = false;
  }

  /** Sustituye el documento (p. ej., tras firmarlo) y lo guarda en recientes. */
  async reemplazarDocumento(bytes: Uint8Array, nombre: string): Promise<void> {
    const id = nuevoId();
    try {
      await almacen.guardarDocumento({ id, nombre, tam: bytes.length, fecha: Date.now(), firmado: true }, bytes);
    } catch {
      toast('No hay espacio para guardar el documento en Recientes.', { tipo: 'error' });
    }
    const zoom = this.visor.zoom;
    const pagina = this.visor.pagina;
    const scroll = { x: this.visor.raiz.scrollLeft, y: this.visor.raiz.scrollTop };
    await this.abrir({ id, nombre, bytes, anotaciones: [] });
    this.visor.setZoom(zoom);
    this.visor.irAPagina(pagina);
    this.visor.raiz.scrollLeft = scroll.x;
    this.visor.raiz.scrollTop = scroll.y;
  }

  nombreArchivo(): string {
    return this.nombre.toLowerCase().endsWith('.pdf') ? this.nombre : `${this.nombre}.pdf`;
  }

  /** Bytes del PDF con las anotaciones aplicadas (actualización incremental). */
  async bytesParaGuardar(): Promise<Uint8Array> {
    if (!this.anotaciones.length) return this.bytes;
    if (this.cifrado) throw new Error('El documento está protegido con contraseña: no se puede modificar desde la web.');
    const aplanar = this.aplanar && this.firmas.length === 0;
    const c = this.cache;
    if (c && c.anots === this.anotaciones && c.aplanar === aplanar && c.base === this.bytes) return c.bytes;
    const anots = this.anotaciones;
    const base = this.bytes;
    const bytes = await aplicarAnotaciones(base, anots, { aplanar });
    this.cache = { anots, aplanar, base, bytes };
    return bytes;
  }

  private exportListo(): boolean {
    if (!this.anotaciones.length) return true;
    const c = this.cache;
    return !!c && c.anots === this.anotaciones && c.base === this.bytes && c.aplanar === (this.aplanar && this.firmas.length === 0);
  }

  /* ------------------------------------------------------------------------ */
  /* Compartir y guardar                                                       */
  /* ------------------------------------------------------------------------ */

  async compartir(): Promise<void> {
    let bytes: Uint8Array;
    if (this.exportListo()) {
      // Sin ningún «await» antes de navigator.share: Safari exige que se llame
      // directamente desde el toque del usuario.
      void compartirBytes(this.anotaciones.length ? this.cache!.bytes : this.bytes, this.nombreArchivo());
      return;
    } else {
      const fin = ocupado('Preparando el documento…');
      try {
        await pintar();
        bytes = await this.bytesParaGuardar();
      } catch (e) {
        toast((e as Error).message, { tipo: 'error', segundos: 5 });
        return;
      } finally {
        fin();
      }
    }
    await compartirBytes(bytes, this.nombreArchivo());
  }

  async guardarEnArchivos(): Promise<void> {
    const fin = ocupado('Preparando el documento…');
    try {
      await pintar();
      const bytes = await this.bytesParaGuardar();
      descargar(bytes, this.nombreArchivo());
      toast('Documento descargado. En el iPhone lo encontrarás en Archivos › Descargas.', { segundos: 5 });
    } catch (e) {
      toast((e as Error).message, { tipo: 'error', segundos: 5 });
    } finally {
      fin();
    }
  }

  /* ------------------------------------------------------------------------ */
  /* Herramientas                                                              */
  /* ------------------------------------------------------------------------ */

  private pulsarHerramienta(id: string): void {
    switch (id) {
      case 'deshacer': return this.deshacer();
      case 'rehacer': return this.rehacer();
      case 'borrarUltima': return this.borrarUltima();
      case 'certificado': return void this.firmarConCertificado();
      case 'firma': return void this.usarFirmaManuscrita();
      default: this.setHerramienta(this.herramienta === id && id !== 'mano' ? 'mano' : (id as Herramienta));
    }
  }

  setHerramienta(h: Herramienta): void {
    if (h !== 'mano' && h !== 'cajaFirma' && !this.editable()) {
      this.avisoNoEditable();
      h = 'mano';
    }
    if (h !== 'cajaFirma') this.alCajaFirma = null;
    this.capa.cancelar();
    this.herramienta = h;
    this.visor.raiz.dataset.herramienta = h;
    this.marcarHerramienta();
    this.actualizarPildora();
  }

  private marcarHerramienta(): void {
    for (const [id, b] of this.botonesHerr) {
      if (b.hasAttribute('aria-pressed')) b.setAttribute('aria-pressed', String(id === this.herramienta));
    }
  }

  private actualizarBotones(): void {
    const sin = (id: string, v: boolean) => { const b = this.botonesHerr.get(id); if (b) b.disabled = v; };
    sin('deshacer', this.posHistorial === 0);
    sin('rehacer', this.posHistorial >= this.historial.length - 1);
    sin('borrarUltima', this.anotaciones.length === 0);
  }

  editable(): boolean {
    return !this.cifrado;
  }

  avisoNoEditable(): void {
    toast('Este PDF está protegido con contraseña: se puede ver, pero no modificar ni firmar.', { tipo: 'error', segundos: 4 });
  }

  private color(): string {
    return this.colores[this.herramienta] ?? COLORES_TRAZO[0];
  }

  private grosor(): number {
    return this.grosores[this.herramienta] ?? 2;
  }

  private actualizarPildora(): void {
    const h = this.herramienta;
    const p = this.elPildora;
    p.replaceChildren();
    if (h === 'mano') {
      p.hidden = true;
      return;
    }
    p.hidden = false;
    const ico: NombreIcono = h === 'cajaFirma' ? 'certificado' : (HERRAMIENTAS.find((d) => d.id === h)?.icono ?? 'mano');
    p.append(el('span.pildora-titulo', { html: `${icono(ico, 19)}<strong>${NOMBRES[h]}</strong>` }));
    if (PISTAS[h] && !esMovil()) p.append(el('span.pildora-pista', {}, PISTAS[h]!));
    if (['resaltar', 'dibujar', 'rectangulo', 'texto'].includes(h)) {
      p.append(el('span.separador-v'));
      const colores = el('div.pildora-colores', { role: 'radiogroup', 'aria-label': 'Color' });
      for (const c of h === 'resaltar' ? COLORES_RESALTADO : h === 'texto' ? ['#111111', ...COLORES_TRAZO.slice(0, 3)] : COLORES_TRAZO) {
        colores.append(el('button.muestra-color', {
          type: 'button', role: 'radio', 'aria-label': `Color ${c}`, 'aria-checked': String(c.toUpperCase() === this.color().toUpperCase()),
          style: { '--color': c } as never,
          onclick: (ev: Event) => {
            this.colores[h] = c;
            void almacen.fijarAjuste('colores', this.colores);
            colores.querySelectorAll('button').forEach((b) => b.setAttribute('aria-checked', String(b === ev.currentTarget)));
          },
        }));
      }
      p.append(colores);
    }
    if (h === 'dibujar' || h === 'rectangulo' || h === 'texto') {
      p.append(el('span.separador-v'));
      const esTexto = h === 'texto';
      const valor = el('span.pildora-valor', {}, esTexto ? `${this.tamTexto} pt` : `${this.grosor()} pt`);
      const deslizador = el('input', {
        type: 'range', min: esTexto ? '8' : '1', max: esTexto ? '48' : '12', step: esTexto ? '1' : '0.5',
        value: String(esTexto ? this.tamTexto : this.grosor()), 'aria-label': esTexto ? 'Tamaño del texto' : 'Grosor',
      }) as HTMLInputElement;
      deslizador.addEventListener('input', () => {
        const v = Number(deslizador.value);
        if (esTexto) this.tamTexto = v; else this.grosores[h] = v;
        valor.textContent = `${v} pt`;
      });
      p.append(el('label.pildora-grosor', {}, el('span.etiqueta-corta', {}, esTexto ? 'Tamaño' : 'Grosor'), deslizador, valor));
    }
    if (h === 'firma' && this.firmaActual) {
      p.append(el('span.separador-v'), el('img.miniatura-firma', { src: this.firmaActual.png, alt: 'Firma actual' }),
        el('button.boton.texto.pequeno', { type: 'button', onclick: () => void this.usarFirmaManuscrita(true) }, 'Cambiar'));
    }
    if (h === 'cajaFirma' && esMovil()) p.append(el('span.pildora-pista', {}, PISTAS.cajaFirma!));
    p.append(el('button.boton-icono.pequeno.pildora-cerrar', {
      type: 'button', 'aria-label': h === 'cajaFirma' ? 'Cancelar la firma' : 'Terminar', title: 'Terminar (Esc)', html: icono('cerrar', 18),
      onclick: () => this.setHerramienta('mano'),
    }));
  }

  /* ------------------------------------------------------------------------ */
  /* Anotaciones e historial                                                   */
  /* ------------------------------------------------------------------------ */

  private confirmar(nuevas: Anotacion[]): void {
    this.historial = this.historial.slice(0, this.posHistorial + 1);
    this.historial.push(nuevas);
    if (this.historial.length > 200) this.historial.shift();
    this.posHistorial = this.historial.length - 1;
    this.establecer(nuevas);
  }

  private establecer(lista: Anotacion[], pagina?: number): void {
    const anteriores = this.anotaciones;
    this.anotaciones = lista;
    if (this.seleccionId && !lista.some((a) => a.id === this.seleccionId)) this.seleccionId = null;
    // Redibuja solo las páginas afectadas.
    const paginas = new Set<number>();
    if (pagina !== undefined) paginas.add(pagina);
    else {
      const ids = new Map(anteriores.map((a) => [a.id, a]));
      for (const a of lista) if (ids.get(a.id) !== a) paginas.add(a.pagina);
      const nuevos = new Set(lista.map((a) => a.id));
      for (const a of anteriores) if (!nuevos.has(a.id) || lista.find((b) => b.id === a.id) !== a) paginas.add(a.pagina);
    }
    for (const p of paginas) this.capa.dibujar(p);
    this.capa.dibujarSeleccion();
    this.actualizarBotones();
    this.actualizarInfo();
    this.programarGuardado();
  }

  private programarGuardado(): void {
    window.clearTimeout(this.temporizadorGuardado);
    this.temporizadorGuardado = window.setTimeout(() => {
      void almacen.guardarAnotaciones(this.id, this.anotaciones).catch(() => undefined);
    }, 700);
    // Prepara el PDF en segundo plano para que «Compartir» sea inmediato
    // (Safari exige que navigator.share se llame justo tras el toque).
    window.clearTimeout(this.temporizadorExport);
    if (this.anotaciones.length && this.bytes.length < 30_000_000 && !this.cifrado) {
      this.temporizadorExport = window.setTimeout(() => void this.bytesParaGuardar().catch(() => undefined), 1500);
    }
  }

  private anadir(a: Anotacion): void {
    if (this.firmas.length && !this.avisoFirmadoMostrado) {
      this.avisoFirmadoMostrado = true;
      toast('Documento firmado: las anotaciones se añadirán sin invalidar las firmas, como cambios posteriores.', { segundos: 6 });
    }
    this.confirmar([...this.anotaciones, a]);
  }

  deshacer(): void {
    if (this.posHistorial === 0) return;
    this.posHistorial--;
    this.establecer(this.historial[this.posHistorial]);
  }

  rehacer(): void {
    if (this.posHistorial >= this.historial.length - 1) return;
    this.posHistorial++;
    this.establecer(this.historial[this.posHistorial]);
  }

  borrarUltima(): void {
    if (!this.anotaciones.length) return;
    this.confirmar(this.anotaciones.slice(0, -1));
    toast('Anotación eliminada', { accion: { texto: 'Deshacer', fn: () => this.deshacer() } });
  }

  private seleccionar(id: string | null): void {
    this.seleccionId = id;
    this.capa.dibujarSeleccion();
  }

  private eliminar(id: string): void {
    this.confirmar(this.anotaciones.filter((a) => a.id !== id));
  }

  private contextoCapa(): ContextoCapa {
    return {
      visor: this.visor,
      herramienta: () => this.herramienta,
      anotaciones: () => this.anotaciones,
      seleccion: () => this.seleccionId,
      seleccionar: (id) => this.seleccionar(id),
      anadir: (a) => this.anadir(a),
      reemplazar: (a, historial) => {
        const lista = this.anotaciones.map((x) => (x.id === a.id ? a : x));
        if (historial) this.confirmar(lista);
        else this.establecer(lista, a.pagina);
      },
      inicioCambio: () => { this.antesDeCambio = this.anotaciones; },
      finCambio: () => {
        if (this.antesDeCambio && this.anotaciones !== this.antesDeCambio) {
          const actual = this.anotaciones;
          this.historial = this.historial.slice(0, this.posHistorial + 1);
          this.historial.push(actual);
          this.posHistorial = this.historial.length - 1;
          this.actualizarBotones();
        }
        this.antesDeCambio = null;
      },
      eliminar: (id) => this.eliminar(id),
      editarTexto: (a) => this.dialogoTexto(a.pagina, a.x, a.y, a),
      color: () => this.color(),
      grosor: () => this.grosor(),
      textoEn: (pagina, x, y) => this.dialogoTexto(pagina, x, y),
      firmaEn: (pagina, x, y) => this.colocarFirma(pagina, x, y),
      cajaFirmaLista: (pagina, caja) => {
        const fn = this.alCajaFirma;
        this.setHerramienta('mano');
        fn?.(pagina, caja);
      },
      editable: () => this.editable(),
      avisoNoEditable: () => this.avisoNoEditable(),
    };
  }

  private dialogoTexto(pagina: number, x: number, y: number, existente?: AnotTexto): void {
    const area = el('textarea', { rows: '3', placeholder: 'Escribe el texto…', 'aria-label': 'Texto', autofocus: true }) as HTMLTextAreaElement;
    area.value = existente?.texto ?? '';
    let tam = existente?.tam ?? this.tamTexto;
    let color = existente?.color ?? this.colores.texto;
    const valor = el('span.pildora-valor', {}, `${tam} pt`);
    const deslizador = el('input', { type: 'range', min: '8', max: '48', step: '1', value: String(tam), 'aria-label': 'Tamaño' }) as HTMLInputElement;
    deslizador.addEventListener('input', () => { tam = Number(deslizador.value); valor.textContent = `${tam} pt`; });
    const colores = el('div.pildora-colores', { role: 'radiogroup', 'aria-label': 'Color' });
    for (const c of ['#111111', ...COLORES_TRAZO.slice(0, 3)]) {
      colores.append(el('button.muestra-color', {
        type: 'button', role: 'radio', 'aria-checked': String(c === color), 'aria-label': `Color ${c}`, style: { '--color': c } as never,
        onclick: (ev: Event) => { color = c; colores.querySelectorAll('button').forEach((b) => b.setAttribute('aria-checked', String(b === ev.currentTarget))); },
      }));
    }
    abrirHoja({
      titulo: existente ? 'Editar texto' : 'Añadir texto',
      contenido: el('div.formulario', {}, area,
        el('div.fila-opciones', {}, el('label.pildora-grosor', {}, el('span.etiqueta-corta', {}, 'Tamaño'), deslizador, valor), colores)),
      botones: [
        ...(existente ? [{ texto: 'Eliminar', tipo: 'peligro' as const, accion: () => this.eliminar(existente.id) }] : []),
        { texto: 'Cancelar', tipo: 'secundario' },
        {
          texto: existente ? 'Guardar' : 'Añadir', tipo: 'primario',
          accion: () => {
            const texto = area.value.replace(/\s+$/, '');
            if (!texto.trim()) {
              if (existente) this.eliminar(existente.id);
              return;
            }
            this.tamTexto = tam;
            this.colores.texto = color;
            if (existente) {
              const a: AnotTexto = { ...existente, texto, tam, color };
              this.confirmar(this.anotaciones.map((z) => (z.id === a.id ? a : z)));
            } else {
              const p = this.visor.paginas[pagina];
              const a: AnotTexto = { id: nuevoId(), pagina, tipo: 'texto', x: Math.min(x, p.ancho - 20), y: Math.max(0, y - tam * 0.6), texto, tam, color };
              this.anadir(a);
              this.seleccionar(a.id);
            }
          },
        },
      ],
    });
    window.setTimeout(() => area.focus(), 260);
  }

  /* ------------------------------------------------------------------------ */
  /* Firma manuscrita                                                          */
  /* ------------------------------------------------------------------------ */

  private async usarFirmaManuscrita(cambiar = false): Promise<void> {
    if (!this.editable()) return this.avisoNoEditable();
    if (!this.firmaActual || cambiar) {
      const f = await elegirFirma('Elige tu firma');
      if (!f) return;
      this.firmaActual = f;
      void almacen.fijarAjuste('firmaActual', f.id);
    }
    this.setHerramienta('firma');
    toast('Toca en la página donde quieras colocar la firma.');
  }

  private colocarFirma(pagina: number, x: number, y: number): void {
    const f = this.firmaActual;
    const p = this.visor.paginas[pagina];
    if (!f || !p) return;
    let w = Math.min(170, p.ancho * 0.36);
    let h = (w * f.alto) / f.ancho;
    if (h > 80) {
      h = 80;
      w = (h * f.ancho) / f.alto;
    }
    const a: Anotacion = {
      id: nuevoId(), pagina, tipo: 'imagen', png: f.png, w, h,
      x: Math.max(0, Math.min(p.ancho - w, x - w / 2)),
      y: Math.max(0, Math.min(p.alto - h, y - h / 2)),
    };
    this.anadir(a);
    this.setHerramienta('mano');
    this.seleccionar(a.id);
    toast('Arrastra la firma para moverla; la esquina, para cambiar su tamaño.');
  }

  /* ------------------------------------------------------------------------ */
  /* Firma digital                                                             */
  /* ------------------------------------------------------------------------ */

  /** Activa el modo «dibujar el recuadro del sello» y devuelve el recuadro elegido. */
  pedirCajaFirma(): Promise<{ pagina: number; caja: { x: number; y: number; w: number; h: number } } | null> {
    return new Promise((resolver) => {
      this.seleccionar(null);
      this.setHerramienta('cajaFirma');
      let resuelto = false;
      this.alCajaFirma = (pagina, caja) => {
        resuelto = true;
        resolver({ pagina, caja });
      };
      const vigilar = window.setInterval(() => {
        if (this.herramienta !== 'cajaFirma') {
          window.clearInterval(vigilar);
          if (!resuelto) resolver(null);
        }
      }, 200);
      toast(esMovil() ? 'Arrastra el dedo sobre la página para dibujar el recuadro del sello.' : 'Arrastra sobre la página para dibujar el recuadro del sello.', { segundos: 4 });
    });
  }

  async firmarConCertificado(): Promise<void> {
    if (!this.editable()) return this.avisoNoEditable();
    this.seleccionar(null);
    await flujoFirmaDigital(this);
  }

  private menuFirmar(): void {
    const opcion = (ico: NombreIcono, titulo: string, detalle: string, fn: () => void) =>
      el('button.opcion-grande', { type: 'button', html: `${icono(ico, 26)}<span><strong>${titulo}</strong><small>${detalle}</small></span>`, onclick: () => { hoja.cerrar(); fn(); } });
    const hoja = abrirHoja({
      titulo: 'Firmar el documento',
      contenido: el('div.lista-opciones', {},
        opcion('firma', 'Firma manuscrita', 'Coloca tu rúbrica dibujada o escrita', () => void this.usarFirmaManuscrita()),
        opcion('certificado', 'Firma con certificado digital', 'Firma electrónica PAdES con tu certificado .p12 / .pfx (FNMT, ACCV…)', () => void this.firmarConCertificado()),
      ),
    });
  }

  /* ------------------------------------------------------------------------ */
  /* Menús, navegación y teclado                                               */
  /* ------------------------------------------------------------------------ */

  private menuMas(ancla: HTMLElement): void {
    abrirMenu(ancla, 'Más opciones', [
      { texto: 'Guardar en Archivos', icono: 'descargar', detalle: 'Descarga una copia del PDF', accion: () => void this.guardarEnArchivos() },
      { texto: 'Compartir…', icono: 'compartir', accion: () => void this.compartir() },
      { texto: 'Mis firmas', icono: 'firma', accion: () => void elegirFirma().then((f) => { if (f) { this.firmaActual = f; void almacen.fijarAjuste('firmaActual', f.id); this.setHerramienta('firma'); } }) },
      { texto: 'Mis certificados', icono: 'certificado', accion: () => void hojaCertificados() },
      ...(this.firmas.length ? [{ texto: 'Firmas del documento', icono: 'escudo' as NombreIcono, detalle: `${this.firmas.length} firma(s) digital(es)`, accion: () => hojaFirmasDocumento(this.firmas) }] : []),
      { texto: 'Ajustar al ancho', icono: 'ajustar', accion: () => this.visor.ajustarAncho() },
      {
        texto: this.aplanar ? 'Al guardar: anotaciones aplanadas' : 'Al guardar: anotaciones editables', icono: 'ajustes',
        detalle: this.aplanar ? 'Se integran en la página (recomendado). Toca para cambiar.' : 'Se podrán editar en otras apps. Toca para cambiar.',
        accion: () => {
          this.aplanar = !this.aplanar;
          void almacen.fijarAjuste('aplanar', this.aplanar);
          toast(this.aplanar ? 'Las anotaciones se integrarán en la página al guardar.' : 'Las anotaciones se guardarán como anotaciones editables.');
        },
      },
      { texto: 'Cerrar documento', icono: 'cerrar', accion: () => this.cerrar() },
    ]);
  }

  private irAPagina(): void {
    const total = this.visor.total;
    const entrada = el('input', { type: 'number', min: '1', max: String(total), inputmode: 'numeric', value: String(this.visor.pagina + 1), 'aria-label': 'Número de página' }) as HTMLInputElement;
    const ir = () => {
      const n = Number(entrada.value);
      if (n >= 1 && n <= total) this.visor.irAPagina(n - 1);
    };
    entrada.addEventListener('keydown', (e) => { if (e.key === 'Enter') { ir(); hoja.cerrar(); } });
    const hoja = abrirHoja({
      titulo: 'Ir a la página',
      contenido: el('div.formulario', {}, el('label.campo', {}, el('span.campo-etiqueta', {}, `Página (1–${total})`), entrada)),
      botones: [{ texto: 'Cancelar' }, { texto: 'Ir', tipo: 'primario', accion: ir }],
    });
    window.setTimeout(() => entrada.select(), 250);
  }

  private actualizarIndicador(n: number, total: number): void {
    const t = this.elIndicador.querySelector('.texto-pagina');
    if (t) t.textContent = `${n + 1} / ${total}`;
  }

  private teclado(e: KeyboardEvent): void {
    if (!this.elemento.isConnected || document.querySelector('.hoja-fondo, .pad-firma')) return;
    const objetivo = e.target as HTMLElement;
    if (objetivo.closest('input, textarea, [contenteditable]')) return;
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      if (e.shiftKey) this.rehacer(); else this.deshacer();
    } else if (mod && e.key.toLowerCase() === 'y') {
      e.preventDefault();
      this.rehacer();
    } else if (mod && (e.key === '+' || e.key === '=')) {
      e.preventDefault();
      this.visor.ampliar(1.2);
    } else if (mod && e.key === '-') {
      e.preventDefault();
      this.visor.ampliar(1 / 1.2);
    } else if (mod && e.key === '0') {
      e.preventDefault();
      this.visor.ajustarAncho();
    } else if ((e.key === 'Delete' || e.key === 'Backspace') && this.seleccionId) {
      e.preventDefault();
      this.eliminar(this.seleccionId);
    } else if (e.key === 'Escape') {
      if (this.seleccionId) this.seleccionar(null);
      else this.setHerramienta('mano');
    }
  }

  cerrar(): void {
    window.clearTimeout(this.temporizadorGuardado);
    void almacen.guardarAnotaciones(this.id, this.anotaciones).catch(() => undefined);
    document.removeEventListener('keydown', this.teclas);
    this.visor.destruir();
    this.elemento.remove();
    this.alCerrar();
  }
}

