/** Componentes de interfaz reutilizables: hojas (diálogos), menús, avisos y formularios. */
import { icono, type NombreIcono } from '../iconos';

type Hijo = Node | string | null | undefined | false;

/** Crea un elemento: el('button.boton.primario', { onclick }, 'Texto'). */
export function el<K extends keyof HTMLElementTagNameMap>(
  selector: K | `${K}.${string}` | `${K}#${string}`,
  attrs: Record<string, unknown> = {},
  ...hijos: Hijo[]
): HTMLElementTagNameMap[K] {
  const [etiquetaId, ...clases] = selector.split('.');
  const [etiqueta, id] = etiquetaId.split('#');
  const e = document.createElement(etiqueta as K);
  if (id) e.id = id;
  if (clases.length) e.className = clases.join(' ');
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'html') e.innerHTML = String(v);
    else if (k === 'style' && typeof v === 'object') {
      for (const [prop, valor] of Object.entries(v as Record<string, string>)) {
        if (prop.startsWith('--')) e.style.setProperty(prop, valor);
        else (e.style as unknown as Record<string, string>)[prop] = valor;
      }
    }
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v as EventListener);
    else if (k === 'dataset' && typeof v === 'object') Object.assign(e.dataset, v);
    else if (k in e && typeof v !== 'string') (e as unknown as Record<string, unknown>)[k] = v;
    else e.setAttribute(k, v === true ? '' : String(v));
  }
  for (const h of hijos) if (h !== null && h !== undefined && h !== false) e.append(h);
  return e;
}

export function esMovil(): boolean {
  return window.matchMedia('(max-width: 760px)').matches;
}

export function escapar(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}

/* ------------------------------------------------------------------------------ */
/* Aviso flotante (toast)                                                          */
/* ------------------------------------------------------------------------------ */

let toastActual: HTMLElement | null = null;
let temporizadorToast = 0;

export function ocultarToast(): void {
  window.clearTimeout(temporizadorToast);
  const t = toastActual;
  toastActual = null;
  if (!t) return;
  t.classList.remove('visible');
  window.setTimeout(() => t.remove(), 250);
}

export function toast(texto: string, opciones: { segundos?: number; tipo?: 'normal' | 'exito' | 'error'; accion?: { texto: string; fn: () => void } } = {}): void {
  toastActual?.remove();
  window.clearTimeout(temporizadorToast);
  const t = el('div.toast', { role: 'status', 'aria-live': 'polite' }, el('span', {}, texto));
  if (opciones.tipo && opciones.tipo !== 'normal') t.classList.add(opciones.tipo);
  if (opciones.accion) {
    const { texto: tx, fn } = opciones.accion;
    t.append(el('button.toast-accion', { type: 'button', onclick: () => { t.remove(); fn(); } }, tx));
  }
  document.body.append(t);
  toastActual = t;
  requestAnimationFrame(() => t.classList.add('visible'));
  temporizadorToast = window.setTimeout(() => {
    t.classList.remove('visible');
    window.setTimeout(() => t.remove(), 250);
  }, (opciones.segundos ?? (opciones.accion ? 6 : 3)) * 1000);
}

/* ------------------------------------------------------------------------------ */
/* Hojas (bottom sheet en el móvil, diálogo centrado en pantallas anchas)          */
/* ------------------------------------------------------------------------------ */

export interface BotonHoja {
  texto: string;
  tipo?: 'primario' | 'secundario' | 'peligro' | 'texto';
  icono?: NombreIcono;
  /** Devuelve false para no cerrar la hoja. */
  accion?: () => unknown | Promise<unknown>;
  id?: string;
}

export interface Hoja {
  elemento: HTMLElement;
  cuerpo: HTMLElement;
  pie: HTMLElement;
  cerrar: () => void;
  alCerrar: Promise<void>;
}

const pilaHojas: Hoja[] = [];

export function boton(texto: string, tipo: BotonHoja['tipo'] = 'secundario', nombreIcono?: NombreIcono, accion?: (ev: MouseEvent) => void): HTMLButtonElement {
  return el('button', { type: 'button', class: `boton ${tipo}`, onclick: accion, html: (nombreIcono ? icono(nombreIcono, 20) : '') + `<span>${escapar(texto)}</span>` });
}

export function abrirHoja(o: {
  titulo: string;
  subtitulo?: string;
  contenido?: Node | Node[];
  botones?: BotonHoja[];
  clase?: string;
  cerrable?: boolean;
  alCerrar?: () => void;
}): Hoja {
  ocultarToast();
  const cerrable = o.cerrable !== false;
  const cuerpo = el('div.hoja-cuerpo');
  if (o.contenido) cuerpo.append(...(Array.isArray(o.contenido) ? o.contenido : [o.contenido]));
  const pie = el('div.hoja-pie');
  const idTitulo = `hoja-${Math.random().toString(36).slice(2)}`;
  const hoja = el('div.hoja', { role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': idTitulo },
    el('div.hoja-asa', { 'aria-hidden': 'true' }),
    el('header.hoja-cab', {},
      el('div', {}, el('h2', { id: idTitulo }, o.titulo), o.subtitulo ? el('p.hoja-subtitulo', {}, o.subtitulo) : null),
      cerrable ? el('button.boton-icono', { type: 'button', 'aria-label': 'Cerrar', html: icono('cerrar', 20), onclick: () => cerrar() }) : null,
    ),
    cuerpo,
  );
  if (o.clase) hoja.classList.add(...o.clase.split(' '));
  const fondo = el('div.hoja-fondo', {}, hoja);
  let resolverCierre: () => void = () => {};
  const alCerrar = new Promise<void>((r) => { resolverCierre = r; });
  let cerrada = false;
  const controlador: Hoja = { elemento: hoja, cuerpo, pie, cerrar: () => cerrar(), alCerrar };

  const cerrar = () => {
    if (cerrada) return;
    cerrada = true;
    fondo.classList.remove('visible');
    document.removeEventListener('keydown', teclas);
    const i = pilaHojas.indexOf(controlador);
    if (i >= 0) pilaHojas.splice(i, 1);
    window.setTimeout(() => fondo.remove(), 220);
    o.alCerrar?.();
    resolverCierre();
  };
  const teclas = (ev: KeyboardEvent) => {
    if (ev.key === 'Escape' && cerrable && pilaHojas[pilaHojas.length - 1] === controlador) {
      ev.preventDefault();
      cerrar();
    }
  };

  if (o.botones?.length) {
    for (const b of o.botones) {
      const elB = boton(b.texto, b.tipo ?? 'secundario', b.icono);
      if (b.id) elB.id = b.id;
      elB.addEventListener('click', async () => {
        if (!b.accion) return cerrar();
        elB.disabled = true;
        try {
          const r = await b.accion();
          if (r !== false) cerrar();
        } finally {
          elB.disabled = false;
        }
      });
      pie.append(elB);
    }
    hoja.append(pie);
  }

  fondo.addEventListener('pointerdown', (ev) => {
    if (ev.target === fondo && cerrable) fondo.dataset.pulsado = '1';
  });
  fondo.addEventListener('click', (ev) => {
    if (ev.target === fondo && cerrable && fondo.dataset.pulsado) cerrar();
    delete fondo.dataset.pulsado;
  });
  document.addEventListener('keydown', teclas);
  document.body.append(fondo);
  pilaHojas.push(controlador);
  requestAnimationFrame(() => {
    fondo.classList.add('visible');
    const foco = hoja.querySelector<HTMLElement>('[autofocus]');
    if (foco && !esMovil()) foco.focus();
  });
  return controlador;
}

export function hojaAbierta(): boolean {
  return pilaHojas.length > 0;
}

/* ------------------------------------------------------------------------------ */
/* Menús                                                                          */
/* ------------------------------------------------------------------------------ */

export interface ElementoMenu {
  texto: string;
  icono?: NombreIcono;
  detalle?: string;
  peligro?: boolean;
  deshabilitado?: boolean;
  accion: () => void;
}

export function abrirMenu(ancla: HTMLElement, titulo: string, elementos: ElementoMenu[]): void {
  const lista = el('div.menu-lista', { role: 'menu' });
  let hoja: Hoja | null = null;
  let pop: HTMLElement | null = null;
  const cerrar = () => {
    hoja?.cerrar();
    if (pop) {
      pop.remove();
      document.removeEventListener('pointerdown', fuera, true);
    }
  };
  const fuera = (ev: Event) => {
    if (pop && !pop.contains(ev.target as Node) && !ancla.contains(ev.target as Node)) cerrar();
  };
  for (const e of elementos) {
    lista.append(el('button.menu-elemento', {
      type: 'button', role: 'menuitem', disabled: e.deshabilitado,
      class: `menu-elemento${e.peligro ? ' peligro' : ''}`,
      html: (e.icono ? icono(e.icono, 21) : '') + `<span class="menu-texto"><span>${escapar(e.texto)}</span>` +
        (e.detalle ? `<small>${escapar(e.detalle)}</small>` : '') + '</span>',
      onclick: () => { cerrar(); e.accion(); },
    }));
  }
  if (esMovil()) {
    hoja = abrirHoja({ titulo, contenido: lista, clase: 'hoja-menu' });
    return;
  }
  pop = el('div.menu-flotante', {}, lista);
  document.body.append(pop);
  const r = ancla.getBoundingClientRect();
  const ancho = pop.offsetWidth;
  pop.style.top = `${r.bottom + 6}px`;
  pop.style.left = `${Math.max(8, Math.min(window.innerWidth - ancho - 8, r.right - ancho))}px`;
  requestAnimationFrame(() => pop?.classList.add('visible'));
  document.addEventListener('pointerdown', fuera, true);
  const esc = (ev: KeyboardEvent) => {
    if (ev.key === 'Escape') {
      cerrar();
      document.removeEventListener('keydown', esc);
    }
  };
  document.addEventListener('keydown', esc);
}

/* ------------------------------------------------------------------------------ */
/* Diálogos de pregunta                                                           */
/* ------------------------------------------------------------------------------ */

export function confirmar(titulo: string, mensaje: string, textoSi = 'Aceptar', peligro = false): Promise<boolean> {
  return new Promise((resolver) => {
    let r = false;
    abrirHoja({
      titulo,
      contenido: el('p.texto-hoja', {}, mensaje),
      botones: [
        { texto: 'Cancelar', tipo: 'secundario' },
        { texto: textoSi, tipo: peligro ? 'peligro' : 'primario', accion: () => { r = true; } },
      ],
      alCerrar: () => resolver(r),
    });
  });
}

export function campo(etiqueta: string, control: HTMLElement, ayuda?: string): HTMLElement {
  return el('label.campo', {}, el('span.campo-etiqueta', {}, etiqueta), control, ayuda ? el('small.campo-ayuda', {}, ayuda) : null);
}

/** Pide una contraseña. `validar` puede devolver un mensaje de error para reintentar. */
export function pedirContrasena(o: {
  titulo: string;
  mensaje: string;
  textoBoton?: string;
  validar?: (contrasena: string) => Promise<string | null> | string | null;
  extra?: Node;
}): Promise<string | null> {
  return new Promise((resolver) => {
    let resultado: string | null = null;
    const entrada = el('input', {
      type: 'password', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', autofocus: true,
      enterkeyhint: 'done', 'aria-label': 'Contraseña', placeholder: 'Contraseña',
    }) as HTMLInputElement;
    const ver = el('button.boton-icono.ver-contrasena', {
      type: 'button', 'aria-label': 'Mostrar la contraseña', html: icono('ojo', 20),
      onclick: () => {
        const oculto = entrada.type === 'password';
        entrada.type = oculto ? 'text' : 'password';
        ver.innerHTML = icono(oculto ? 'ojoTachado' : 'ojo', 20);
      },
    });
    const error = el('p.error-campo', { role: 'alert' });
    const contenido = el('div', {},
      el('p.texto-hoja', {}, o.mensaje),
      el('div.campo-contrasena', {}, entrada, ver),
      error,
      o.extra ?? null,
    );
    const enviar = async () => {
      const valor = entrada.value;
      if (o.validar) {
        error.textContent = '';
        const msg = await o.validar(valor);
        if (msg) {
          error.textContent = msg;
          entrada.select();
          return false;
        }
      }
      resultado = valor;
      return true;
    };
    const hoja = abrirHoja({
      titulo: o.titulo,
      contenido,
      botones: [
        { texto: 'Cancelar', tipo: 'secundario' },
        { texto: o.textoBoton ?? 'Aceptar', tipo: 'primario', accion: enviar, id: 'boton-contrasena' },
      ],
      alCerrar: () => resolver(resultado),
    });
    entrada.addEventListener('keydown', async (ev) => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        (hoja.pie.querySelector('#boton-contrasena') as HTMLButtonElement)?.click();
      }
    });
    window.setTimeout(() => entrada.focus(), 280);
  });
}

/* ------------------------------------------------------------------------------ */
/* Capa de «trabajando…»                                                          */
/* ------------------------------------------------------------------------------ */

export function ocupado(texto: string): () => void {
  const capa = el('div.ocupado', { role: 'alert', 'aria-busy': 'true' },
    el('div.ocupado-caja', {}, el('div.giro', { 'aria-hidden': 'true' }), el('span', {}, texto)));
  document.body.append(capa);
  requestAnimationFrame(() => capa.classList.add('visible'));
  return () => {
    capa.classList.remove('visible');
    window.setTimeout(() => capa.remove(), 200);
  };
}

/** Espera a que el navegador pinte (para que se vea el indicador antes de un trabajo pesado). */
export function pintar(): Promise<void> {
  return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));
}

export function tamLegible(n: number): string {
  if (n < 1024) return `${n} bytes`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
}

export function fechaRelativa(ms: number): string {
  const fecha = new Date(ms);
  const hoy = new Date();
  const dias = Math.round((new Date(hoy.toDateString()).getTime() - new Date(fecha.toDateString()).getTime()) / 86400000);
  const hh = `${String(fecha.getHours()).padStart(2, '0')}:${String(fecha.getMinutes()).padStart(2, '0')}`;
  if (dias === 0) return `hoy, ${hh}`;
  if (dias === 1) return 'ayer';
  if (dias < 7) return `hace ${dias} días`;
  return fecha.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export function fechaCorta(ms: number): string {
  return new Date(ms).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

/** Abre el selector de archivos del sistema (en iOS, la app Archivos / iCloud Drive). */
export function elegirArchivo(accept?: string): Promise<File | null> {
  return new Promise((resolver) => {
    const entrada = el('input', { type: 'file', style: { position: 'fixed', left: '-1000px', top: '0', opacity: '0' } }) as HTMLInputElement;
    if (accept) entrada.accept = accept;
    let resuelto = false;
    entrada.addEventListener('change', () => {
      resuelto = true;
      resolver(entrada.files?.[0] ?? null);
      entrada.remove();
    });
    entrada.addEventListener('cancel', () => {
      if (!resuelto) resolver(null);
      entrada.remove();
    });
    document.body.append(entrada);
    entrada.click();
  });
}
