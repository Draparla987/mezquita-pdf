/**
 * Escribir directamente sobre la página: un cuadro en el sitio tocado, con la misma letra,
 * tamaño, color e interlineado con que se dibuja el texto (SVG) y se guarda en el PDF, y una
 * barra pegada a él para cambiar el tamaño y el color mientras se escribe.
 */
import { icono } from './iconos';
import { TEXTO_INTERLINEA } from './modelo';
import type { PaginaVisor } from './visor';

const FUENTE = 'Helvetica, Arial, sans-serif';
const TAM_MIN = 6;
const TAM_MAX = 72;
const medida = document.createElement('canvas').getContext('2d')!;

export interface OpcionesTexto {
  pagina: PaginaVisor;
  /** Capa de la página donde se coloca el cuadro (mismo tamaño que la página). */
  capa: HTMLElement;
  /** Esquina superior izquierda del texto, en unidades de página. */
  x: number;
  y: number;
  texto: string;
  tam: number;
  color: string;
  colores: string[];
  alTerminar(texto: string, tam: number, color: string): void;
  alCancelar(): void;
}

export class EdicionTexto {
  readonly raiz: HTMLDivElement;
  readonly area: HTMLTextAreaElement;
  private valor: HTMLSpanElement;
  private barra: HTMLDivElement;
  private muestras: HTMLButtonElement[] = [];
  private tam: number;
  private color: string;
  private cerrada = false;
  private alRedimensionar = () => this.asegurarVisible();

  constructor(private o: OpcionesTexto) {
    this.tam = o.tam;
    this.color = o.color;
    this.raiz = document.createElement('div');
    this.raiz.className = 'editor-texto';
    this.raiz.style.left = `${(o.x / o.pagina.ancho) * 100}%`;
    this.raiz.style.top = `${(o.y / o.pagina.alto) * 100}%`;
    if (o.y < 50) this.raiz.classList.add('barra-abajo');

    this.area = document.createElement('textarea');
    this.area.className = 'area-texto';
    this.area.value = o.texto;
    this.area.wrap = 'off';
    this.area.rows = 1;
    this.area.placeholder = 'Escribe aquí';
    this.area.setAttribute('aria-label', 'Texto');
    this.area.setAttribute('autocapitalize', 'sentences');
    this.area.addEventListener('input', () => this.ajustar());
    this.area.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        this.cancelar();
      } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        this.terminar();
      }
    });
    // Al salir del cuadro (otra parte de la app, «OK» del teclado del iPhone…) se termina
    this.area.addEventListener('blur', () => window.setTimeout(() => {
      if (!this.cerrada && !this.raiz.contains(document.activeElement)) this.terminar();
    }, 0));

    const barra = document.createElement('div');
    this.barra = barra;
    barra.className = 'barra-texto';
    barra.setAttribute('role', 'toolbar');
    barra.setAttribute('aria-label', 'Formato del texto');
    // Los botones no se quedan con el foco: así el teclado sigue abierto y se sigue escribiendo
    barra.addEventListener('pointerdown', (e) => { e.preventDefault(); e.stopPropagation(); });
    barra.addEventListener('mousedown', (e) => e.preventDefault());
    const boton = (clase: string, etiqueta: string, html: string, fn: () => void): HTMLButtonElement => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = clase;
      b.setAttribute('aria-label', etiqueta);
      b.title = etiqueta;
      b.innerHTML = html;
      b.addEventListener('click', (e) => { e.stopPropagation(); fn(); });
      return b;
    };
    this.valor = document.createElement('span');
    this.valor.className = 'valor-texto';
    barra.append(
      boton('boton-texto', 'Letra más pequeña', '<small>A</small>−', () => this.cambiarTam(-1)),
      this.valor,
      boton('boton-texto', 'Letra más grande', 'A+', () => this.cambiarTam(1)),
      Object.assign(document.createElement('span'), { className: 'separador-v' }),
    );
    const colores = [...new Set([o.color, ...o.colores].map((c) => c.toLowerCase()))].slice(0, 5);
    for (const c of colores) {
      const m = boton('muestra-color', `Color ${c}`, '', () => this.cambiarColor(c));
      m.setAttribute('role', 'radio');
      m.style.setProperty('--color', c);
      this.muestras.push(m);
      barra.append(m);
    }
    barra.append(
      Object.assign(document.createElement('span'), { className: 'separador-v' }),
      boton('boton-texto listo', 'Listo', icono('ok', 20), () => this.terminar()),
    );
    this.raiz.append(this.area, barra);
    o.capa.append(this.raiz);
    this.ajustar();
    // En el mismo toque: si no, el iPhone no saca el teclado
    this.area.focus({ preventScroll: true });
    this.area.setSelectionRange(this.area.value.length, this.area.value.length);
    window.visualViewport?.addEventListener('resize', this.alRedimensionar);
    window.setTimeout(() => this.asegurarVisible(), 350);
  }

  /** Tamaño de la letra y del cuadro según el zoom (también al pellizcar o con los botones). */
  ajustar(): void {
    const z = this.o.pagina.div.offsetWidth / this.o.pagina.ancho; // px por unidad de página
    const fs = this.tam * z;
    const lh = TEXTO_INTERLINEA * this.tam * z;
    const a = this.area.style;
    a.font = `${fs}px/${lh}px ${FUENTE}`;
    a.color = this.color;
    medida.font = `${fs}px ${FUENTE}`;
    const lineas = this.area.value.split('\n');
    const ancho = Math.max(medida.measureText(this.area.placeholder).width * (this.area.value ? 0 : 1),
      ...lineas.map((l) => medida.measureText(l).width));
    a.width = `${Math.ceil(ancho + Math.max(3, fs * 0.15))}px`;
    a.height = `${Math.ceil(lineas.length * lh)}px`;
    this.valor.textContent = `${this.tam} pt`;
    this.colocarBarra();
    for (const m of this.muestras) {
      m.setAttribute('aria-checked', String(m.style.getPropertyValue('--color').toLowerCase() === this.color.toLowerCase()));
    }
  }

  /** La barra, centrada sobre el cuadro pero sin salirse de la pantalla (iPhone estrecho). */
  private colocarBarra(): void {
    const b = this.barra;
    const caja = this.raiz.getBoundingClientRect();
    const ancho = b.offsetWidth;
    let izquierda = (caja.width - ancho) / 2;
    const margen = 8;
    izquierda = Math.min(izquierda, window.innerWidth - margen - ancho - caja.left);
    izquierda = Math.max(izquierda, margen - caja.left);
    b.style.left = `${Math.round(izquierda)}px`;
  }

  /** Con el teclado del iPhone abierto, que el cuadro no quede debajo. */
  private asegurarVisible(): void {
    if (this.cerrada) return;
    const vv = window.visualViewport;
    const alto = vv ? vv.height + vv.offsetTop : window.innerHeight;
    const r = this.raiz.getBoundingClientRect();
    const contenedor = this.o.pagina.div.closest('.visor') as HTMLElement | null;
    if (!contenedor) return;
    const sobra = r.bottom + 24 - alto;
    if (sobra > 0) contenedor.scrollTop += sobra;
  }

  private cambiarTam(paso: number): void {
    this.tam = Math.max(TAM_MIN, Math.min(TAM_MAX, Math.round(this.tam) + paso));
    this.ajustar();
  }

  private cambiarColor(c: string): void {
    this.color = c;
    this.ajustar();
  }

  private cerrar(): void {
    this.cerrada = true;
    window.visualViewport?.removeEventListener('resize', this.alRedimensionar);
    this.raiz.remove();
  }

  terminar(): void {
    if (this.cerrada) return;
    const texto = this.area.value.replace(/\s+$/, '');
    this.cerrar();
    this.o.alTerminar(texto, this.tam, this.color);
  }

  cancelar(): void {
    if (this.cerrada) return;
    this.cerrar();
    this.o.alCancelar();
  }
}
