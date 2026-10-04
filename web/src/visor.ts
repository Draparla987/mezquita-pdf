/**
 * Visor de páginas con pdf.js:
 *  - desplazamiento continuo con todas las páginas en una columna;
 *  - renderizado perezoso: solo se pintan las páginas visibles (y las vecinas), una a una,
 *    y se liberan los lienzos lejanos (iOS limita la memoria total de los <canvas>);
 *  - nitidez en pantallas Retina (devicePixelRatio), con un tope de píxeles por lienzo;
 *  - zoom con pellizco (táctil y trackpad), Ctrl+rueda y botones.
 */
import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs';
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from 'pdfjs-dist/legacy/build/pdf.mjs';
import TrabajadorPdf from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?worker';

export interface PaginaVisor {
  indice: number;
  /** Tamaño en unidades de página (vista a escala 1 con la rotación aplicada). */
  ancho: number;
  alto: number;
  div: HTMLDivElement;
  proxy: PDFPageProxy;
  lienzo: HTMLCanvasElement | null;
  escalaPintada: number;
  tarea: RenderTask | null;
}

export interface EventosVisor {
  alCambiarPagina?: (actual: number, total: number) => void;
  alCambiarZoom?: (zoom: number) => void;
  alCrearPagina?: (p: PaginaVisor) => void;
  /** Al empezar un gesto de dos dedos (para cancelar un trazo en curso). */
  alPellizcar?: () => void;
}

export class ErrorContrasena extends Error {
  constructor(public incorrecta: boolean) {
    super(incorrecta ? 'Contraseña incorrecta' : 'El documento necesita contraseña');
  }
}

const ZOOM_MIN = 0.2;
const ZOOM_MAX = 6;
const MARGEN = 16;
const MAX_LIENZOS = 8;
const esTactil = () => window.matchMedia('(pointer: coarse)').matches;
/** Píxeles máximos por lienzo (iOS no admite más de 16,7 MP por <canvas>). */
const maxPixeles = () => (esTactil() ? 10_000_000 : 20_000_000);

let trabajador: Worker | null = null;
function prepararTrabajador(): void {
  if (trabajador) return;
  trabajador = new TrabajadorPdf();
  pdfjs.GlobalWorkerOptions.workerPort = trabajador;
}

function urlRecurso(ruta: string): string {
  return new URL(ruta, document.baseURI).href;
}

export class Visor {
  readonly raiz: HTMLElement;
  readonly contenedor: HTMLDivElement;
  doc: PDFDocumentProxy | null = null;
  private tareaCarga: { destroy(): Promise<void> } | null = null;
  paginas: PaginaVisor[] = [];
  zoom = 1;
  private eventos: EventosVisor;
  private cola: PaginaVisor[] = [];
  private pintando = false;
  private temporizadorRender = 0;
  private paginaActual = 0;
  private pellizco: {
    d0: number; m0: { x: number; y: number }; m: { x: number; y: number }; z0: number; s: number;
    origen: { x: number; y: number }; ancla: { pagina: number; u: number; v: number } | null;
  } | null = null;
  private gestoSafari: { z0: number; s: number; m0: { x: number; y: number }; origen: { x: number; y: number }; ancla: { pagina: number; u: number; v: number } | null } | null = null;
  private observador: ResizeObserver;
  private anchoPrevio = 0;
  private ajuste: 'ancho' | 'pagina' | null = 'ancho';
  private destruido = false;

  constructor(raiz: HTMLElement, eventos: EventosVisor = {}) {
    this.raiz = raiz;
    this.eventos = eventos;
    this.contenedor = document.createElement('div');
    this.contenedor.className = 'paginas';
    raiz.append(this.contenedor);
    raiz.addEventListener('scroll', () => this.alDesplazar(), { passive: true });
    raiz.addEventListener('touchstart', (e) => this.toqueInicio(e), { passive: true });
    raiz.addEventListener('touchmove', (e) => this.toqueMovimiento(e), { passive: false });
    raiz.addEventListener('touchend', (e) => this.toqueFin(e), { passive: true });
    raiz.addEventListener('touchcancel', (e) => this.toqueFin(e), { passive: true });
    raiz.addEventListener('wheel', (e) => this.rueda(e), { passive: false });
    // Safari (iOS y trackpad del Mac): gestos de pellizco propios
    raiz.addEventListener('gesturestart', (e) => this.gestoInicio(e as GestureEvento), { passive: false } as AddEventListenerOptions);
    raiz.addEventListener('gesturechange', (e) => this.gestoCambio(e as GestureEvento), { passive: false } as AddEventListenerOptions);
    raiz.addEventListener('gestureend', (e) => this.gestoFin(e as GestureEvento), { passive: false } as AddEventListenerOptions);
    this.observador = new ResizeObserver(() => this.alRedimensionar());
    this.observador.observe(raiz);
  }

  /** Abre un documento. Lanza ErrorContrasena si hace falta (o es incorrecta). */
  async abrir(datos: Uint8Array, contrasena?: string): Promise<PDFDocumentProxy> {
    prepararTrabajador();
    const tarea = pdfjs.getDocument({
      data: datos.slice(), // pdf.js transfiere (y vacía) el búfer: se le pasa una copia
      password: contrasena,
      cMapUrl: urlRecurso('pdfjs/cmaps/'),
      cMapPacked: true,
      standardFontDataUrl: urlRecurso('pdfjs/standard_fonts/'),
      wasmUrl: urlRecurso('pdfjs/wasm/'),
      iccUrl: urlRecurso('pdfjs/iccs/'),
      enableXfa: false,
    });
    let doc: PDFDocumentProxy;
    try {
      doc = await tarea.promise;
    } catch (e) {
      const err = e as { name?: string; code?: number };
      if (err?.name === 'PasswordException') {
        throw new ErrorContrasena(err.code === pdfjs.PasswordResponses.INCORRECT_PASSWORD);
      }
      throw e;
    }
    await this.cerrar();
    this.doc = doc;
    this.tareaCarga = tarea;
    const proxies: PDFPageProxy[] = [];
    // Se piden todas las páginas (solo metadatos, rápido) para conocer sus tamaños.
    const lote = 32;
    for (let i = 1; i <= doc.numPages; i += lote) {
      const fin = Math.min(doc.numPages, i + lote - 1);
      const trozo = await Promise.all(Array.from({ length: fin - i + 1 }, (_, k) => doc.getPage(i + k)));
      proxies.push(...trozo);
    }
    this.contenedor.replaceChildren();
    this.paginas = proxies.map((proxy, indice) => {
      const vista = proxy.getViewport({ scale: 1 });
      const div = document.createElement('div');
      div.className = 'pagina';
      div.dataset.indice = String(indice);
      div.setAttribute('aria-label', `Página ${indice + 1}`);
      this.contenedor.append(div);
      const p: PaginaVisor = { indice, ancho: vista.width, alto: vista.height, div, proxy, lienzo: null, escalaPintada: 0, tarea: null };
      this.eventos.alCrearPagina?.(p);
      return p;
    });
    this.ajuste = 'ancho';
    this.ajustar();
    this.raiz.scrollTop = 0;
    this.alDesplazar();
    return doc;
  }

  get total(): number {
    return this.paginas.length;
  }

  async cerrar(): Promise<void> {
    for (const p of this.paginas) this.liberar(p);
    this.paginas = [];
    this.cola = [];
    this.contenedor.replaceChildren();
    this.doc = null;
    if (this.tareaCarga) {
      const t = this.tareaCarga;
      this.tareaCarga = null;
      try {
        await t.destroy();
      } catch {
        /* ya destruido */
      }
    }
  }

  destruir(): void {
    this.destruido = true;
    this.observador.disconnect();
    void this.cerrar();
  }

  /* --- Zoom ----------------------------------------------------------------------- */

  private zoomAncho(): number {
    const disponible = this.raiz.clientWidth - 2 * MARGEN;
    const maxAncho = Math.max(1, ...this.paginas.map((p) => p.ancho));
    // En pantallas anchas no se amplía más del 125 % aproximado (como un visor de escritorio).
    return Math.min(disponible / maxAncho, esTactil() ? ZOOM_MAX : 1.6);
  }

  private zoomPagina(): number {
    const p = this.paginas[this.paginaActual] ?? this.paginas[0];
    if (!p) return 1;
    return Math.min((this.raiz.clientWidth - 2 * MARGEN) / p.ancho, (this.raiz.clientHeight - 2 * MARGEN) / p.alto);
  }

  ajustarAncho(): void {
    this.ajuste = 'ancho';
    this.setZoom(this.zoomAncho());
  }

  ajustarPagina(): void {
    this.ajuste = 'pagina';
    this.setZoom(this.zoomPagina());
    this.irAPagina(this.paginaActual);
  }

  private ajustar(): void {
    this.zoom = this.ajuste === 'pagina' ? this.zoomPagina() : this.zoomAncho();
    this.aplicarTamanos();
    this.eventos.alCambiarZoom?.(this.zoom);
  }

  ampliar(factor: number): void {
    this.ajuste = null;
    this.setZoom(this.zoom * factor);
  }

  /** Cambia el zoom manteniendo fijo el punto del documento bajo `foco` (coordenadas de pantalla). */
  setZoom(z: number, foco?: { x: number; y: number }, ancla?: { pagina: number; u: number; v: number } | null): void {
    if (!this.paginas.length) return;
    const nuevo = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
    const r = this.raiz.getBoundingClientRect();
    const f = foco ?? { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    const a = ancla ?? this.puntoDocumento(f.x, f.y);
    this.zoom = nuevo;
    this.aplicarTamanos();
    if (a) {
      const p = this.paginas[a.pagina];
      const x = this.contenedor.offsetLeft + p.div.offsetLeft + a.u * nuevo;
      const y = this.contenedor.offsetTop + p.div.offsetTop + a.v * nuevo;
      this.raiz.scrollLeft = x - (f.x - r.left);
      this.raiz.scrollTop = y - (f.y - r.top);
    }
    this.eventos.alCambiarZoom?.(this.zoom);
    this.programarRender();
  }

  private aplicarTamanos(): void {
    const z = this.zoom;
    for (const p of this.paginas) {
      p.div.style.width = `${Math.round(p.ancho * z)}px`;
      p.div.style.height = `${Math.round(p.alto * z)}px`;
    }
  }

  private alRedimensionar(): void {
    const ancho = this.raiz.clientWidth;
    if (!this.paginas.length || Math.abs(ancho - this.anchoPrevio) < 2) {
      this.anchoPrevio = ancho;
      return;
    }
    this.anchoPrevio = ancho;
    if (this.ajuste) {
      const actual = this.paginaActual;
      this.ajustar();
      this.irAPagina(actual);
    }
    this.programarRender();
  }

  /* --- Coordenadas -------------------------------------------------------------------- */

  /** Punto del documento (página y unidades) bajo unas coordenadas de pantalla. */
  puntoDocumento(cx: number, cy: number): { pagina: number; u: number; v: number } | null {
    if (!this.paginas.length) return null;
    let mejor = 0;
    let distancia = Infinity;
    for (const p of this.paginasCercanas()) {
      const r = p.div.getBoundingClientRect();
      const d = cy < r.top ? r.top - cy : cy > r.bottom ? cy - r.bottom : 0;
      if (d < distancia) {
        distancia = d;
        mejor = p.indice;
        if (d === 0) break;
      }
    }
    const p = this.paginas[mejor];
    const r = p.div.getBoundingClientRect();
    return { pagina: mejor, u: ((cx - r.left) / r.width) * p.ancho, v: ((cy - r.top) / r.height) * p.alto };
  }

  /** Convierte coordenadas de pantalla a unidades de una página concreta. */
  aUnidades(p: PaginaVisor, cx: number, cy: number): { x: number; y: number } {
    const r = p.div.getBoundingClientRect();
    return { x: ((cx - r.left) / r.width) * p.ancho, y: ((cy - r.top) / r.height) * p.alto };
  }

  private paginasCercanas(): PaginaVisor[] {
    const [ini, fin] = this.rangoVisible(1);
    return this.paginas.slice(ini, fin + 1);
  }

  /** Índices [primero, último] de las páginas visibles (más `extra` pantallas alrededor). */
  rangoVisible(extra = 0.75): [number, number] {
    const n = this.paginas.length;
    if (!n) return [0, -1];
    const alto = this.raiz.clientHeight;
    const arriba = this.raiz.scrollTop - this.contenedor.offsetTop - alto * extra;
    const abajo = this.raiz.scrollTop - this.contenedor.offsetTop + alto * (1 + extra);
    // Búsqueda binaria sobre offsetTop (las páginas están en una columna).
    let lo = 0, hi = n - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      const p = this.paginas[mid].div;
      if (p.offsetTop + p.offsetHeight < arriba) lo = mid + 1;
      else hi = mid;
    }
    let fin = lo;
    while (fin + 1 < n && this.paginas[fin + 1].div.offsetTop <= abajo) fin++;
    return [lo, fin];
  }

  irAPagina(indice: number, suave = false): void {
    const p = this.paginas[Math.max(0, Math.min(this.paginas.length - 1, indice))];
    if (!p) return;
    this.raiz.scrollTo({ top: this.contenedor.offsetTop + p.div.offsetTop - MARGEN / 2, behavior: suave ? 'smooth' : 'auto' });
  }

  /* --- Renderizado ---------------------------------------------------------------------- */

  private alDesplazar(): void {
    if (!this.paginas.length) return;
    const medio = this.raiz.scrollTop - this.contenedor.offsetTop + this.raiz.clientHeight / 2;
    const [ini, fin] = this.rangoVisible(0);
    let actual = ini;
    for (let i = ini; i <= fin; i++) {
      const d = this.paginas[i].div;
      if (d.offsetTop <= medio) actual = i;
    }
    if (actual !== this.paginaActual) {
      this.paginaActual = actual;
    }
    this.eventos.alCambiarPagina?.(this.paginaActual, this.paginas.length);
    this.programarRender();
  }

  get pagina(): number {
    return this.paginaActual;
  }

  programarRender(retardo = 80): void {
    window.clearTimeout(this.temporizadorRender);
    this.temporizadorRender = window.setTimeout(() => this.encolarVisibles(), retardo);
  }

  private escalaDeseada(p: PaginaVisor): number {
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const escala = this.zoom * dpr;
    const limite = Math.sqrt(maxPixeles() / (p.ancho * p.alto));
    return Math.min(escala, limite);
  }

  private encolarVisibles(): void {
    if (this.destruido || this.pellizco || this.gestoSafari) return;
    const [ini, fin] = this.rangoVisible(0.75);
    const centro = this.paginaActual;
    const pendientes: PaginaVisor[] = [];
    for (let i = ini; i <= fin; i++) {
      const p = this.paginas[i];
      const deseada = this.escalaDeseada(p);
      if (!p.lienzo || Math.abs(p.escalaPintada - deseada) / deseada > 0.04) pendientes.push(p);
    }
    pendientes.sort((a, b) => Math.abs(a.indice - centro) - Math.abs(b.indice - centro));
    // Cancela lo que ya no está a la vista.
    for (const p of this.cola) if (!pendientes.includes(p) && p.tarea) p.tarea.cancel();
    this.cola = pendientes;
    this.liberarLejanas(ini, fin);
    void this.procesarCola();
  }

  private liberarLejanas(ini: number, fin: number): void {
    const pintadas = this.paginas.filter((p) => p.lienzo);
    if (pintadas.length <= MAX_LIENZOS) return;
    const centro = (ini + fin) / 2;
    pintadas
      .filter((p) => p.indice < ini || p.indice > fin)
      .sort((a, b) => Math.abs(b.indice - centro) - Math.abs(a.indice - centro))
      .slice(0, pintadas.length - MAX_LIENZOS)
      .forEach((p) => this.liberar(p));
  }

  private liberar(p: PaginaVisor): void {
    p.tarea?.cancel();
    p.tarea = null;
    if (p.lienzo) {
      p.lienzo.width = 0;
      p.lienzo.height = 0;
      p.lienzo.remove();
      p.lienzo = null;
      p.escalaPintada = 0;
    }
  }

  private async procesarCola(): Promise<void> {
    if (this.pintando) return;
    this.pintando = true;
    try {
      while (this.cola.length && !this.destruido) {
        const p = this.cola.shift()!;
        await this.pintar(p);
      }
    } finally {
      this.pintando = false;
    }
  }

  private async pintar(p: PaginaVisor): Promise<void> {
    const escala = this.escalaDeseada(p);
    const vista = p.proxy.getViewport({ scale: escala });
    const lienzo = document.createElement('canvas');
    lienzo.className = 'lienzo-pdf';
    lienzo.width = Math.max(1, Math.floor(vista.width));
    lienzo.height = Math.max(1, Math.floor(vista.height));
    lienzo.setAttribute('aria-hidden', 'true');
    const tarea = p.proxy.render({ canvas: lienzo, viewport: vista, annotationMode: pdfjs.AnnotationMode.ENABLE });
    p.tarea = tarea;
    try {
      await tarea.promise;
    } catch (e) {
      lienzo.width = lienzo.height = 0;
      if ((e as { name?: string })?.name !== 'RenderingCancelledException') console.warn('Error al pintar la página', p.indice + 1, e);
      return;
    } finally {
      if (p.tarea === tarea) p.tarea = null;
    }
    if (!this.paginas.includes(p)) {
      lienzo.width = lienzo.height = 0;
      return;
    }
    const anterior = p.lienzo;
    p.div.prepend(lienzo);
    p.lienzo = lienzo;
    p.escalaPintada = escala;
    if (anterior) {
      anterior.width = anterior.height = 0;
      anterior.remove();
    }
  }

  /* --- Gestos ---------------------------------------------------------------------------- */

  private origenContenedor(): { x: number; y: number } {
    const r = this.contenedor.getBoundingClientRect();
    return { x: r.left, y: r.top };
  }

  private transformar(s: number, m0: { x: number; y: number }, m: { x: number; y: number }, origen: { x: number; y: number }): void {
    const fx = m0.x - origen.x;
    const fy = m0.y - origen.y;
    const tx = fx * (1 - s) + (m.x - m0.x);
    const ty = fy * (1 - s) + (m.y - m0.y);
    this.contenedor.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
  }

  private toqueInicio(e: TouchEvent): void {
    if (e.touches.length !== 2 || !this.paginas.length) return;
    const [a, b] = [e.touches[0], e.touches[1]];
    const m0 = { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    this.pellizco = {
      d0: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) || 1,
      m0, m: m0, z0: this.zoom, s: 1, origen: this.origenContenedor(), ancla: this.puntoDocumento(m0.x, m0.y),
    };
    this.contenedor.style.transformOrigin = '0 0';
    this.contenedor.classList.add('pellizcando');
    this.eventos.alPellizcar?.();
  }

  private toqueMovimiento(e: TouchEvent): void {
    const pz = this.pellizco;
    if (!pz || e.touches.length < 2) return;
    if (e.cancelable) e.preventDefault();
    const [a, b] = [e.touches[0], e.touches[1]];
    const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
    const zNuevo = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, (pz.z0 * d) / pz.d0));
    pz.s = zNuevo / pz.z0;
    pz.m = { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    this.transformar(pz.s, pz.m0, pz.m, pz.origen);
  }

  private toqueFin(e: TouchEvent): void {
    const pz = this.pellizco;
    if (!pz || e.touches.length >= 2) return;
    this.pellizco = null;
    this.contenedor.style.transform = '';
    this.contenedor.classList.remove('pellizcando');
    this.ajuste = null;
    this.setZoom(pz.z0 * pz.s, pz.m, pz.ancla);
  }

  private gestoInicio(e: GestureEvento): void {
    e.preventDefault();
    if (this.pellizco || !this.paginas.length) return; // en iOS ya lo gestionan los eventos táctiles
    const m0 = { x: e.clientX, y: e.clientY };
    this.gestoSafari = { z0: this.zoom, s: 1, m0, origen: this.origenContenedor(), ancla: this.puntoDocumento(m0.x, m0.y) };
    this.contenedor.style.transformOrigin = '0 0';
  }

  private gestoCambio(e: GestureEvento): void {
    e.preventDefault();
    const g = this.gestoSafari;
    if (!g || this.pellizco) return;
    const zNuevo = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, g.z0 * e.scale));
    g.s = zNuevo / g.z0;
    this.transformar(g.s, g.m0, g.m0, g.origen);
  }

  private gestoFin(e: GestureEvento): void {
    e.preventDefault();
    const g = this.gestoSafari;
    if (!g) return;
    this.gestoSafari = null;
    this.contenedor.style.transform = '';
    this.ajuste = null;
    this.setZoom(g.z0 * g.s, g.m0, g.ancla);
  }

  private rueda(e: WheelEvent): void {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const factor = Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.01));
    this.ajuste = null;
    this.setZoom(this.zoom * factor, { x: e.clientX, y: e.clientY });
  }
}

interface GestureEvento extends UIEvent {
  scale: number;
  clientX: number;
  clientY: number;
}
