// Explica en la página de ayuda por qué no se ha podido abrir el PDF (motivo y detalle en la dirección).
const PROBLEMAS = {
  sinApp: ["No se ha encontrado Mezquita PDF en este ordenador",
    "Instala Mezquita PDF 2.11 o posterior y ábrelo una vez: al abrirse se conecta con Chrome. Después vuelve a pulsar el botón."],
  noPdf: ["Esta pestaña no muestra un PDF",
    "Abre el PDF en Chrome o en Google Drive y vuelve a pulsar el botón de Mezquita PDF."],
  sinDireccion: ["Este PDF no tiene una dirección desde la que descargarlo",
    "Lo ha creado la propia página. Descárgalo con el botón de descarga del visor y ábrelo en Mezquita PDF."],
  drive: ["No se ha podido descargar este archivo de Google Drive",
    "Comprueba que es un PDF, que tienes acceso a él y que su propietario permite descargarlo. Si lo estás viendo en la vista previa de una carpeta, ábrelo en su propia pestaña (⋮ → Abrir en una ventana nueva) y vuelve a pulsar el botón."],
  descarga: ["No se ha podido descargar el PDF",
    "Algunas webs solo dejan descargar el documento desde su propio botón. Descárgalo con el botón de descarga del visor y ábrelo en Mezquita PDF."],
  grande: ["El PDF es demasiado grande",
    "Desde Chrome se pueden pasar PDF de hasta 48 MB. Descárgalo y ábrelo en Mezquita PDF."],
  app: ["Mezquita PDF no ha podido abrir el documento", ""],
  otro: ["Algo ha fallado al pasar el PDF a Mezquita PDF", ""],
};

const datos = new URLSearchParams(location.search);
const problema = PROBLEMAS[datos.get("motivo")];
if (problema) {
  document.getElementById("problema").hidden = false;
  document.getElementById("problema-titulo").textContent = problema[0];
  document.getElementById("problema-texto").textContent = problema[1];
  const detalle = datos.get("detalle");
  if (detalle) {
    const nodo = document.getElementById("problema-detalle");
    nodo.textContent = detalle;
    nodo.hidden = false;
  }
}
if (/Mac/.test(navigator.platform || navigator.userAgent)) {
  document.getElementById("atajo").textContent = "⌥⇧F";
}
