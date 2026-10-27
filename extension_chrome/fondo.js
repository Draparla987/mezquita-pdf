// Botón «Firmar con Mezquita PDF»: coge el PDF de la pestaña (o el archivo de Drive que se está
// viendo) y se lo pasa a la app por la mensajería nativa de Chrome. La app lo guarda en
// Descargas/Mezquita PDF y lo abre, listo para firmar. La firma la hace la app, con el certificado
// del ordenador: Chrome no tiene acceso a él.
importScripts("utilidades.js");

const ANFITRION = "es.mezquitapdf.chrome";
const MAX_PDF = 48 * 1024 * 1024; // Chrome admite mensajes de hasta 64 MB y el PDF va en base64
const TITULO = "Firmar con Mezquita PDF";

class Problema extends Error {
  constructor(motivo, detalle = "") {
    super(motivo);
    this.motivo = motivo;
    this.detalle = detalle;
  }
}

chrome.action.onClicked.addListener((pestana) => {
  abrirEnMezquita(pestana);
});

async function abrirEnMezquita(pestana) {
  await marcar(pestana.id, "…", "Pasando el PDF a Mezquita PDF…");
  try {
    const mensaje = await prepararMensaje(pestana.url || "", pestana.title || "");
    const respuesta = await enviar(mensaje);
    if (!respuesta || !respuesta.ok) throw new Problema("app", (respuesta && respuesta.error) || "");
    await marcar(pestana.id, "✓", "Abierto en Mezquita PDF");
    setTimeout(() => marcar(pestana.id, "", TITULO), 4000);
    return respuesta;
  } catch (e) {
    const problema = e instanceof Problema ? e : new Problema("otro", String((e && e.message) || e));
    await marcar(pestana.id, "!", TITULO);
    setTimeout(() => marcar(pestana.id, "", TITULO), 6000);
    const consulta = `motivo=${encodeURIComponent(problema.motivo)}&detalle=${encodeURIComponent(problema.detalle)}`;
    await chrome.tabs.create({ url: chrome.runtime.getURL(`ayuda.html?${consulta}`), index: pestana.index + 1 });
    return { ok: false, motivo: problema.motivo, detalle: problema.detalle };
  }
}

async function prepararMensaje(url, titulo) {
  if (url.startsWith("file://")) { // un PDF del propio ordenador: basta con su ruta
    const ruta = rutaDeArchivo(url);
    if (!/\.pdf$/i.test(ruta)) throw new Problema("noPdf");
    return { accion: "abrir_ruta", ruta };
  }
  if (!/^https?:\/\//.test(url)) throw new Problema(url.startsWith("blob:") ? "sinDireccion" : "noPdf");
  const id = idDeDrive(url);
  let respuesta;
  try {
    respuesta = await fetch(id ? urlDescargaDrive(id) : url, { credentials: "include" });
  } catch (e) {
    throw new Problema(id ? "drive" : "descarga", String((e && e.message) || e));
  }
  if (!respuesta.ok) throw new Problema(id ? "drive" : "descarga", `Error ${respuesta.status}`);
  if (Number(respuesta.headers.get("content-length") || 0) > MAX_PDF) throw new Problema("grande");
  const bytes = new Uint8Array(await respuesta.arrayBuffer());
  if (bytes.length > MAX_PDF) throw new Problema("grande");
  if (!esPdf(bytes)) throw new Problema(id ? "drive" : "noPdf");
  const nombre = nombreDeCabecera(respuesta.headers.get("content-disposition")) || nombreDeUrl(respuesta.url)
    || nombreDeUrl(url) || nombreDeTitulo(titulo) || "documento.pdf";
  return { accion: "abrir", nombre, datos: aBase64(bytes), origen: url };
}

function enviar(mensaje) {
  return new Promise((resolver, rechazar) => {
    chrome.runtime.sendNativeMessage(ANFITRION, mensaje, (respuesta) => {
      if (chrome.runtime.lastError) rechazar(new Problema("sinApp", chrome.runtime.lastError.message));
      else resolver(respuesta);
    });
  });
}

async function marcar(idPestana, texto, titulo) {
  try {
    await chrome.action.setBadgeBackgroundColor({ color: texto === "!" ? "#B3261E" : "#8E1B2C", tabId: idPestana });
    await chrome.action.setBadgeText({ text: texto, tabId: idPestana });
    await chrome.action.setTitle({ title: titulo, tabId: idPestana });
  } catch (e) {
    // la pestaña ya no existe
  }
}
