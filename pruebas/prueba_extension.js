// Funciones de la extensión de Chrome que no dependen de Chrome.  Uso: node pruebas/prueba_extension.js
const assert = require("assert");
const path = require("path");
const u = require(path.join(__dirname, "..", "extension_chrome", "utilidades.js"));

const ID = "1AbCdEfGhIjKlMnOpQrStUv";
assert.strictEqual(u.idDeDrive(`https://drive.google.com/file/d/${ID}/view?usp=sharing`), ID);
assert.strictEqual(u.idDeDrive(`https://drive.google.com/file/u/1/d/${ID}/view`), ID);
assert.strictEqual(u.idDeDrive(`https://drive.google.com/open?id=${ID}`), ID);
assert.strictEqual(u.idDeDrive(`https://docs.google.com/file/d/${ID}/edit`), ID);
assert.strictEqual(u.idDeDrive("https://drive.google.com/drive/folders/abc"), null);
assert.strictEqual(u.idDeDrive("https://example.com/a.pdf"), null);
assert.ok(u.urlDescargaDrive(ID).endsWith(`id=${ID}`));

assert.strictEqual(u.nombreDeCabecera(`attachment; filename="a.pdf"; filename*=UTF-8''Contrato%20firmado%20%C3%B1.pdf`),
  "Contrato firmado ñ.pdf");
assert.strictEqual(u.nombreDeCabecera('inline; filename="Acta.pdf"'), "Acta.pdf");
assert.strictEqual(u.nombreDeCabecera("attachment; filename=Acta.pdf"), "Acta.pdf");
assert.strictEqual(u.nombreDeCabecera(null), null);
assert.strictEqual(u.nombreDeUrl("https://x.es/docs/Acta%20junio.pdf?v=2"), "Acta junio.pdf");
assert.strictEqual(u.nombreDeUrl("https://x.es/descargar?id=3"), null);
assert.strictEqual(u.nombreDeTitulo("Contrato.pdf - Google Drive"), "Contrato.pdf");
assert.strictEqual(u.nombreDeTitulo(""), null);

assert.ok(u.esPdf(new TextEncoder().encode("%PDF-1.7\n...")));
assert.ok(u.esPdf(new TextEncoder().encode("\n\n%PDF-1.4")));
assert.ok(!u.esPdf(new TextEncoder().encode("<!doctype html><html>")));
const bytes = new Uint8Array(100000).map((_, i) => (i * 7) % 256);
assert.strictEqual(u.aBase64(bytes), Buffer.from(bytes).toString("base64"));

assert.strictEqual(u.rutaDeArchivo("file:///Users/ana/Mis%20docs/a%C3%B1o.pdf"), "/Users/ana/Mis docs/año.pdf");
assert.strictEqual(u.rutaDeArchivo("file:///C:/Users/Ana/Doc%201.pdf"), "C:\\Users\\Ana\\Doc 1.pdf");
assert.strictEqual(u.rutaDeArchivo("file://servidor/compartida/a.pdf"), "\\\\servidor\\compartida\\a.pdf");
console.log("ok");
