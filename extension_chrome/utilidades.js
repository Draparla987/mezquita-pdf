// Funciones sin dependencias de Chrome (las prueba pruebas/prueba_chrome.py con Node).

/** Identificador del archivo si la dirección es de Google Drive; null si no lo es. */
function idDeDrive(url) {
  let m = /^https:\/\/(?:drive|docs)\.google\.com\/file\/(?:u\/\d+\/)?d\/([\w-]{10,})/.exec(url);
  if (m) return m[1];
  m = /^https:\/\/drive\.google\.com\/(?:open|uc)\?(?:[^#]*&)?id=([\w-]{10,})/.exec(url);
  return m ? m[1] : null;
}

function urlDescargaDrive(id) {
  return `https://drive.google.com/uc?export=download&id=${encodeURIComponent(id)}`;
}

/** Nombre del archivo según la cabecera Content-Disposition, o null. */
function nombreDeCabecera(cabecera) {
  if (!cabecera) return null;
  let m = /filename\*\s*=\s*utf-8''([^;]+)/i.exec(cabecera);
  if (m) {
    try {
      return decodeURIComponent(m[1].trim().replace(/^"|"$/g, ""));
    } catch (e) {
      // codificación rota: se prueba con el nombre sencillo
    }
  }
  m = /filename\s*=\s*"([^"]+)"/i.exec(cabecera) || /filename\s*=\s*([^;]+)/i.exec(cabecera);
  return m ? m[1].trim() : null;
}

/** Nombre del archivo según la dirección, si acaba en .pdf. */
function nombreDeUrl(url) {
  try {
    const ultimo = decodeURIComponent(new URL(url).pathname.split("/").pop() || "");
    return /\.pdf$/i.test(ultimo) ? ultimo : null;
  } catch (e) {
    return null;
  }
}

/** Nombre según el título de la pestaña («Contrato.pdf - Google Drive» → «Contrato.pdf»). */
function nombreDeTitulo(titulo) {
  return (titulo || "").replace(/\s+-\s+Google Drive$/, "").trim() || null;
}

/** ¿Empieza como un PDF? (la cabecera «%PDF» puede llegar tras algo de basura, hasta 1 KB) */
function esPdf(bytes) {
  const n = Math.min(bytes.length, 1024);
  for (let i = 0; i + 3 < n; i++) {
    if (bytes[i] === 0x25 && bytes[i + 1] === 0x50 && bytes[i + 2] === 0x44 && bytes[i + 3] === 0x46) return true;
  }
  return false;
}

function aBase64(bytes) {
  let texto = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    texto += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(texto);
}

/** Ruta en el ordenador de una dirección file:// (también C:\… y \\servidor\… en Windows). */
function rutaDeArchivo(url) {
  const u = new URL(url);
  let ruta = decodeURIComponent(u.pathname);
  if (u.host) return `\\\\${u.host}${ruta.replace(/\//g, "\\")}`;
  if (/^\/[A-Za-z]:\//.test(ruta)) ruta = ruta.slice(1).replace(/\//g, "\\");
  return ruta;
}

if (typeof module !== "undefined") {
  module.exports = { idDeDrive, urlDescargaDrive, nombreDeCabecera, nombreDeUrl, nombreDeTitulo, esPdf, aBase64, rutaDeArchivo };
}
