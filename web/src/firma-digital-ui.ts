/**
 * Interfaz de la firma con certificado digital (PAdES):
 * importar certificados .p12/.pfx, elegir aspecto (sello visible o invisible), motivo y
 * lugar, pedir la contraseña (que nunca se guarda) y firmar.
 */
import * as almacen from './almacen';
import type { CertGuardado, FirmaGuardada } from './almacen';
import type { Editor } from './editor';
import { compartirBytes, descargar } from './compartir';
import { icono } from './iconos';
import { nuevoId } from './modelo';
import { nuevaFirma } from './pad-firma';
import { firmarPdf } from './pdf/firma';
import { abrirP12, type Credencial } from './pdf/p12';
import { bytesDeDataUrl, fechaLegible } from './pdf/util';
import type { EstadoFirma } from './pdf/verificar';
import {
  abrirHoja, confirmar, el, elegirArchivo, escapar, fechaCorta, ocupado, pedirContrasena, pintar, toast,
} from './ui/componentes';

const TSA_PREDETERMINADA = 'https://freetsa.org/tsr';

function caducado(c: CertGuardado): boolean {
  return c.validoHasta < Date.now();
}

function fichaCert(c: CertGuardado): string {
  const venc = caducado(c)
    ? `<span class="texto-error">Caducó el ${fechaCorta(c.validoHasta)}</span>`
    : `Válido hasta el ${fechaCorta(c.validoHasta)}`;
  return `<strong>${escapar(c.titular)}</strong><small>Emitido por ${escapar(c.emisor)}</small><small>${venc}</small>`;
}

/** Importa un .p12/.pfx: pide la contraseña solo para leer los datos y guarda el archivo tal cual. */
export async function importarCertificado(): Promise<CertGuardado | null> {
  const archivo = await elegirArchivo(); // sin filtro: iOS a veces no reconoce el tipo .p12
  if (!archivo) return null;
  if (archivo.size > 2_000_000) {
    toast('El archivo es demasiado grande para ser un certificado .p12/.pfx.', { tipo: 'error' });
    return null;
  }
  const bytes = new Uint8Array(await archivo.arrayBuffer());
  let cred: Credencial | null = null;
  const c = await pedirContrasena({
    titulo: 'Importar certificado',
    mensaje: `Escribe la contraseña de «${archivo.name}» para leer sus datos. La contraseña no se guarda: se pedirá cada vez que firmes.`,
    textoBoton: 'Importar',
    validar: async (pwd) => {
      try {
        await pintar();
        cred = abrirP12(bytes, pwd);
        return null;
      } catch (e) {
        return (e as Error).message;
      }
    },
  });
  if (c === null || !cred) return null;
  const info = (cred as Credencial).info;
  const guardado: CertGuardado = {
    id: nuevoId(), nombreArchivo: archivo.name,
    p12: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer,
    titular: info.titular, emisor: info.emisor, validoDesde: info.validoDesde.getTime(), validoHasta: info.validoHasta.getTime(),
    numeroSerie: info.numeroSerie, nif: info.nif, fecha: Date.now(),
  };
  try {
    await almacen.guardarCertificado(guardado);
  } catch {
    toast('No se pudo guardar el certificado en este dispositivo.', { tipo: 'error' });
    return null;
  }
  toast(`Certificado importado: ${info.titular}`, { tipo: 'exito' });
  return guardado;
}

/** «Mis certificados»: lista, importar y eliminar. */
export async function hojaCertificados(): Promise<void> {
  const lista = el('div.lista-certs');
  const pintarLista = async () => {
    const certs = await almacen.certificados().catch(() => [] as CertGuardado[]);
    lista.replaceChildren();
    if (!certs.length) lista.append(el('p.vacio', {}, 'Aún no has importado ningún certificado.'));
    for (const c of certs) {
      lista.append(el('div.ficha-cert', {},
        el('span.icono-cert', { html: icono('certificado', 26) }),
        el('span.texto-cert', { html: fichaCert(c) }),
        el('button.boton-icono', {
          type: 'button', 'aria-label': `Eliminar el certificado de ${c.titular}`, html: icono('papelera', 20),
          onclick: async () => {
            if (await confirmar('Eliminar el certificado', `Se borrará de este dispositivo el certificado de ${c.titular}. El archivo original no se toca.`, 'Eliminar', true)) {
              await almacen.borrarCertificado(c.id);
              void pintarLista();
            }
          },
        }),
      ));
    }
  };
  await pintarLista();
  abrirHoja({
    titulo: 'Mis certificados',
    subtitulo: 'Se guardan en este dispositivo, cifrados con su contraseña.',
    contenido: lista,
    botones: [
      { texto: 'Cerrar', tipo: 'secundario' },
      { texto: 'Importar .p12 / .pfx', tipo: 'primario', icono: 'subir', accion: async () => { await importarCertificado(); await pintarLista(); return false; } },
    ],
  });
}

interface OpcionesElegidas {
  cert: CertGuardado;
  visible: boolean;
  rubrica: FirmaGuardada | null;
  motivo: string;
  lugar: string;
  tsa?: string;
}

async function hojaOpciones(ed: Editor): Promise<OpcionesElegidas | null> {
  let certs = await almacen.certificados().catch(() => [] as CertGuardado[]);
  let firmasM = await almacen.firmas().catch(() => [] as FirmaGuardada[]);
  const ultimoCert = await almacen.ajuste<string | null>('ultimoCert', null);
  let cert = certs.find((c) => c.id === ultimoCert) ?? certs[0] ?? null;
  let visible = await almacen.ajuste('selloVisible', true);
  const idRubrica = await almacen.ajuste<string | null>('rubricaSello', null);
  let rubrica: FirmaGuardada | null = idRubrica === 'ninguna' ? null : firmasM.find((f) => f.id === idRubrica) ?? firmasM[0] ?? null;
  const motivo = el('input', { type: 'text', placeholder: 'p. ej. Conformidad, Aprobación…', 'aria-label': 'Motivo', value: await almacen.ajuste('motivo', '') }) as HTMLInputElement;
  const lugar = el('input', { type: 'text', placeholder: 'p. ej. Córdoba', 'aria-label': 'Lugar', value: await almacen.ajuste('lugar', '') }) as HTMLInputElement;
  const usarTsa = el('input', { type: 'checkbox' }) as HTMLInputElement;
  const urlTsa = el('input', { type: 'url', value: await almacen.ajuste('urlTsa', TSA_PREDETERMINADA), 'aria-label': 'Servidor de sellado de tiempo', inputmode: 'url', autocapitalize: 'off' }) as HTMLInputElement;

  const zonaCerts = el('div.lista-certs.seleccionable', { role: 'radiogroup', 'aria-label': 'Certificado' });
  const pintarCerts = () => {
    zonaCerts.replaceChildren();
    if (!certs.length) {
      zonaCerts.append(el('p.vacio', {}, 'Importa tu certificado (.p12 o .pfx) una sola vez. En el iPhone puedes guardarlo antes en Archivos o iCloud Drive.'));
    }
    for (const c of certs) {
      zonaCerts.append(el('button.ficha-cert', {
        type: 'button', role: 'radio', 'aria-checked': String(c === cert),
        html: `<span class="icono-cert">${icono('certificado', 26)}</span><span class="texto-cert">${fichaCert(c)}</span><span class="marca-radio" aria-hidden="true"></span>`,
        onclick: () => { cert = c; pintarCerts(); },
      }));
    }
    zonaCerts.append(el('button.boton.texto.boton-importar', {
      type: 'button', html: `${icono('subir', 20)}<span>${certs.length ? 'Importar otro certificado' : 'Importar certificado (.p12 / .pfx)'}</span>`,
      onclick: async () => {
        const nuevo = await importarCertificado();
        if (nuevo) {
          certs = await almacen.certificados();
          cert = certs.find((c) => c.id === nuevo.id) ?? nuevo;
          pintarCerts();
        }
      },
    }));
  };
  pintarCerts();

  const zonaRubrica = el('div.rubricas', { role: 'radiogroup', 'aria-label': 'Rúbrica en el sello' });
  const pintarRubricas = () => {
    zonaRubrica.replaceChildren(
      el('button.opcion-rubrica', { type: 'button', role: 'radio', 'aria-checked': String(rubrica === null), onclick: () => { rubrica = null; pintarRubricas(); } }, 'Sin rúbrica'),
    );
    for (const f of firmasM) {
      zonaRubrica.append(el('button.opcion-rubrica', {
        type: 'button', role: 'radio', 'aria-checked': String(rubrica?.id === f.id), 'aria-label': 'Usar esta rúbrica',
        onclick: () => { rubrica = f; pintarRubricas(); },
      }, el('img', { src: f.png, alt: '' })));
    }
    zonaRubrica.append(el('button.opcion-rubrica.nueva', {
      type: 'button', 'aria-label': 'Nueva rúbrica', html: icono('mas2', 20),
      onclick: async () => {
        const f = await nuevaFirma();
        if (f) {
          firmasM = await almacen.firmas();
          rubrica = firmasM.find((x) => x.id === f.id) ?? f;
          pintarRubricas();
        }
      },
    }));
  };
  pintarRubricas();
  const filaRubrica = el('div.campo', {}, el('span.campo-etiqueta', {}, 'Rúbrica en el sello'), zonaRubrica);

  const segmento = el('div.segmentos', { role: 'radiogroup', 'aria-label': 'Aspecto de la firma' });
  const pintarSegmento = () => {
    segmento.replaceChildren(
      el('button.segmento', { type: 'button', role: 'radio', 'aria-checked': String(visible), onclick: () => { visible = true; pintarSegmento(); } }, 'Sello visible'),
      el('button.segmento', { type: 'button', role: 'radio', 'aria-checked': String(!visible), onclick: () => { visible = false; pintarSegmento(); } }, 'Firma invisible'),
    );
    filaRubrica.hidden = !visible;
    ayudaAspecto.textContent = visible
      ? 'Después dibujarás en la página el recuadro donde irá el sello.'
      : 'La firma no se ve en la página, pero los lectores de PDF la muestran en su panel de firmas.';
  };
  const ayudaAspecto = el('small.campo-ayuda');
  pintarSegmento();

  const avisos = el('div.avisos');
  if (ed.firmas.length) {
    avisos.append(el('p.nota', { html: `${icono('info', 18)}<span>El documento ya tiene ${ed.firmas.length} firma(s). La nueva se añadirá como actualización incremental, sin invalidar las anteriores.</span>` }));
  }
  if (ed.anotaciones.length) {
    avisos.append(el('p.nota', { html: `${icono('info', 18)}<span>Las ${ed.anotaciones.length} anotación(es) pendientes se incluirán en el documento antes de firmar.</span>` }));
  }

  const avanzado = el('details.avanzado', {},
    el('summary', {}, 'Opciones avanzadas'),
    el('label.casilla', {}, usarTsa, el('span', {}, 'Añadir un sello de tiempo de una TSA (necesita conexión)')),
    el('label.campo', {}, el('span.campo-etiqueta', {}, 'Servidor de sellado de tiempo (RFC 3161)'), urlTsa,
      el('small.campo-ayuda', {}, 'Desactivado por defecto. El servidor debe aceptar peticiones desde el navegador (CORS); si no, la firma fallará y podrás firmar sin sello de tiempo.')),
  );

  return new Promise((resolver) => {
    let resultado: OpcionesElegidas | null = null;
    abrirHoja({
      titulo: 'Firma con certificado digital',
      subtitulo: 'Firma electrónica PAdES · SHA-256',
      clase: 'hoja-ancha',
      contenido: el('div.formulario', {},
        el('h3.seccion', {}, 'Certificado'), zonaCerts,
        el('h3.seccion', {}, 'Aspecto'), segmento, ayudaAspecto, filaRubrica,
        el('h3.seccion', {}, 'Datos opcionales'),
        el('div.fila-campos', {}, el('label.campo', {}, el('span.campo-etiqueta', {}, 'Motivo'), motivo), el('label.campo', {}, el('span.campo-etiqueta', {}, 'Lugar'), lugar)),
        avisos, avanzado,
      ),
      botones: [
        { texto: 'Cancelar', tipo: 'secundario' },
        {
          texto: 'Continuar', tipo: 'primario', icono: 'pluma',
          accion: async () => {
            if (!cert) {
              toast('Primero importa tu certificado (.p12 o .pfx).');
              return false;
            }
            if (caducado(cert) && !(await confirmar('Certificado caducado', `El certificado de ${cert.titular} caducó el ${fechaCorta(cert.validoHasta)}. Una firma hecha con él no se considerará válida. ¿Firmar de todos modos?`, 'Firmar igualmente', true))) {
              return false;
            }
            resultado = {
              cert, visible, rubrica, motivo: motivo.value.trim(), lugar: lugar.value.trim(),
              tsa: usarTsa.checked && urlTsa.value.trim() ? urlTsa.value.trim() : undefined,
            };
            void almacen.fijarAjuste('ultimoCert', cert.id);
            void almacen.fijarAjuste('selloVisible', visible);
            void almacen.fijarAjuste('rubricaSello', rubrica?.id ?? 'ninguna');
            void almacen.fijarAjuste('motivo', resultado.motivo);
            void almacen.fijarAjuste('lugar', resultado.lugar);
            if (resultado.tsa) void almacen.fijarAjuste('urlTsa', resultado.tsa);
            return true;
          },
        },
      ],
      alCerrar: () => resolver(resultado),
    });
  });
}

function nombreFirmado(nombre: string): string {
  const base = nombre.replace(/\.pdf$/i, '');
  return /_firmado$/i.test(base) ? `${base}.pdf` : `${base}_firmado.pdf`;
}

export async function flujoFirmaDigital(ed: Editor): Promise<void> {
  const op = await hojaOpciones(ed);
  if (!op) return;

  let pagina: number | undefined;
  let caja: { x: number; y: number; w: number; h: number } | undefined;
  if (op.visible) {
    const r = await ed.pedirCajaFirma();
    if (!r) return;
    pagina = r.pagina;
    caja = r.caja;
  }

  let credencial: Credencial | null = null;
  const pwd = await pedirContrasena({
    titulo: 'Contraseña del certificado',
    mensaje: `Escribe la contraseña del certificado de ${op.cert.titular}. No se guarda en ningún sitio.`,
    textoBoton: 'Firmar',
    validar: async (c) => {
      try {
        await pintar();
        credencial = abrirP12(new Uint8Array(op.cert.p12), c);
        return null;
      } catch (e) {
        return (e as Error).message;
      }
    },
  });
  if (pwd === null || !credencial) return;

  const fin = ocupado(op.tsa ? 'Firmando y pidiendo el sello de tiempo…' : 'Firmando el documento…');
  await pintar();
  try {
    const base = await ed.bytesParaGuardar();
    const r = await firmarPdf(base, {
      credencial, pagina, caja, motivo: op.motivo || undefined, lugar: op.lugar || undefined,
      rubricaPng: op.visible && op.rubrica ? bytesDeDataUrl(op.rubrica.png) : undefined,
      urlTsa: op.tsa,
    });
    const nombre = nombreFirmado(ed.nombreArchivo());
    await ed.reemplazarDocumento(r.bytes, nombre);
    fin();
    const info = (credencial as Credencial).info;
    abrirHoja({
      titulo: 'Documento firmado',
      contenido: el('div.exito-firma', {},
        el('span.icono-exito', { html: icono('escudo', 40) }),
        el('p', { html: `Firmado digitalmente por <strong>${escapar(info.titular)}</strong>` }),
        el('p.texto-suave', {}, `${fechaLegible(new Date())} · campo ${r.campo}${r.firmasPrevias ? ` · ${r.firmasPrevias} firma(s) anterior(es) intacta(s)` : ''}`),
        el('p.texto-suave', {}, nombre),
      ),
      botones: [
        { texto: 'Guardar en Archivos', tipo: 'secundario', icono: 'descargar', accion: () => descargar(r.bytes, nombre) },
        { texto: 'Compartir', tipo: 'primario', icono: 'compartir', accion: () => compartirBytes(r.bytes, nombre) },
      ],
    });
  } catch (e) {
    fin();
    console.error(e);
    toast(`No se pudo firmar: ${(e as Error).message}`, { tipo: 'error', segundos: 7 });
  }
}

/** Detalle de las firmas digitales del documento. */
export function hojaFirmasDocumento(firmas: EstadoFirma[]): void {
  const lista = el('div.lista-firmas-doc');
  for (const f of firmas) {
    const estado = f.integra ? (f.cubreTodo ? 'Válida' : 'Válida, con cambios posteriores') : 'No válida';
    lista.append(el('div.firma-doc', { class: `firma-doc ${f.integra ? 'bien' : 'mal'}` },
      el('span.icono-estado', { html: icono(f.integra ? 'escudo' : 'escudoAlerta', 26) }),
      el('div', {},
        el('strong', {}, f.firmante),
        el('small', {}, `${estado} · ${f.campo}`),
        el('small', {}, `Emisor: ${f.emisor}`),
        f.fecha ? el('small', {}, `Fecha: ${fechaLegible(f.fecha)}`) : null,
        f.motivo ? el('small', {}, `Motivo: ${f.motivo}`) : null,
        f.lugar ? el('small', {}, `Lugar: ${f.lugar}`) : null,
        el('p.texto-suave', {}, f.resumen),
      ),
    ));
  }
  abrirHoja({
    titulo: 'Firmas del documento',
    subtitulo: 'Comprobación de integridad hecha en el dispositivo.',
    contenido: [lista, el('p.nota', { html: `${icono('info', 18)}<span>Se comprueba que el documento no se ha alterado desde cada firma. La identidad del firmante (cadena de confianza y revocación) no se verifica sin conexión: para ello usa Adobe Acrobat o VALIDe.</span>` })],
    botones: [{ texto: 'Cerrar', tipo: 'primario' }],
  });
}
