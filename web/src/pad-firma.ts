/**
 * Firmas manuscritas: dibujadas en un panel a pantalla completa (dedo o Apple Pencil,
 * con grosor sensible a la presión) o escritas con letra caligráfica. Se guardan en
 * IndexedDB como PNG con fondo transparente.
 */
import allura from '@fontsource/allura/files/allura-latin-400-normal.woff2?url';
import dancing from '@fontsource/dancing-script/files/dancing-script-latin-400-normal.woff2?url';
import greatVibes from '@fontsource/great-vibes/files/great-vibes-latin-400-normal.woff2?url';
import * as almacen from './almacen';
import type { FirmaGuardada } from './almacen';
import { icono } from './iconos';
import { nuevoId } from './modelo';
import { COLORES_FIRMA } from './tema';
import { abrirHoja, boton, confirmar, el, esMovil, toast } from './ui/componentes';

interface Punto { x: number; y: number; w: number }

const LETRAS = [
  { nombre: 'Great Vibes', url: greatVibes },
  { nombre: 'Dancing Script', url: dancing },
  { nombre: 'Allura', url: allura },
];
let letrasCargadas: Promise<void> | null = null;

function cargarLetras(): Promise<void> {
  letrasCargadas ??= Promise.all(
    LETRAS.map(async (l) => {
      try {
        const f = new FontFace(l.nombre, `url(${l.url}) format("woff2")`);
        await f.load();
        document.fonts.add(f);
      } catch {
        /* si falla, se usará la letra del sistema */
      }
    }),
  ).then(() => undefined);
  return letrasCargadas;
}

/** Recorta los bordes transparentes de un lienzo y devuelve un PNG. */
function recortar(lienzo: HTMLCanvasElement, margen = 6, anchoMax = 1400): { png: string; ancho: number; alto: number } | null {
  const ctx = lienzo.getContext('2d')!;
  const { width: w, height: h } = lienzo;
  const datos = ctx.getImageData(0, 0, w, h).data;
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (datos[(y * w + x) * 4 + 3] > 8) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
  }
  if (x1 < 0) return null;
  x0 = Math.max(0, x0 - margen); y0 = Math.max(0, y0 - margen);
  x1 = Math.min(w - 1, x1 + margen); y1 = Math.min(h - 1, y1 + margen);
  const cw = x1 - x0 + 1, ch = y1 - y0 + 1;
  const escala = Math.min(1, anchoMax / cw);
  const salida = document.createElement('canvas');
  salida.width = Math.round(cw * escala);
  salida.height = Math.round(ch * escala);
  const sctx = salida.getContext('2d')!;
  sctx.imageSmoothingQuality = 'high';
  sctx.drawImage(lienzo, x0, y0, cw, ch, 0, 0, salida.width, salida.height);
  return { png: salida.toDataURL('image/png'), ancho: salida.width, alto: salida.height };
}

async function guardar(r: { png: string; ancho: number; alto: number }): Promise<FirmaGuardada> {
  const f: FirmaGuardada = { id: nuevoId(), png: r.png, ancho: r.ancho, alto: r.alto, fecha: Date.now() };
  try {
    await almacen.guardarFirma(f);
  } catch {
    toast('No se pudo guardar la firma en este dispositivo; se usará solo ahora.', { tipo: 'error' });
  }
  return f;
}

/* ------------------------------------------------------------------------------ */
/* Panel de dibujo a pantalla completa                                             */
/* ------------------------------------------------------------------------------ */

export function dibujarFirma(): Promise<FirmaGuardada | null> {
  return new Promise((resolver) => {
    let color = COLORES_FIRMA[0];
    const trazos: Array<{ color: string; puntos: Punto[] }> = [];
    const lienzo = el('canvas', { class: 'pad-lienzo', 'aria-label': 'Zona para dibujar la firma' });
    const ctx = lienzo.getContext('2d')!;
    const pista = el('p.pad-pista', {}, 'Firma con el dedo o con el Apple Pencil');
    const giro = el('p.pad-giro', { html: `${icono('girar', 18)}<span>Gira el iPhone para tener más espacio</span>` });
    const zona = el('div.pad-zona', {}, lienzo, el('div.pad-linea', { 'aria-hidden': 'true' }, el('span', {}, '×')), pista);
    let dpr = 1;
    let anchoPrevio = 0;

    const redibujar = () => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, lienzo.width, lienzo.height);
      for (const t of trazos) pintarTrazo(t.puntos, t.color);
    };
    const pintarTrazo = (p: Punto[], c: string) => {
      ctx.strokeStyle = c;
      ctx.fillStyle = c;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      if (p.length === 1) {
        ctx.beginPath();
        ctx.arc(p[0].x, p[0].y, p[0].w / 2, 0, Math.PI * 2);
        ctx.fill();
        return;
      }
      for (let i = 1; i < p.length; i++) {
        const a = p[i - 1], b = p[i];
        const ant = p[i - 2] ?? a;
        ctx.beginPath();
        ctx.lineWidth = (a.w + b.w) / 2;
        ctx.moveTo((ant.x + a.x) / 2, (ant.y + a.y) / 2);
        ctx.quadraticCurveTo(a.x, a.y, (a.x + b.x) / 2, (a.y + b.y) / 2);
        ctx.stroke();
      }
    };
    const ajustarTamano = () => {
      const r = zona.getBoundingClientRect();
      if (!r.width) return;
      dpr = Math.min(window.devicePixelRatio || 1, 3);
      if (anchoPrevio && Math.abs(anchoPrevio - r.width) > 1) {
        const f = r.width / anchoPrevio;
        for (const t of trazos) for (const p of t.puntos) { p.x *= f; p.y *= f; p.w *= Math.sqrt(f); }
      }
      anchoPrevio = r.width;
      lienzo.width = Math.round(r.width * dpr);
      lienzo.height = Math.round(r.height * dpr);
      redibujar();
    };

    let actual: { id: number; puntos: Punto[]; t: number } | null = null;
    const grosorBase = () => Math.max(2.2, Math.min(4.2, zona.clientWidth / 220));
    const punto = (e: PointerEvent, anterior?: Punto, t?: number): Punto => {
      const r = lienzo.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      const base = grosorBase();
      let w = base;
      if (e.pointerType === 'pen' && e.pressure > 0) w = base * (0.45 + e.pressure * 1.1);
      else if (anterior && t) {
        const v = Math.hypot(x - anterior.x, y - anterior.y) / Math.max(1, performance.now() - t);
        w = base * Math.max(0.55, Math.min(1.25, 1.3 - v * 0.35));
        w = anterior.w * 0.6 + w * 0.4;
      }
      return { x, y, w };
    };
    lienzo.addEventListener('pointerdown', (e) => {
      if (actual) return;
      e.preventDefault();
      lienzo.setPointerCapture(e.pointerId);
      actual = { id: e.pointerId, puntos: [punto(e)], t: performance.now() };
      trazos.push({ color, puntos: actual.puntos });
      pista.classList.add('oculta');
      redibujar();
    });
    lienzo.addEventListener('pointermove', (e) => {
      if (!actual || e.pointerId !== actual.id) return;
      e.preventDefault();
      const eventos = typeof e.getCoalescedEvents === 'function' ? e.getCoalescedEvents() : [];
      for (const ev of eventos.length ? eventos : [e]) {
        const ant = actual.puntos[actual.puntos.length - 1];
        const p = punto(ev, ant, actual.t);
        if (Math.hypot(p.x - ant.x, p.y - ant.y) < 0.8) continue;
        actual.puntos.push(p);
        actual.t = performance.now();
      }
      redibujar();
    });
    const terminar = (e: PointerEvent) => {
      if (actual && e.pointerId === actual.id) actual = null;
    };
    lienzo.addEventListener('pointerup', terminar);
    lienzo.addEventListener('pointercancel', terminar);

    const colores = el('div.pad-colores', { role: 'radiogroup', 'aria-label': 'Color de la tinta' });
    for (const c of COLORES_FIRMA) {
      const b = el('button.muestra-color', {
        type: 'button', role: 'radio', 'aria-checked': String(c === color), 'aria-label': `Color ${c}`,
        style: { '--color': c } as never,
        onclick: () => {
          color = c;
          colores.querySelectorAll('button').forEach((x) => x.setAttribute('aria-checked', String(x === b)));
          for (const t of trazos) t.color = c;
          redibujar();
        },
      });
      colores.append(b);
    }
    const borrar = boton('Borrar', 'secundario', 'borrarUltima', () => {
      trazos.length = 0;
      pista.classList.remove('oculta');
      redibujar();
    });
    const deshacer = el('button.boton-icono', { type: 'button', 'aria-label': 'Deshacer el último trazo', html: icono('deshacer', 22), onclick: () => { trazos.pop(); if (!trazos.length) pista.classList.remove('oculta'); redibujar(); } });

    const cerrar = (r: FirmaGuardada | null) => {
      panel.classList.remove('visible');
      window.removeEventListener('resize', ajustarTamano);
      observador.disconnect();
      window.setTimeout(() => panel.remove(), 220);
      resolver(r);
    };
    const aceptar = el('button.boton.primario', {
      type: 'button', html: `${icono('ok', 20)}<span>Guardar</span>`,
      onclick: async () => {
        if (!trazos.length) {
          toast('Dibuja tu firma antes de guardarla.');
          return;
        }
        const r = recortar(lienzo, Math.round(8 * dpr));
        if (!r) return;
        cerrar(await guardar(r));
      },
    });
    const panel = el('div.pad-firma', { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Dibujar firma' },
      el('header.pad-cab', {},
        el('button.boton.texto', { type: 'button', onclick: () => cerrar(null) }, 'Cancelar'),
        el('h2', {}, 'Dibuja tu firma'),
        aceptar,
      ),
      zona,
      el('footer.pad-pie', {}, colores, giro, el('div.pad-acciones', {}, deshacer, borrar)),
    );
    document.body.append(panel);
    const observador = new ResizeObserver(() => ajustarTamano());
    observador.observe(zona);
    window.addEventListener('resize', ajustarTamano);
    requestAnimationFrame(() => {
      panel.classList.add('visible');
      ajustarTamano();
    });
  });
}

/* ------------------------------------------------------------------------------ */
/* Firma escrita con letra caligráfica                                             */
/* ------------------------------------------------------------------------------ */

function renderizarNombre(nombre: string, letra: string, color: string): { png: string; ancho: number; alto: number } | null {
  const tam = 160;
  const lienzo = document.createElement('canvas');
  const ctx = lienzo.getContext('2d')!;
  ctx.font = `${tam}px "${letra}", "Snell Roundhand", "Apple Chancery", cursive`;
  const ancho = Math.ceil(ctx.measureText(nombre).width + tam);
  lienzo.width = Math.min(4000, ancho);
  lienzo.height = Math.round(tam * 1.9);
  ctx.font = `${tam}px "${letra}", "Snell Roundhand", "Apple Chancery", cursive`;
  ctx.fillStyle = color;
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(nombre, tam / 2, tam * 1.25);
  return recortar(lienzo, 10, 1600);
}

export function escribirFirma(): Promise<FirmaGuardada | null> {
  return new Promise((resolver) => {
    let resultado: FirmaGuardada | null = null;
    let letra = LETRAS[0].nombre;
    let color = COLORES_FIRMA[0];
    const entrada = el('input', {
      type: 'text', placeholder: 'Tu nombre y apellidos', autocomplete: 'name', autocapitalize: 'words',
      enterkeyhint: 'done', 'aria-label': 'Nombre',
    }) as HTMLInputElement;
    const opciones = el('div.opciones-letra', { role: 'radiogroup', 'aria-label': 'Tipo de letra' });
    const actualizar = () => {
      const texto = entrada.value.trim() || 'Tu firma';
      opciones.querySelectorAll<HTMLButtonElement>('button').forEach((b) => {
        b.querySelector('span')!.textContent = texto;
        b.setAttribute('aria-checked', String(b.dataset.letra === letra));
        b.style.color = color;
      });
    };
    for (const l of LETRAS) {
      opciones.append(el('button.opcion-letra', {
        type: 'button', role: 'radio', dataset: { letra: l.nombre }, style: { fontFamily: `"${l.nombre}", cursive` },
        onclick: () => { letra = l.nombre; actualizar(); },
      }, el('span')));
    }
    const colores = el('div.pad-colores', { role: 'radiogroup', 'aria-label': 'Color' });
    for (const c of COLORES_FIRMA) {
      colores.append(el('button.muestra-color', {
        type: 'button', role: 'radio', 'aria-checked': String(c === color), 'aria-label': `Color ${c}`, style: { '--color': c } as never,
        onclick: (ev: Event) => {
          color = c;
          colores.querySelectorAll('button').forEach((x) => x.setAttribute('aria-checked', String(x === ev.currentTarget)));
          actualizar();
        },
      }));
    }
    entrada.addEventListener('input', actualizar);
    void cargarLetras().then(actualizar);
    actualizar();
    abrirHoja({
      titulo: 'Escribir la firma',
      subtitulo: 'Se generará una rúbrica con letra caligráfica.',
      contenido: el('div.formulario', {}, entrada, opciones, el('div.fila-colores', {}, el('span.campo-etiqueta', {}, 'Color'), colores)),
      botones: [
        { texto: 'Cancelar', tipo: 'secundario' },
        {
          texto: 'Guardar firma', tipo: 'primario', icono: 'ok',
          accion: async () => {
            const nombre = entrada.value.trim();
            if (!nombre) {
              toast('Escribe tu nombre.');
              entrada.focus();
              return false;
            }
            await cargarLetras();
            const r = renderizarNombre(nombre, letra, color);
            if (!r) return false;
            resultado = await guardar(r);
            return true;
          },
        },
      ],
      alCerrar: () => resolver(resultado),
    });
    if (!esMovil()) window.setTimeout(() => entrada.focus(), 250);
  });
}

/** Pregunta cómo crear la firma (dibujarla o escribirla). */
export function nuevaFirma(): Promise<FirmaGuardada | null> {
  return new Promise((resolver) => {
    let eleccion: (() => Promise<FirmaGuardada | null>) | null = null;
    const opcion = (ico: 'lapiz' | 'teclado', titulo: string, detalle: string, fn: () => Promise<FirmaGuardada | null>) =>
      el('button.opcion-grande', {
        type: 'button', html: `${icono(ico, 26)}<span><strong>${titulo}</strong><small>${detalle}</small></span>`,
        onclick: () => { eleccion = fn; hoja.cerrar(); },
      });
    const hoja = abrirHoja({
      titulo: 'Nueva firma',
      contenido: el('div.lista-opciones', {},
        opcion('lapiz', 'Dibujarla', 'Con el dedo, el Apple Pencil o el trackpad', dibujarFirma),
        opcion('teclado', 'Escribir mi nombre', 'Con letra caligráfica', escribirFirma),
      ),
      alCerrar: () => {
        if (eleccion) void eleccion().then(resolver);
        else resolver(null);
      },
    });
  });
}

/** «Mis firmas»: elige una firma guardada (o crea una nueva). */
export function elegirFirma(titulo = 'Mis firmas', subtitulo = 'Toca una firma para colocarla en el documento.'): Promise<FirmaGuardada | null> {
  return new Promise((resolver) => {
    let elegida: FirmaGuardada | null = null;
    let crear = false;
    const rejilla = el('div.rejilla-firmas');
    const pintar = async () => {
      const lista = await almacen.firmas().catch(() => [] as FirmaGuardada[]);
      rejilla.replaceChildren();
      for (const f of lista) {
        const ficha = el('div.ficha-firma', {},
          el('button.ficha-firma-boton', {
            type: 'button', 'aria-label': 'Usar esta firma',
            onclick: () => { elegida = f; hoja.cerrar(); },
          }, el('img', { src: f.png, alt: 'Firma guardada' })),
          el('button.boton-icono.borrar-ficha', {
            type: 'button', 'aria-label': 'Eliminar esta firma', html: icono('papelera', 18),
            onclick: async () => {
              if (await confirmar('Eliminar la firma', 'Se borrará esta firma de este dispositivo.', 'Eliminar', true)) {
                await almacen.borrarFirma(f.id);
                void pintar();
              }
            },
          }),
        );
        rejilla.append(ficha);
      }
      rejilla.append(el('button.ficha-firma.nueva', {
        type: 'button', html: `${icono('mas2', 26)}<span>Nueva firma</span>`,
        onclick: () => { crear = true; hoja.cerrar(); },
      }));
    };
    void pintar();
    const hoja = abrirHoja({
      titulo,
      subtitulo,
      contenido: rejilla,
      alCerrar: () => {
        if (crear) void nuevaFirma().then(resolver);
        else resolver(elegida);
      },
    });
  });
}
