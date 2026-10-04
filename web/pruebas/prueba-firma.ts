/**
 * Prueba automatizada del flujo de anotación y firma con el MISMO código que usa la app
 * (src/pdf/*). Ejecutar con:  npm run prueba:firma
 *
 * Genera en pruebas/salida/:
 *   firmado.pdf                 ejemplo.pdf firmado con sello visible y rúbrica
 *   firmado_dos_veces.pdf       el anterior, firmado otra vez (firma invisible)
 *   anotado.pdf                 ejemplo.pdf con anotaciones aplanadas
 *   tres_firmas.pdf             dos firmas + anotaciones editables + una tercera firma
 *   xref_stream_firmado.pdf     PDF con flujos XRef y página girada 90°, firmado dos veces
 *   cien_paginas.pdf            documento de 100 páginas para probar el visor
 * y después valida cada archivo con pyHanko (entorno de la app de escritorio).
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateSync } from 'node:zlib';
import { degrees, PDFDocument, rgb, StandardFonts } from 'pdf-lib';
import type { Anotacion } from '../src/modelo';
import { aplicarAnotaciones } from '../src/pdf/anotaciones-pdf';
import { firmarPdf } from '../src/pdf/firma';
import { analizarCola } from '../src/pdf/incremental';
import { abrirP12 } from '../src/pdf/p12';
import { verificarFirmas } from '../src/pdf/verificar';

const aqui = dirname(fileURLToPath(import.meta.url));
const raizEscritorio = resolve(aqui, '../..');
const salida = join(aqui, 'salida');
mkdirSync(salida, { recursive: true });

let fallos = 0;
function comprobar(condicion: boolean, mensaje: string) {
  console.log(`${condicion ? '  ✔' : '  ✘'} ${mensaje}`);
  if (!condicion) fallos++;
}

/* --- PNG mínimo con una rúbrica de prueba (sin dependencias) ------------------- */
function crc32(buf: Uint8Array): number {
  let c = ~0;
  for (const b of buf) {
    c ^= b;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}
function trozo(tipo: string, datos: Uint8Array): Uint8Array {
  const t = new TextEncoder().encode(tipo);
  const out = new Uint8Array(12 + datos.length);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, datos.length);
  out.set(t, 4);
  out.set(datos, 8);
  dv.setUint32(8 + datos.length, crc32(out.subarray(4, 8 + datos.length)));
  return out;
}
function pngRubrica(w = 360, h = 140): Uint8Array {
  const px = new Uint8Array(w * h * 4);
  const pintar = (x: number, y: number) => {
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
      const xx = Math.round(x + dx), yy = Math.round(y + dy);
      if (xx < 0 || yy < 0 || xx >= w || yy >= h || dx * dx + dy * dy > 5) continue;
      const i = (yy * w + xx) * 4;
      px[i] = 15; px[i + 1] = 30; px[i + 2] = 110; px[i + 3] = 255;
    }
  };
  for (let t = 0; t <= 1; t += 0.0005) {
    const x = 20 + t * 320;
    const y = 70 + Math.sin(t * Math.PI * 5) * 40 * (1 - t * 0.5) + Math.cos(t * 23) * 6;
    pintar(x, y);
  }
  const filas = new Uint8Array(h * (w * 4 + 1));
  for (let y = 0; y < h; y++) filas.set(px.subarray(y * w * 4, (y + 1) * w * 4), y * (w * 4 + 1) + 1);
  const ihdr = new Uint8Array(13);
  const dv = new DataView(ihdr.buffer);
  dv.setUint32(0, w); dv.setUint32(4, h);
  ihdr[8] = 8; ihdr[9] = 6;
  const partes = [Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]), trozo('IHDR', ihdr),
    trozo('IDAT', new Uint8Array(deflateSync(filas))), trozo('IEND', new Uint8Array())];
  const total = partes.reduce((s, p) => s + p.length, 0);
  const png = new Uint8Array(total);
  let o = 0;
  for (const p of partes) { png.set(p, o); o += p.length; }
  return png;
}
const rubrica = pngRubrica();
const dataUrlRubrica = 'data:image/png;base64,' + Buffer.from(rubrica).toString('base64');
writeFileSync(join(salida, 'rubrica_prueba.png'), rubrica);

async function main() {
  const ejemplo = new Uint8Array(readFileSync(join(raizEscritorio, 'ejemplos/ejemplo.pdf')));
  const p12 = new Uint8Array(readFileSync(join(raizEscritorio, 'ejemplos/certificado_prueba.p12')));

  console.log('\n1) Certificado de prueba');
  let t = Date.now();
  const cred = abrirP12(p12, '1234');
  console.log(`   Titular: ${cred.info.titular} · Emisor: ${cred.info.emisor} · Caduca: ${cred.info.validoHasta.toISOString()} (${Date.now() - t} ms)`);
  comprobar(cred.info.titular === 'PRUEBA ESPAÑOL - 00000000T', 'titular leído correctamente (con «Ñ»)');
  let error = '';
  try { abrirP12(p12, 'mala'); } catch (e) { error = (e as Error).message; }
  comprobar(error === 'Contraseña incorrecta.', `contraseña incorrecta detectada («${error}»)`);

  console.log('\n2) Firma visible de ejemplo.pdf → firmado.pdf');
  t = Date.now();
  const r1 = await firmarPdf(ejemplo, {
    credencial: cred, pagina: 0, caja: { x: 300, y: 690, w: 260, h: 95 },
    motivo: 'Conformidad', lugar: 'Córdoba', rubricaPng: rubrica,
  });
  console.log(`   ${r1.campo}, ${r1.bytes.length} bytes (${Date.now() - t} ms)`);
  writeFileSync(join(salida, 'firmado.pdf'), r1.bytes);
  comprobar(r1.bytes.subarray(0, ejemplo.length).every((b, i) => b === ejemplo[i]), 'los bytes originales se conservan (actualización incremental)');

  console.log('\n3) Segunda firma (invisible) → firmado_dos_veces.pdf');
  const r2 = await firmarPdf(r1.bytes, { credencial: cred, motivo: 'Segunda firma de prueba' });
  writeFileSync(join(salida, 'firmado_dos_veces.pdf'), r2.bytes);
  comprobar(r2.campo === 'Firma2' && r2.firmasPrevias === 1, `campo ${r2.campo}, firmas previas: ${r2.firmasPrevias}`);

  console.log('\n4) Anotaciones aplanadas → anotado.pdf');
  const anots: Anotacion[] = [
    { id: 'a1', pagina: 0, tipo: 'resaltado', x: 60, y: 90, w: 300, h: 22, color: '#FFD60A' },
    { id: 'a2', pagina: 0, tipo: 'rectangulo', x: 50, y: 300, w: 200, h: 120, color: '#1C7ED6', grosor: 3 },
    { id: 'a3', pagina: 0, tipo: 'trazo', puntos: [80, 500, 120, 470, 160, 520, 200, 480, 240, 510], color: '#E03131', grosor: 2.5 },
    { id: 'a4', pagina: 1, tipo: 'texto', x: 70, y: 200, texto: 'Revisado — señal «ñandú» ¿sí?\nSegunda línea', tam: 14, color: '#8E1B2C' },
    { id: 'a5', pagina: 2, tipo: 'imagen', x: 320, y: 700, w: 180, h: 70, png: dataUrlRubrica },
  ];
  const anotado = await aplicarAnotaciones(ejemplo, anots, { aplanar: true });
  writeFileSync(join(salida, 'anotado.pdf'), anotado);
  const recargado = await PDFDocument.load(anotado);
  comprobar(recargado.getPageCount() === 3, 'el PDF anotado se vuelve a leer (3 páginas)');

  console.log('\n5) Anotaciones editables sobre un PDF ya firmado y tercera firma → tres_firmas.pdf');
  const conAnots = await aplicarAnotaciones(r2.bytes, anots.slice(0, 4), { aplanar: false });
  const r3 = await firmarPdf(conAnots, {
    credencial: cred, pagina: 1, caja: { x: 40, y: 40, w: 220, h: 80 }, motivo: 'Tercera', lugar: 'Madrid',
  });
  writeFileSync(join(salida, 'tres_firmas.pdf'), r3.bytes);

  console.log('\n6) PDF con flujos XRef (PDF 1.5) y página girada → xref_stream_firmado.pdf');
  const nuevo = await PDFDocument.create();
  const helv = await nuevo.embedFont(StandardFonts.Helvetica);
  for (let i = 0; i < 2; i++) {
    const p = nuevo.addPage([595, 842]);
    if (i === 1) p.setRotation(degrees(90));
    p.drawText(`Página ${i + 1} de prueba (flujos XRef${i === 1 ? ', girada 90°' : ''})`, { x: 60, y: 760, size: 18, font: helv, color: rgb(0.2, 0.1, 0.1) });
  }
  const xrefBytes = await nuevo.save({ useObjectStreams: true });
  comprobar(analizarCola(xrefBytes)?.esFlujo === true, 'el PDF de partida usa un flujo XRef');
  const x1 = await firmarPdf(xrefBytes, { credencial: cred, pagina: 1, caja: { x: 40, y: 400, w: 260, h: 90 }, rubricaPng: rubrica, motivo: 'Página girada' });
  const x2 = await firmarPdf(x1.bytes, { credencial: cred, pagina: 0, caja: { x: 300, y: 700, w: 250, h: 90 } });
  writeFileSync(join(salida, 'xref_stream_firmado.pdf'), x2.bytes);
  comprobar(analizarCola(x2.bytes)?.esFlujo === true, 'la actualización mantiene el formato de flujo XRef');

  console.log('\n7) Documento de 100 páginas (para el visor) → cien_paginas.pdf');
  const cien = await PDFDocument.create();
  const f = await cien.embedFont(StandardFonts.HelveticaBold);
  for (let i = 1; i <= 100; i++) {
    const p = cien.addPage([595, 842]);
    p.drawRectangle({ x: 40, y: 40, width: 515, height: 762, borderColor: rgb(0.56, 0.11, 0.17), borderWidth: 2 });
    p.drawText(`Página ${i}`, { x: 200, y: 420, size: 40, font: f, color: rgb(0.56, 0.11, 0.17) });
  }
  writeFileSync(join(salida, 'cien_paginas.pdf'), await cien.save());

  console.log('\n8) Verificación propia (src/pdf/verificar.ts, la que usa la app)');
  for (const nombre of ['firmado.pdf', 'firmado_dos_veces.pdf', 'tres_firmas.pdf', 'xref_stream_firmado.pdf']) {
    const res = await verificarFirmas(new Uint8Array(readFileSync(join(salida, nombre))));
    for (const r of res) console.log(`   ${nombre} · ${r.campo}: íntegra=${r.integra} cubre_todo=${r.cubreTodo} · ${r.firmante}`);
    comprobar(res.length > 0 && res.every((r) => r.integra), `${nombre}: todas las firmas íntegras (${res.length})`);
    comprobar(res[res.length - 1].cubreTodo, `${nombre}: la última firma cubre todo el documento`);
  }
  // Manipulación: cambiar un byte del contenido firmado debe invalidar la firma.
  const alterado = new Uint8Array(r1.bytes);
  const pos = alterado.indexOf(0x2f, 200); // un «/» cualquiera dentro del rango firmado
  alterado[pos + 1] ^= 0x01;
  const resAlt = await verificarFirmas(alterado);
  comprobar(resAlt.length === 1 && !resAlt[0].integra, `un documento alterado se detecta como no válido («${resAlt[0]?.resumen}»)`);

  console.log('\n9) Validación con pyHanko (entorno de escritorio)');
  const python = process.env.PYTHON ?? join(raizEscritorio, '.venv/bin/python');
  try {
    const out = execFileSync(python, [join(aqui, 'validar_pyhanko.py'), salida], { encoding: 'utf8', cwd: raizEscritorio });
    process.stdout.write(out);
    if (/FALLO/.test(out)) fallos++;
  } catch (e) {
    console.log('   No se pudo ejecutar pyHanko:', (e as Error).message);
    fallos++;
  }

  console.log(fallos ? `\n✘ ${fallos} comprobación(es) fallida(s)` : '\n✔ Todas las comprobaciones han pasado');
  process.exit(fallos ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
