/** Pantalla de bienvenida: friso de arcos, logotipo, «Abrir un PDF» y documentos recientes. */
import * as almacen from './almacen';
import type { DocReciente } from './almacen';
import { icono } from './iconos';
import { elegirFirma } from './pad-firma';
import { esNativo } from './nativo';
import { frisoSvg, NOMBRE_APP, VERSION } from './tema';
import { confirmar, el, fechaRelativa, tamLegible } from './ui/componentes';

export interface AccionesBienvenida {
  abrir: () => void;
  abrirReciente: (id: string) => void;
}

function esIosSinInstalar(): boolean {
  if (esNativo) return false; // ya es una app instalada
  const nav = navigator as Navigator & { standalone?: boolean };
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  return ios && nav.standalone === false;
}

export function crearBienvenida(acciones: AccionesBienvenida): HTMLElement {
  const friso = el('div.friso-contenedor', { 'aria-hidden': 'true' });
  const pintarFriso = () => { friso.innerHTML = frisoSvg(Math.max(320, friso.clientWidth || window.innerWidth)); };
  const observador = new ResizeObserver(pintarFriso);

  const recientes = el('section.recientes', { 'aria-label': 'Documentos recientes' });
  const pintarRecientes = async () => {
    let docs: DocReciente[] = [];
    try {
      docs = await almacen.recientes();
    } catch {
      /* sin IndexedDB (p. ej. navegación privada) */
    }
    recientes.replaceChildren();
    if (!docs.length) return;
    recientes.append(el('h2.seccion', {}, 'Recientes'));
    const lista = el('ul.lista-recientes');
    for (const d of docs.slice(0, 8)) {
      const etiquetas: string[] = [];
      if (d.firmado) etiquetas.push('<span class="etiqueta firmado">Firmado</span>');
      if (d.anotaciones?.length) etiquetas.push(`<span class="etiqueta">${d.anotaciones.length} ${d.anotaciones.length === 1 ? 'anotación' : 'anotaciones'}</span>`);
      const fila = el('li.fila-reciente', {},
        el('button.abrir-reciente', {
          type: 'button', title: d.nombre,
          html: `${icono('pdf', 30, 'icono-pdf')}<span class="textos-reciente"><span class="nombre-reciente">${d.nombre.replace(/[&<>]/g, '')}</span>` +
            `<span class="detalle-reciente">${tamLegible(d.tam)} · ${fechaRelativa(d.fecha)} ${etiquetas.join('')}</span></span>`,
          onclick: () => acciones.abrirReciente(d.id),
        }),
        el('button.boton-icono.quitar-reciente', {
          type: 'button', 'aria-label': `Quitar «${d.nombre}» de recientes`, title: 'Quitar de recientes', html: icono('cerrar', 18),
          onclick: async () => {
            if (await confirmar('Quitar de recientes', `Se borrará de este dispositivo la copia de «${d.nombre}» y sus anotaciones pendientes. El archivo original no se toca.`, 'Quitar', true)) {
              await almacen.borrarDocumento(d.id);
              void pintarRecientes();
            }
          },
        }),
      );
      lista.append(fila);
    }
    recientes.append(lista);
  };

  const abrir = el('button.boton.primario.grande', { type: 'button', html: `${icono('carpeta', 22)}<span>Abrir un PDF</span>`, onclick: acciones.abrir });
  const firmas = el('button.boton.secundario.grande', { type: 'button', html: `${icono('firma', 22)}<span>Mis firmas</span>`, onclick: () => void elegirFirma('Mis firmas', 'Se guardan solo en este dispositivo. Crea una nueva o borra las que no uses.') });

  const instalar = esIosSinInstalar() && !sessionStorage.getItem('ocultarInstalar')
    ? el('div.tarjeta-instalar', { role: 'note' },
      el('span', { html: icono('compartir', 22) }),
      el('p', { html: 'Para instalarla como app: pulsa <strong>Compartir</strong> y luego <strong>Añadir a pantalla de inicio</strong>.' }),
      el('button.boton-icono', { type: 'button', 'aria-label': 'Ocultar', html: icono('cerrar', 18), onclick: (e: Event) => { try { sessionStorage.setItem('ocultarInstalar', '1'); } catch { /* */ } (e.currentTarget as HTMLElement).parentElement?.remove(); } }))
    : null;

  const pantalla = el('section.pantalla-bienvenida', { 'aria-label': 'Inicio' },
    el('div.franja-estado', { 'aria-hidden': 'true' }),
    friso,
    el('div.bienvenida-contenido', {},
      el('div.bienvenida-centro', {},
        el('img.logo-grande', { src: './icons/logo-256.png', alt: '', width: '96', height: '96' }),
        el('h1.titulo-bienvenida', {}, NOMBRE_APP),
        el('p.subtitulo-bienvenida', {}, 'Abre, edita, firma y comparte tus documentos PDF'),
        el('div.acciones-bienvenida', {}, abrir, firmas),
        el('p.pista-arrastrar', {}, 'o arrastra un archivo PDF a esta ventana'),
        instalar,
      ),
      recientes,
    ),
    el('footer.pie-bienvenida', {}, `Versión ${VERSION} · inspirado en la Mezquita de Córdoba · todo se queda en tu dispositivo`),
  );
  requestAnimationFrame(() => {
    observador.observe(friso);
    pintarFriso();
  });
  void pintarRecientes();
  (pantalla as HTMLElement & { refrescar?: () => void }).refrescar = () => void pintarRecientes();
  return pantalla;
}
