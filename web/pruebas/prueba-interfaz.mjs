/**
 * Prueba de la interfaz con Playwright (playwright-core):
 *  - WebKit (motor de Safari) emulando un iPhone 390×844 @3x, en claro y en oscuro;
 *  - Google Chrome del sistema en un viewport de escritorio, en claro y en oscuro.
 *
 * Recorre: bienvenida → abrir PDF → anotar (resaltar, dibujar, rectángulo, texto) →
 * deshacer/rehacer → firma manuscrita (dibujada y colocada) → importar certificado →
 * firma digital con sello visible → descarga del PDF firmado; documento de 100 páginas
 * (renderizado perezoso); PDF con contraseña; y funcionamiento sin conexión (service worker).
 *
 * Requisitos: `npm run build` hecho, `npx playwright-core install webkit` y Chrome instalado.
 * Uso: npm run prueba:interfaz
 */
import { execFileSync, spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, webkit } from 'playwright-core';

const aqui = dirname(fileURLToPath(import.meta.url));
const raizWeb = resolve(aqui, '..');
const raizEscritorio = resolve(raizWeb, '..');
const salida = join(aqui, 'salida');
const capturas = join(salida, 'capturas');
mkdirSync(capturas, { recursive: true });
const EJEMPLO = join(raizEscritorio, 'ejemplos/ejemplo.pdf');
const P12 = join(raizEscritorio, 'ejemplos/certificado_prueba.p12');
const CIEN = join(salida, 'cien_paginas.pdf');
const PROTEGIDO = join(salida, 'protegido.pdf');
const PUERTO = 4319;
const URL_APP = `http://127.0.0.1:${PUERTO}/`;

let fallos = 0;
const ok = (c, m) => {
  console.log(`${c ? '  ✔' : '  ✘'} ${m}`);
  if (!c) fallos++;
};

// PDF protegido con contraseña (AES-256, contraseña «1234») creado con PyMuPDF.
if (!existsSync(PROTEGIDO)) {
  execFileSync(join(raizEscritorio, '.venv/bin/python'), ['-c',
    `import pymupdf; d=pymupdf.open(${JSON.stringify(EJEMPLO)}); d.save(${JSON.stringify(PROTEGIDO)}, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw='1234', owner_pw='propietario-1234')`]);
}
if (!existsSync(CIEN)) {
  console.log('Falta cien_paginas.pdf: ejecuta antes «npm run prueba:firma».');
  process.exit(1);
}

const servidor = spawn('npx', ['vite', 'preview', '--port', String(PUERTO), '--strictPort', '--host', '127.0.0.1'], { cwd: raizWeb, stdio: 'pipe' });
await new Promise((r, j) => {
  const t = setTimeout(() => j(new Error('El servidor no arrancó')), 20000);
  servidor.stdout.on('data', (d) => { if (String(d).includes(String(PUERTO))) { clearTimeout(t); r(); } });
});

async function abrirPdf(pagina, ruta) {
  const [selector] = await Promise.all([
    pagina.waitForEvent('filechooser'),
    pagina.getByRole('button', { name: 'Abrir un PDF' }).click(),
  ]);
  await selector.setFiles(ruta);
}

async function esperarLienzo(pagina, n = 1) {
  await pagina.waitForFunction((k) => document.querySelectorAll('canvas.lienzo-pdf').length >= k, n, { timeout: 20000 });
}

async function arrastrar(pagina, x0, y0, x1, y1, pasos = 12) {
  await pagina.mouse.move(x0, y0);
  await pagina.mouse.down();
  for (let i = 1; i <= pasos; i++) {
    await pagina.mouse.move(x0 + ((x1 - x0) * i) / pasos, y0 + ((y1 - y0) * i) / pasos + Math.sin(i) * 6);
  }
  await pagina.mouse.up();
}

async function cajaPagina(pagina, i = 0) {
  return pagina.locator('.pagina').nth(i).boundingBox();
}

async function infoDoc(pagina) {
  return (await pagina.locator('.info-doc').textContent()) ?? '';
}

async function recorrido(nombre, navegador, opcionesContexto, esMovil) {
  console.log(`\n▶ ${nombre}`);
  for (const esquema of ['light', 'dark']) {
    const ctx = await navegador.newContext({ ...opcionesContexto, colorScheme: esquema, acceptDownloads: true });
    const p = await ctx.newPage();
    const errores = [];
    p.on('pageerror', (e) => errores.push(String(e)));
    p.on('console', (m) => { if (m.type() === 'error' && !/service ?worker|sw\.js/i.test(m.text())) errores.push(m.text()); });
    await p.goto(URL_APP);
    await p.getByRole('button', { name: 'Abrir un PDF' }).waitFor();
    await p.waitForTimeout(400);
    await p.screenshot({ path: join(capturas, `${nombre}-${esquema}-bienvenida.png`) });

    await abrirPdf(p, EJEMPLO);
    await esperarLienzo(p, 1);
    await p.waitForTimeout(500);
    await p.screenshot({ path: join(capturas, `${nombre}-${esquema}-editor.png`) });
    ok((await p.locator('.texto-pagina').textContent()) === '1 / 3', `${esquema}: indicador de página «1 / 3»`);
    const dpr = await p.evaluate(() => {
      const c = document.querySelector('canvas.lienzo-pdf');
      return c.width / c.getBoundingClientRect().width;
    });
    ok(dpr > (opcionesContexto.deviceScaleFactor ?? 1) * 0.9, `${esquema}: lienzo nítido (${dpr.toFixed(2)} píxeles por px CSS)`);

    if (esquema === 'dark') {
      ok(errores.length === 0, `sin errores de JavaScript (${errores.join(' | ') || 'ninguno'})`);
      await ctx.close();
      continue;
    }

    // --- Anotaciones -------------------------------------------------------------
    if (!esMovil) {
      // En escritorio la página no cabe entera a lo alto: se ajusta a la página.
      await p.getByRole('button', { name: 'Ajustar a la página' }).click();
      await p.waitForTimeout(400);
      await p.screenshot({ path: join(capturas, `${nombre}-ajustar-pagina.png`) });
    }
    const c = await cajaPagina(p, 0);
    await p.getByRole('button', { name: 'Resaltar' }).click();
    await arrastrar(p, c.x + c.width * 0.07, c.y + c.height * 0.1, c.x + c.width * 0.6, c.y + c.height * 0.135, 4);
    await p.getByRole('button', { name: 'Dibujar' }).click();
    await arrastrar(p, c.x + c.width * 0.2, c.y + c.height * 0.5, c.x + c.width * 0.7, c.y + c.height * 0.55, 20);
    await p.getByRole('button', { name: 'Rectángulo' }).click();
    await arrastrar(p, c.x + c.width * 0.15, c.y + c.height * 0.62, c.x + c.width * 0.5, c.y + c.height * 0.75, 6);
    await p.getByRole('button', { name: 'Texto' }).click();
    await p.mouse.click(c.x + c.width * 0.1, c.y + c.height * 0.3);
    await p.locator('textarea').fill('Revisado en el iPhone — ñ, á, ¿?');
    await p.getByRole('button', { name: 'Añadir' }).click();
    await p.waitForTimeout(300);
    ok((await infoDoc(p)).includes('4 anotaciones'), `cuatro anotaciones creadas («${await infoDoc(p)}»)`);
    await p.screenshot({ path: join(capturas, `${nombre}-anotaciones.png`) });
    await p.getByRole('button', { name: 'Deshacer' }).click();
    ok((await infoDoc(p)).includes('3 anotaciones'), 'deshacer elimina la última');
    await p.getByRole('button', { name: 'Rehacer' }).click();
    ok((await infoDoc(p)).includes('4 anotaciones'), 'rehacer la recupera');

    // --- Firma manuscrita ---------------------------------------------------------
    await p.getByRole('button', { name: 'Firmar', exact: true }).click();
    await p.getByRole('button', { name: /Firma manuscrita/ }).click();
    await p.getByRole('button', { name: /Nueva firma/ }).click();
    await p.getByRole('button', { name: /Dibujarla/ }).click();
    const pad = await p.locator('.pad-lienzo').boundingBox();
    await arrastrar(p, pad.x + pad.width * 0.2, pad.y + pad.height * 0.6, pad.x + pad.width * 0.8, pad.y + pad.height * 0.5, 30);
    await p.screenshot({ path: join(capturas, `${nombre}-pad-firma.png`) });
    await p.locator('.pad-firma').getByRole('button', { name: 'Guardar' }).click();
    await p.waitForTimeout(400);
    const c2 = await cajaPagina(p, 0);
    await p.mouse.click(c2.x + c2.width * 0.7, c2.y + c2.height * 0.85);
    await p.waitForTimeout(300);
    ok((await p.locator('.capa-anotaciones image').count()) === 1, 'firma manuscrita colocada en la página');
    ok(await p.locator('.seleccion .asa').isVisible(), 'la firma queda seleccionada para moverla o redimensionarla');
    // Moverla arrastrando el recuadro de selección
    const sel = await p.locator('.seleccion').boundingBox();
    await arrastrar(p, sel.x + sel.width / 2, sel.y + sel.height / 2, sel.x + sel.width / 2 - 40, sel.y + sel.height / 2 - 30, 5);
    const sel2 = await p.locator('.seleccion').boundingBox();
    ok(Math.abs(sel2.x - (sel.x - 40)) < 4, 'la firma se mueve arrastrándola');
    await p.screenshot({ path: join(capturas, `${nombre}-firma-manuscrita.png`) });
    await p.getByRole('button', { name: 'Hecho' }).click();

    // --- Firma digital con certificado ---------------------------------------------
    await p.getByRole('button', { name: 'Firmar', exact: true }).click();
    await p.getByRole('button', { name: /Firma con certificado digital/ }).click();
    const [selP12] = await Promise.all([
      p.waitForEvent('filechooser'),
      p.getByRole('button', { name: /Importar certificado/ }).click(),
    ]);
    await selP12.setFiles(P12);
    await p.locator('input[type="password"]').fill('mala');
    await p.getByRole('button', { name: 'Importar', exact: true }).click();
    await p.locator('.error-campo', { hasText: 'Contraseña incorrecta' }).waitFor();
    ok(true, 'contraseña incorrecta del .p12 detectada');
    await p.locator('input[type="password"]').fill('1234');
    await p.getByRole('button', { name: 'Importar', exact: true }).click();
    await p.locator('.ficha-cert', { hasText: 'PRUEBA ESPAÑOL' }).first().waitFor();
    ok(true, 'certificado importado: titular «PRUEBA ESPAÑOL - 00000000T» visible');
    await p.locator('input[aria-label="Motivo"]').fill('Conformidad');
    await p.locator('input[aria-label="Lugar"]').fill('Córdoba');
    await p.screenshot({ path: join(capturas, `${nombre}-opciones-firma.png`) });
    await p.getByRole('button', { name: 'Continuar' }).click();
    await p.waitForTimeout(400);
    const c3 = await cajaPagina(p, 0);
    await p.evaluate(() => document.querySelector('.visor').scrollTo(0, 0));
    await arrastrar(p, c3.x + c3.width * 0.45, c3.y + c3.height * 0.86, c3.x + c3.width * 0.95, c3.y + c3.height * 0.97, 6);
    await p.locator('input[type="password"]').fill('1234');
    await p.getByRole('button', { name: 'Firmar', exact: true }).last().click();
    await p.getByText('Documento firmado').waitFor({ timeout: 20000 });
    await p.screenshot({ path: join(capturas, `${nombre}-firmado.png`) });
    const [descarga] = await Promise.all([
      p.waitForEvent('download'),
      p.getByRole('button', { name: 'Guardar en Archivos' }).click(),
    ]);
    const destino = join(salida, `firmado_desde_interfaz_${nombre}.pdf`);
    await descarga.saveAs(destino);
    ok(descarga.suggestedFilename() === 'ejemplo_firmado.pdf', `descarga «${descarga.suggestedFilename()}»`);
    await p.locator('.aviso-firmas.bien').waitFor({ timeout: 10000 });
    ok((await p.locator('.aviso-firmas').textContent()).includes('PRUEBA ESPAÑOL'), 'aviso verde «Firmado digitalmente por…» al recargar el documento firmado');
    await p.screenshot({ path: join(capturas, `${nombre}-aviso-firma.png`) });

    // --- Compartir: sin menú del sistema (navegador de prueba) se descarga ------------
    const puedeCompartir = await p.evaluate(() => !!navigator.canShare);
    if (!puedeCompartir) {
      const [descarga2] = await Promise.all([
        p.waitForEvent('download'),
        p.locator('.boton-compartir').click(),
      ]);
      ok(descarga2.suggestedFilename() === 'ejemplo_firmado.pdf', 'Compartir sin navigator.share descarga el PDF');
    }

    // --- Recientes: el original conserva sus anotaciones pendientes -----------------
    await p.getByRole('button', { name: 'Volver al inicio' }).click();
    await p.locator('.fila-reciente').first().waitFor();
    const recientes = await p.locator('.nombre-reciente').allTextContents();
    ok(recientes[0] === 'ejemplo_firmado.pdf' && recientes.includes('ejemplo.pdf'), `recientes: ${recientes.join(', ')}`);
    await p.locator('.abrir-reciente', { hasText: /^ejemplo\.pdf/ }).click();
    await esperarLienzo(p, 1);
    await p.waitForTimeout(300);
    ok((await infoDoc(p)).includes('5 anotaciones'), `al reabrir se recuperan las anotaciones («${await infoDoc(p)}»)`);

    // --- Documento de 100 páginas -----------------------------------------------------
    await p.getByRole('button', { name: 'Volver al inicio' }).click();
    await abrirPdf(p, CIEN);
    await esperarLienzo(p, 1);
    ok((await p.locator('.texto-pagina').textContent()) === '1 / 100', 'documento de 100 páginas abierto');
    const t0 = Date.now();
    await p.evaluate(() => {
      const v = document.querySelector('.visor');
      const pag = document.querySelectorAll('.pagina')[49];
      v.scrollTop = pag.offsetTop + 20;
    });
    await p.waitForFunction(() => document.querySelector('.texto-pagina').textContent === '50 / 100');
    await p.waitForFunction(() => document.querySelector('.pagina[data-indice="49"] canvas') !== null, null, { timeout: 15000 });
    const lienzos = await p.locator('canvas.lienzo-pdf').count();
    ok(lienzos <= 9, `renderizado perezoso: ${lienzos} lienzos vivos de 100 páginas (página 50 pintada en ${Date.now() - t0} ms)`);
    const ancho0 = (await cajaPagina(p, 49)).width;
    await p.locator('.indicador-pagina').getByRole('button', { name: 'Ampliar' }).click();
    await p.waitForTimeout(300);
    const ancho1 = (await cajaPagina(p, 49)).width;
    ok(ancho1 > ancho0 * 1.2, `botón de zoom: ${Math.round(ancho0)} → ${Math.round(ancho1)} px`);
    ok((await p.locator('.texto-pagina').textContent()) === '50 / 100', 'el zoom mantiene la página actual');

    // --- PDF con contraseña -------------------------------------------------------------
    await p.getByRole('button', { name: 'Volver al inicio' }).click();
    await abrirPdf(p, PROTEGIDO);
    await p.getByText('Documento protegido').waitFor();
    await p.locator('input[type="password"]').fill('0000');
    await p.getByRole('button', { name: 'Abrir', exact: true }).click();
    await p.getByText('La contraseña no es correcta').waitFor();
    await p.locator('input[type="password"]').fill('1234');
    await p.getByRole('button', { name: 'Abrir', exact: true }).click();
    await esperarLienzo(p, 1);
    ok(true, 'PDF con contraseña: se pide, se rechaza la incorrecta y se abre con la buena');

    ok(errores.length === 0, `sin errores de JavaScript (${errores.join(' | ') || 'ninguno'})`);
    await ctx.close();
  }
}

async function pruebaSinConexion(navegador) {
  console.log('\n▶ Sin conexión (service worker, Chrome)');
  const ctx = await navegador.newContext({ viewport: { width: 1100, height: 760 } });
  const p = await ctx.newPage();
  await p.goto(URL_APP);
  await p.evaluate(async () => {
    const reg = await navigator.serviceWorker.ready;
    return reg.active?.state;
  });
  // Espera a que el precache termine (el SW se activa al acabar la instalación).
  await p.waitForFunction(async () => {
    const claves = await caches.keys();
    for (const k of claves) {
      const c = await caches.open(k);
      if ((await c.keys()).length > 150) return true;
    }
    return false;
  }, null, { timeout: 30000 });
  const total = await p.evaluate(async () => {
    let n = 0;
    for (const k of await caches.keys()) n += (await (await caches.open(k)).keys()).length;
    return n;
  });
  ok(total > 150, `precache del service worker: ${total} recursos`);
  await ctx.setOffline(true);
  await p.reload();
  await p.getByRole('button', { name: 'Abrir un PDF' }).waitFor({ timeout: 10000 });
  ok(true, 'la app carga sin conexión');
  await abrirPdf(p, EJEMPLO);
  await esperarLienzo(p, 1);
  ok(true, 'sin conexión se abre y pinta un PDF (pdf.js y su worker desde la caché)');
  const peticionesExternas = [];
  p.on('request', (r) => { if (!r.url().startsWith(URL_APP) && !r.url().startsWith('blob:') && !r.url().startsWith('data:')) peticionesExternas.push(r.url()); });
  await p.reload();
  await p.waitForTimeout(500);
  ok(peticionesExternas.length === 0, `ninguna petición a otros dominios (${peticionesExternas.length})`);
  await ctx.close();
}

async function pruebaPellizco(navegador) {
  console.log('\n▶ Pellizco con dos dedos (eventos táctiles reales vía CDP, Chrome móvil)');
  const ctx = await navegador.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
  const p = await ctx.newPage();
  await p.goto(URL_APP);
  await abrirPdf(p, EJEMPLO);
  await esperarLienzo(p, 1);
  const cdp = await ctx.newCDPSession(p);
  const antes = (await cajaPagina(p, 0)).width;
  const cx = 195, cy = 380;
  const toque = (type, d) => cdp.send('Input.dispatchTouchEvent', {
    type, touchPoints: type === 'touchEnd' ? [] : [{ x: cx - d, y: cy, id: 1 }, { x: cx + d, y: cy, id: 2 }],
  });
  await toque('touchStart', 40);
  for (let d = 45; d <= 100; d += 5) await toque('touchMove', d);
  await toque('touchEnd', 100);
  await p.waitForTimeout(500);
  const despues = (await cajaPagina(p, 0)).width;
  ok(despues > antes * 2.2, `el pellizco amplía la página: ${Math.round(antes)} → ${Math.round(despues)} px (×${(despues / antes).toFixed(2)})`);
  await p.waitForFunction(() => {
    const c = document.querySelector('.pagina[data-indice="0"] canvas');
    return c && c.width / c.getBoundingClientRect().width > 2.5;
  }, null, { timeout: 10000 }).then(() => ok(true, 'tras el pellizco la página se vuelve a pintar nítida'), () => ok(false, 'tras el pellizco la página se vuelve a pintar nítida'));
  await ctx.close();
}

try {
  const wk = await webkit.launch();
  await recorrido('iphone-webkit', wk, {
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
  }, true);
  await wk.close();
  const ch = await chromium.launch({ channel: 'chrome' });
  await recorrido('escritorio-chrome', ch, { viewport: { width: 1280, height: 820 }, deviceScaleFactor: 2 }, false);
  await pruebaPellizco(ch);
  await pruebaSinConexion(ch);
  await ch.close();
} catch (e) {
  console.error(e);
  fallos++;
} finally {
  servidor.kill();
}
console.log(fallos ? `\n✘ ${fallos} comprobación(es) fallida(s)` : '\n✔ Todas las comprobaciones de interfaz han pasado');
process.exit(fallos ? 1 : 0);
