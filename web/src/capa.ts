/**
 * Capa de anotaciones sobre cada página: dibujo SVG (vectorial, nítido a cualquier zoom)
 * e interacción con el dedo, el Apple Pencil o el ratón (Pointer Events).
 */
import { icono } from './iconos';
import {
  type Anotacion, type AnotTexto, cajaAnotacion, nuevoId, OPACIDAD_RESALTADO, segmentosSuaves, simplificar,
  TEXTO_ASCENSO, TEXTO_INTERLINEA,
} from './modelo';
import { escapar } from './ui/componentes';
import type { PaginaVisor, Visor } from './visor';

export type Herramienta = 'mano' | 'resaltar' | 'texto' | 'dibujar' | 'rectangulo' | 'firma' | 'cajaFirma';

export interface ContextoCapa {
  visor: Visor;
  herramienta(): Herramienta;
  anotaciones(): Anotacion[];
  seleccion(): string | null;
  seleccionar(id: string | null): void;
  /** Añade una anotación (con historial). */
  anadir(a: Anotacion): void;
  /** Sustituye una anotación; `historial` = false durante un arrastre (se confirma al final). */
  reemplazar(a: Anotacion, historial: boolean): void;
  /** Marca el inicio de un cambio interactivo (mover/redimensionar) para el historial. */
  inicioCambio(): void;
  finCambio(): void;
  eliminar(id: string): void;
  editarTexto(a: AnotTexto): void;
  color(): string;
  grosor(): number;
  textoEn(pagina: number, x: number, y: number): void;
  firmaEn(pagina: number, x: number, y: number): void;
  cajaFirmaLista(pagina: number, caja: { x: number; y: number; w: number; h: number }): void;
  editable(): boolean;
  avisoNoEditable(): void;
}

const NS = 'http://www.w3.org/2000/svg';
const lienzoMedida = document.createElement('canvas').getContext('2d')!;

export function anchoTexto(a: AnotTexto): number {
  lienzoMedida.font = `${a.tam}px Helvetica, Arial, sans-serif`;
  return Math.max(a.tam * 0.6, ...a.texto.split('\n').map((l) => lienzoMedida.measureText(l).width));
}

export function caja(a: Anotacion): { x: number; y: number; w: number; h: number } {
  return cajaAnotacion(a, anchoTexto);
}

function rutaTrazo(p: number[]): string {
  if (p.length < 2) return '';
  let d = `M${p[0].toFixed(2)} ${p[1].toFixed(2)}`;
  const segs = segmentosSuaves(p);
  if (!segs.length) return `${d}L${p[0].toFixed(2)} ${p[1].toFixed(2)}`;
  for (const [, , cx, cy, x1, y1] of segs) d += `Q${cx.toFixed(2)} ${cy.toFixed(2)} ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  return d;
}

export function svgAnotacion(a: Anotacion): string {
  const id = `data-id="${a.id}"`;
  switch (a.tipo) {
    case 'resaltado':
      return `<rect ${id} class="a-resaltado" x="${a.x}" y="${a.y}" width="${a.w}" height="${a.h}" fill="${a.color}" fill-opacity="${OPACIDAD_RESALTADO}"/>`;
    case 'rectangulo':
      return `<rect ${id} x="${a.x}" y="${a.y}" width="${a.w}" height="${a.h}" fill="none" stroke="${a.color}" stroke-width="${a.grosor}"/>`;
    case 'trazo':
      return `<path ${id} d="${rutaTrazo(a.puntos)}" fill="none" stroke="${a.color}" stroke-width="${a.grosor}" stroke-linecap="round" stroke-linejoin="round"/>`;
    case 'texto': {
      const lineas = a.texto.split('\n').map((l, i) =>
        `<tspan x="${a.x}" y="${(a.y + a.tam * (TEXTO_ASCENSO + TEXTO_INTERLINEA * i)).toFixed(2)}">${escapar(l) || ' '}</tspan>`).join('');
      return `<text ${id} font-family="Helvetica, Arial, sans-serif" font-size="${a.tam}" fill="${a.color}" xml:space="preserve">${lineas}</text>`;
    }
    case 'imagen':
      return `<image ${id} href="${a.png}" x="${a.x}" y="${a.y}" width="${a.w}" height="${a.h}" preserveAspectRatio="none"/>`;
  }
}

interface Gesto {
  tipo: 'dibujo' | 'caja' | 'toque' | 'mover' | 'redimensionar' | 'panoramica';
  pagina: PaginaVisor;
  idPuntero: number;
  x0: number; y0: number;
  cx0: number; cy0: number;
  puntos: number[];
  vista?: SVGElement;
  original?: Anotacion;
  scroll0?: { x: number; y: number };
  movido: boolean;
  t0: number;
}

export class CapaAnotaciones {
  private gesto: Gesto | null = null;
  private svgs = new Map<number, SVGSVGElement>();
  private capasUi = new Map<number, HTMLDivElement>();

  constructor(private ctx: ContextoCapa) {
    const raiz = ctx.visor.raiz;
    raiz.addEventListener('pointerdown', (e) => this.abajo(e));
    raiz.addEventListener('pointermove', (e) => this.mover(e));
    raiz.addEventListener('pointerup', (e) => this.arriba(e));
    raiz.addEventListener('pointercancel', () => this.cancelar());
    raiz.addEventListener('dblclick', (e) => this.doble(e));
    // iOS: con una herramienta de dibujo, un dedo sobre la página nunca debe desplazar el
    // documento (touch-action llega tarde si el gesto empieza muy rápido). Dos dedos: zoom.
    raiz.addEventListener('touchstart', (e) => {
      const h = this.ctx.herramienta();
      const dibuja = h === 'dibujar' || h === 'resaltar' || h === 'rectangulo' || h === 'cajaFirma';
      if (dibuja && e.touches.length === 1 && (e.target as HTMLElement).closest?.('.pagina') && this.ctx.editable()) {
        e.preventDefault();
      }
    }, { passive: false });
  }

  /** Llamado por el visor al crear cada página. */
  prepararPagina(p: PaginaVisor): void {
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'capa-anotaciones');
    svg.setAttribute('viewBox', `0 0 ${p.ancho} ${p.alto}`);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('aria-hidden', 'true');
    const ui = document.createElement('div');
    ui.className = 'capa-ui';
    p.div.append(svg, ui);
    this.svgs.set(p.indice, svg);
    this.capasUi.set(p.indice, ui);
  }

  reiniciar(): void {
    this.svgs.clear();
    this.capasUi.clear();
    this.gesto = null;
  }

  /** Vuelve a dibujar las anotaciones (de una página o de todas). */
  dibujar(pagina?: number): void {
    const todas = this.ctx.anotaciones();
    const paginas = pagina === undefined ? [...this.svgs.keys()] : [pagina];
    for (const i of paginas) {
      const svg = this.svgs.get(i);
      if (!svg) continue;
      svg.innerHTML = todas.filter((a) => a.pagina === i).map(svgAnotacion).join('');
    }
    this.dibujarSeleccion();
  }

  dibujarSeleccion(): void {
    for (const ui of this.capasUi.values()) ui.querySelector('.seleccion')?.remove();
    const id = this.ctx.seleccion();
    const a = id ? this.ctx.anotaciones().find((x) => x.id === id) : undefined;
    if (!a) return;
    const p = this.ctx.visor.paginas[a.pagina];
    const ui = this.capasUi.get(a.pagina);
    if (!p || !ui) return;
    const c = caja(a);
    const margen = a.tipo === 'texto' ? 6 : a.tipo === 'rectangulo' || a.tipo === 'trazo' ? a.grosor / 2 + 3 : 2;
    const sel = document.createElement('div');
    sel.className = 'seleccion';
    sel.dataset.id = a.id;
    Object.assign(sel.style, {
      left: `${((c.x - margen) / p.ancho) * 100}%`,
      top: `${((c.y - margen) / p.alto) * 100}%`,
      width: `${((c.w + 2 * margen) / p.ancho) * 100}%`,
      height: `${((c.h + 2 * margen) / p.alto) * 100}%`,
    });
    const redimensionable = a.tipo !== 'trazo';
    if (redimensionable) {
      const asa = document.createElement('div');
      asa.className = 'asa';
      asa.setAttribute('aria-label', 'Cambiar tamaño');
      sel.append(asa);
    }
    const barra = document.createElement('div');
    barra.className = 'barra-seleccion';
    const botones: Array<[string, string, () => void]> = [];
    if (a.tipo === 'texto') botones.push(['lapiz', 'Editar texto', () => this.ctx.editarTexto(a)]);
    botones.push(['papelera', 'Eliminar', () => this.ctx.eliminar(a.id)]);
    botones.push(['ok', 'Hecho', () => this.ctx.seleccionar(null)]);
    for (const [ico, texto, fn] of botones) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'boton-seleccion';
      b.title = texto;
      b.setAttribute('aria-label', texto);
      b.innerHTML = icono(ico as never, 19);
      b.addEventListener('pointerdown', (e) => e.stopPropagation());
      b.addEventListener('click', (e) => { e.stopPropagation(); fn(); });
      barra.append(b);
    }
    sel.append(barra);
    // Si la anotación está pegada al borde superior, la barra va debajo.
    if (c.y < 40) sel.classList.add('barra-abajo');
    ui.append(sel);
  }

  cancelar(): void {
    const g = this.gesto;
    if (!g) return;
    g.vista?.remove();
    if ((g.tipo === 'mover' || g.tipo === 'redimensionar') && g.original) {
      this.ctx.reemplazar(g.original, false);
      this.ctx.finCambio();
    }
    this.gesto = null;
  }

  private paginaDe(e: PointerEvent): PaginaVisor | null {
    const div = (e.target as HTMLElement).closest?.('.pagina') as HTMLElement | null;
    if (!div) return null;
    return this.ctx.visor.paginas[Number(div.dataset.indice)] ?? null;
  }

  private abajo(e: PointerEvent): void {
    if (this.gesto || (e.pointerType === 'mouse' && e.button !== 0) || !e.isPrimary) {
      if (this.gesto && !e.isPrimary) this.cancelar(); // segundo dedo: es un pellizco
      return;
    }
    const objetivo = e.target as HTMLElement;
    if (objetivo.closest('.barra-seleccion')) return;
    const p = this.paginaDe(e);
    const h = this.ctx.herramienta();
    const enSeleccion = objetivo.closest('.seleccion') as HTMLElement | null;
    if (!p) {
      // Fuera de las páginas: con el ratón y la mano, arrastrar desplaza el documento.
      if (h === 'mano' && e.pointerType === 'mouse') this.iniciarPanoramica(e);
      return;
    }
    const { x, y } = this.ctx.visor.aUnidades(p, e.clientX, e.clientY);
    const base = { pagina: p, idPuntero: e.pointerId, x0: x, y0: y, cx0: e.clientX, cy0: e.clientY, puntos: [x, y], movido: false, t0: performance.now() };

    if (enSeleccion) {
      const a = this.ctx.anotaciones().find((z) => z.id === enSeleccion.dataset.id);
      if (!a) return;
      e.preventDefault();
      this.ctx.inicioCambio();
      this.gesto = { ...base, tipo: objetivo.classList.contains('asa') ? 'redimensionar' : 'mover', original: a };
      enSeleccion.setPointerCapture(e.pointerId);
      return;
    }

    if (h === 'mano') {
      this.gesto = { ...base, tipo: e.pointerType === 'mouse' ? 'panoramica' : 'toque', scroll0: { x: this.ctx.visor.raiz.scrollLeft, y: this.ctx.visor.raiz.scrollTop } };
      return;
    }
    if (!this.ctx.editable()) {
      this.ctx.avisoNoEditable();
      return;
    }
    e.preventDefault();
    p.div.setPointerCapture(e.pointerId);
    const svg = this.svgs.get(p.indice)!;
    if (h === 'dibujar') {
      const vista = document.createElementNS(NS, 'path');
      vista.setAttribute('fill', 'none');
      vista.setAttribute('stroke', this.ctx.color());
      vista.setAttribute('stroke-width', String(this.ctx.grosor()));
      vista.setAttribute('stroke-linecap', 'round');
      vista.setAttribute('stroke-linejoin', 'round');
      svg.append(vista);
      this.gesto = { ...base, tipo: 'dibujo', vista };
      this.actualizarVista();
    } else if (h === 'resaltar' || h === 'rectangulo' || h === 'cajaFirma') {
      const vista = document.createElementNS(NS, 'rect');
      if (h === 'resaltar') {
        vista.setAttribute('fill', this.ctx.color());
        vista.setAttribute('fill-opacity', String(OPACIDAD_RESALTADO));
      } else if (h === 'rectangulo') {
        vista.setAttribute('fill', 'none');
        vista.setAttribute('stroke', this.ctx.color());
        vista.setAttribute('stroke-width', String(this.ctx.grosor()));
      } else {
        vista.setAttribute('class', 'vista-caja-firma');
      }
      svg.append(vista);
      this.gesto = { ...base, tipo: 'caja', vista };
      this.actualizarVista();
    } else {
      this.gesto = { ...base, tipo: 'toque' };
    }
  }

  private iniciarPanoramica(e: PointerEvent): void {
    const raiz = this.ctx.visor.raiz;
    this.gesto = {
      tipo: 'panoramica', pagina: this.ctx.visor.paginas[0], idPuntero: e.pointerId, x0: 0, y0: 0,
      cx0: e.clientX, cy0: e.clientY, puntos: [], movido: false, t0: performance.now(),
      scroll0: { x: raiz.scrollLeft, y: raiz.scrollTop },
    };
  }

  private mover(e: PointerEvent): void {
    const g = this.gesto;
    if (!g || e.pointerId !== g.idPuntero) return;
    const dx = e.clientX - g.cx0, dy = e.clientY - g.cy0;
    if (!g.movido && Math.hypot(dx, dy) > (e.pointerType === 'mouse' ? 3 : 6)) g.movido = true;
    switch (g.tipo) {
      case 'panoramica': {
        if (!g.movido) return;
        const raiz = this.ctx.visor.raiz;
        raiz.scrollLeft = g.scroll0!.x - dx;
        raiz.scrollTop = g.scroll0!.y - dy;
        raiz.classList.add('arrastrando');
        return;
      }
      case 'toque':
        return;
      case 'dibujo': {
        e.preventDefault();
        const eventos = typeof e.getCoalescedEvents === 'function' ? e.getCoalescedEvents() : [];
        for (const ev of eventos.length ? eventos : [e]) {
          const { x, y } = this.ctx.visor.aUnidades(g.pagina, ev.clientX, ev.clientY);
          const n = g.puntos.length;
          if (Math.hypot(x - g.puntos[n - 2], y - g.puntos[n - 1]) > 0.4) g.puntos.push(x, y);
        }
        this.actualizarVista();
        return;
      }
      case 'caja': {
        e.preventDefault();
        const { x, y } = this.ctx.visor.aUnidades(g.pagina, e.clientX, e.clientY);
        g.puntos = [g.x0, g.y0, Math.max(0, Math.min(g.pagina.ancho, x)), Math.max(0, Math.min(g.pagina.alto, y))];
        this.actualizarVista();
        return;
      }
      case 'mover':
      case 'redimensionar': {
        e.preventDefault();
        const z = g.pagina.div.getBoundingClientRect().width / g.pagina.ancho;
        const ux = dx / z, uy = dy / z;
        const nueva = g.tipo === 'mover' ? desplazar(g.original!, ux, uy, g.pagina) : redimensionar(g.original!, ux, uy);
        this.ctx.reemplazar(nueva, false);
        return;
      }
    }
  }

  private actualizarVista(): void {
    const g = this.gesto;
    if (!g?.vista) return;
    if (g.tipo === 'dibujo') {
      g.vista.setAttribute('d', rutaTrazo(g.puntos));
    } else if (g.tipo === 'caja') {
      const [x0, y0, x1 = x0, y1 = y0] = g.puntos;
      g.vista.setAttribute('x', String(Math.min(x0, x1)));
      g.vista.setAttribute('y', String(Math.min(y0, y1)));
      g.vista.setAttribute('width', String(Math.abs(x1 - x0)));
      g.vista.setAttribute('height', String(Math.abs(y1 - y0)));
    }
  }

  private arriba(e: PointerEvent): void {
    const g = this.gesto;
    if (!g || e.pointerId !== g.idPuntero) return;
    this.gesto = null;
    g.vista?.remove();
    const h = this.ctx.herramienta();
    switch (g.tipo) {
      case 'panoramica':
        this.ctx.visor.raiz.classList.remove('arrastrando');
        if (!g.movido) this.tocar(e, g);
        return;
      case 'toque':
        if (g.movido || performance.now() - g.t0 > 800) return;
        this.tocar(e, g);
        return;
      case 'dibujo': {
        // El último tramo (entre el último pointermove y el pointerup) también cuenta.
        const fin = this.ctx.visor.aUnidades(g.pagina, e.clientX, e.clientY);
        const n = g.puntos.length;
        if (n < 2 || g.puntos[n - 2] !== fin.x || g.puntos[n - 1] !== fin.y) g.puntos.push(fin.x, fin.y);
        const puntos = simplificar(g.puntos, 0.35);
        this.ctx.anadir({ id: nuevoId(), pagina: g.pagina.indice, tipo: 'trazo', puntos, color: this.ctx.color(), grosor: this.ctx.grosor() });
        return;
      }
      case 'caja': {
        const [x0, y0, x1 = x0, y1 = y0] = g.puntos;
        const c = { x: Math.min(x0, x1), y: Math.min(y0, y1), w: Math.abs(x1 - x0), h: Math.abs(y1 - y0) };
        if (h === 'cajaFirma') {
          if (c.w < 30 || c.h < 15) return; // demasiado pequeño: se ignora
          this.ctx.cajaFirmaLista(g.pagina.indice, c);
          return;
        }
        if (c.w < 4 || c.h < 4) return;
        if (h === 'resaltar') this.ctx.anadir({ id: nuevoId(), pagina: g.pagina.indice, tipo: 'resaltado', ...c, color: this.ctx.color() });
        else this.ctx.anadir({ id: nuevoId(), pagina: g.pagina.indice, tipo: 'rectangulo', ...c, color: this.ctx.color(), grosor: this.ctx.grosor() });
        return;
      }
      case 'mover':
      case 'redimensionar':
        this.ctx.finCambio();
        if (!g.movido && g.tipo === 'mover' && g.original?.tipo === 'texto' && e.detail >= 2) this.ctx.editarTexto(g.original);
        return;
    }
  }

  private tocar(e: PointerEvent, g: Gesto): void {
    const h = this.ctx.herramienta();
    const p = g.pagina;
    const { x, y } = this.ctx.visor.aUnidades(p, e.clientX, e.clientY);
    if (h === 'texto') return this.ctx.textoEn(p.indice, x, y);
    if (h === 'firma') return this.ctx.firmaEn(p.indice, x, y);
    // Mano: tocar una anotación la selecciona; tocar fuera, deselecciona.
    const z = p.div.getBoundingClientRect().width / p.ancho;
    const tolerancia = 10 / z;
    const candidata = [...this.ctx.anotaciones()].reverse().find((a) => {
      if (a.pagina !== p.indice) return false;
      const c = caja(a);
      return x >= c.x - tolerancia && x <= c.x + c.w + tolerancia && y >= c.y - tolerancia && y <= c.y + c.h + tolerancia;
    });
    this.ctx.seleccionar(candidata?.id ?? null);
  }

  private doble(e: MouseEvent): void {
    const sel = (e.target as HTMLElement).closest('.seleccion') as HTMLElement | null;
    if (!sel) return;
    const a = this.ctx.anotaciones().find((z) => z.id === sel.dataset.id);
    if (a?.tipo === 'texto') this.ctx.editarTexto(a);
  }
}

function desplazar(a: Anotacion, dx: number, dy: number, p: PaginaVisor): Anotacion {
  const c = caja(a);
  // Se mantiene dentro de la página.
  dx = Math.max(-c.x, Math.min(p.ancho - c.x - c.w, dx));
  dy = Math.max(-c.y, Math.min(p.alto - c.y - c.h, dy));
  if (a.tipo === 'trazo') {
    return { ...a, puntos: a.puntos.map((v, i) => v + (i % 2 === 0 ? dx : dy)) };
  }
  return { ...a, x: a.x + dx, y: a.y + dy };
}

function redimensionar(a: Anotacion, dx: number, dy: number): Anotacion {
  switch (a.tipo) {
    case 'imagen': {
      // Se conserva la proporción de la firma.
      const w = Math.max(20, a.w + Math.max(dx, (dy * a.w) / a.h));
      return { ...a, w, h: (w * a.h) / a.w };
    }
    case 'texto': {
      const c = caja(a);
      const factor = Math.max(0.2, (c.w + dx) / c.w);
      return { ...a, tam: Math.max(5, Math.min(120, Math.round(a.tam * factor * 2) / 2)) };
    }
    case 'resaltado':
    case 'rectangulo':
      return { ...a, w: Math.max(6, a.w + dx), h: Math.max(6, a.h + dy) };
    default:
      return a;
  }
}
