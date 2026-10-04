// Copia los recursos de pdf.js que se cargan en tiempo de ejecución (tablas CMap para
// textos CJK, fuentes estándar no incrustadas, decodificadores WebAssembly de JPEG 2000
// y JBIG2, y perfiles de color) a public/pdfjs/, para servirlos desde la propia app y
// que el service worker los guarde para trabajar sin conexión. Nada se pide a una CDN.
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const raiz = join(dirname(fileURLToPath(import.meta.url)), '..');
const origen = join(raiz, 'node_modules/pdfjs-dist');
const destino = join(raiz, 'public/pdfjs');
if (!existsSync(origen)) {
  console.error('Falta node_modules/pdfjs-dist: ejecuta «npm install».');
  process.exit(1);
}
rmSync(destino, { recursive: true, force: true });
mkdirSync(destino, { recursive: true });
for (const carpeta of ['cmaps', 'standard_fonts', 'iccs']) {
  cpSync(join(origen, carpeta), join(destino, carpeta), { recursive: true });
}
mkdirSync(join(destino, 'wasm'));
for (const f of ['openjpeg.wasm', 'openjpeg_nowasm_fallback.js', 'jbig2.wasm', 'jbig2_nowasm_fallback.js',
  'qcms_bg.wasm', 'LICENSE_OPENJPEG', 'LICENSE_JBIG2', 'LICENSE_QCMS', 'LICENSE_PDFJS_OPENJPEG',
  'LICENSE_PDFJS_JBIG2', 'LICENSE_PDFJS_QCMS']) {
  cpSync(join(origen, 'wasm', f), join(destino, 'wasm', f));
}
console.log('Recursos de pdf.js copiados en public/pdfjs/');
