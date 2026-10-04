# Mezquita PDF · versión web (PWA)

Visor, editor y firmador de PDF que se instala en el iPhone como una app (y funciona también en
el navegador del Mac). Es la versión web de la app de escritorio de esta misma carpeta, con el
mismo aspecto: granate y crema, arcos de herradura de la Mezquita de Córdoba, modo claro y oscuro.

**Todo ocurre en el dispositivo.** No hay servidor, ni cuentas, ni analítica, ni CDN: las
librerías van empaquetadas y, una vez cargada, la app funciona sin conexión. La única llamada de
red posible es el sello de tiempo (TSA), que está desactivado por defecto.

## Qué hace

| Ver | Anotar | Firmar | Compartir |
|---|---|---|---|
| Desplazamiento continuo, zoom con pellizco, Ctrl/⌘ + rueda y botones | Resaltar (arrastrando un recuadro sobre el texto) | Firma manuscrita: dibujada a pantalla completa (dedo o Apple Pencil, sensible a la presión) o escrita con letra caligráfica | Botón **Compartir**: menú del sistema (WhatsApp, Mail, AirDrop…) |
| Nitidez Retina y renderizado perezoso (solo las páginas visibles) | Texto libre, dibujo a mano alzada, rectángulos | Firmas guardadas para reutilizarlas; se colocan con un toque y se mueven/redimensionan | **Guardar en Archivos** (descarga) |
| Indicador «3 / 12» e «Ir a la página» | Seleccionar, mover, redimensionar y borrar anotaciones | Firma digital **PAdES** con certificado `.p12`/`.pfx`, con sello visible (rúbrica + datos) o invisible | Documentos recientes (se reabren con sus anotaciones pendientes) |
| PDF con contraseña (se pide al abrir) | Deshacer / rehacer, «Borrar última» | Varias firmas seguidas sin invalidar las anteriores | |
| Aviso verde/rojo con la comprobación de las firmas del documento | Al guardar: anotaciones aplanadas (por defecto) o editables | Motivo, lugar y sello de tiempo opcional | |

## Desarrollo

Requisitos: **Node 22** y npm.

```sh
cd web
npm install
npm run dev          # http://localhost:5173 (copia antes los recursos de pdf.js a public/pdfjs)
```

`npm run dev -- --host` la sirve también en la red local para abrirla desde el iPhone, pero por
`http://` Safari no activa el *service worker* (sin modo sin conexión) ni WebCrypto; la app
funciona igualmente (usa node-forge para SHA-256), salvo los certificados de curva elíptica.

## Construir

```sh
npm run build        # comprueba tipos (tsc) y genera dist/
npm run preview      # sirve dist/ en http://localhost:4173
```

`dist/` es una web estática con rutas relativas (`base: './'`): se puede servir desde cualquier
carpeta de cualquier alojamiento **HTTPS** (GitHub Pages, Netlify, un NAS…). HTTPS es
imprescindible para el *service worker* y para WebCrypto.

Los iconos (`public/icons/`) se generan a partir de `../recursos/icono.png` con
`npm run iconos` (usa `sips` de macOS y el Pillow del entorno virtual de escritorio para quitar
las transparencias, que iOS pintaría de negro).

## Instalarla en el iPhone

1. Abre la dirección donde la hayas publicado en **Safari** (con conexión, la primera vez).
2. Pulsa **Compartir** (el cuadrado con la flecha) → **Añadir a pantalla de inicio** → **Añadir**.
3. Ábrela desde su icono: se abre a pantalla completa, como una app, y ya funciona sin conexión.

Para abrir un PDF, **Abrir un PDF** muestra la app Archivos (iCloud Drive, En mi iPhone…). Para
firmar con certificado, guarda antes tu `.p12`/`.pfx` en Archivos: se importa una sola vez y la
contraseña se pide en cada firma (nunca se guarda). Cuando hay una versión nueva, la app lo avisa
con un botón **Actualizar**.

## Firma digital: detalles técnicos

- **Formato**: PAdES con `/SubFilter /ETSI.CAdES.detached`, `/Filter /Adobe.PPKLite`, resumen
  SHA-256 sobre los rangos de `/ByteRange` y firma CMS separada (SignedData) con los atributos
  firmados `contentType`, `messageDigest`, `signingTime` y `signingCertificateV2` (ESS, RFC 5035),
  incluyendo todos los certificados de la cadena del `.p12`. Claves RSA (PKCS#1 v1.5) y, con
  WebCrypto, ECDSA P-256/384/521.
- **Librerías**: el CMS se construye a mano con el ASN.1 de **node-forge** (que también abre
  los `.p12`, tanto con cifrado moderno AES/PBKDF2 como con el antiguo 3DES/RC2 del Llavero y
  Firefox), **pdf-lib** como modelo de objetos PDF y **pdf.js** (versión *legacy*, compatible
  con Safari 16) para mostrar las páginas.
- **Actualización incremental**: pdf-lib solo sabe reescribir el archivo entero, lo que
  rompería las firmas existentes. Por eso `src/pdf/incremental.ts` toma una «huella» de cada
  objeto al cargar, aplica los cambios con pdf-lib y **añade al final del archivo original**
  solo los objetos nuevos o modificados, con su propia tabla de referencias (clásica o flujo
  XRef, igual que el original) y `/Prev`. Los bytes originales no cambian, así que cada firma
  previa sigue siendo válida. Las anotaciones se escriben igual; si el documento ya está firmado
  se guardan como anotaciones PDF (cambio permitido tras firmar) en lugar de aplanarse.
- **Sello visible**: rúbrica guardada a la izquierda y, a la derecha, «Firmado digitalmente por:
  / titular / Fecha / Motivo / Lugar» con texto vectorial (Helvetica), como en escritorio.

## Pruebas

```sh
npm run prueba:firma      # firma con el MISMO código de la app y valida con pyHanko
npm run build && npm run prueba:interfaz
```

- `prueba:firma` (Node + tsx) firma `../ejemplos/ejemplo.pdf` con
  `../ejemplos/certificado_prueba.p12` (contraseña `1234`), lo firma una segunda vez, añade
  anotaciones y una tercera firma, prueba un PDF con flujos XRef y una página girada, y valida
  cada resultado con la verificación propia de la app y con **pyHanko** (entorno virtual de la
  app de escritorio, `../.venv`). Los resultados quedan en `pruebas/salida/`.
- `prueba:interfaz` (playwright-core) recorre la app en **WebKit** emulando un iPhone 390×844 y
  en el **Chrome** del sistema (escritorio), en claro y en oscuro: abrir, anotar, deshacer,
  firma manuscrita, importar certificado, firma digital con sello visible, descarga, recientes,
  100 páginas, PDF con contraseña, pellizco con dos dedos y funcionamiento sin conexión.
  Necesita `npx playwright-core install webkit` y Google Chrome. Guarda capturas en
  `pruebas/salida/capturas/`.

## Estructura

```
index.html               Metaetiquetas de iOS (pantalla completa, barra de estado, icono)
vite.config.ts           Vite + vite-plugin-pwa (manifiesto y service worker con precarga)
src/main.ts              Arranque, navegación, abrir archivos, service worker
src/bienvenida.ts        Pantalla de bienvenida (friso de arcos, recientes)
src/editor.ts            Editor: barras, herramientas, historial, compartir
src/visor.ts             pdf.js: páginas perezosas, Retina, zoom y pellizco
src/capa.ts              Capa SVG de anotaciones e interacción (Pointer Events)
src/pad-firma.ts         Firma manuscrita dibujada o escrita; «Mis firmas»
src/firma-digital-ui.ts  Certificados, opciones de firma, contraseña y verificación
src/compartir.ts         navigator.share / descarga
src/almacen.ts           IndexedDB (recientes, firmas, certificados, ajustes)
src/tema.ts, iconos.ts   Arco de herradura en SVG e iconos de trazo
src/estilos.css          Paleta clara/oscura, safe areas, diseño adaptable
src/pdf/                 Núcleo sin DOM (se usa también en las pruebas de Node):
  incremental.ts           escritura por actualización incremental
  anotaciones-pdf.ts       anotaciones → PDF (aplanadas o editables)
  firma.ts, cms.ts         firma PAdES y CMS
  p12.ts                   lectura de .p12/.pfx
  sello.ts                 apariencia del sello visible
  verificar.ts             comprobación de integridad de las firmas
  geometria.ts             conversión de coordenadas (igual que pdf.js)
scripts/                 Iconos y copia de recursos de pdf.js
pruebas/                 Pruebas automáticas
```

## Limitaciones conocidas

- **PDF cifrados** (con contraseña): se pueden ver, pero no anotar ni firmar.
- La comprobación de firmas verifica la **integridad** (que el documento no ha cambiado) pero no
  la **confianza** en el emisor ni la revocación (OCSP/CRL): para eso, Adobe Acrobat o VALIDe.
- **Anotar un documento ya firmado** no invalida las firmas, pero algunos validadores lo señalan:
  Adobe indica «cambios posteriores permitidos»; pyHanko lo clasifica como modificación no
  reconocida porque su análisis de diferencias no contempla anotaciones.
- `signingTime` va incluido porque así se pidió; el perfil estricto PAdES *baseline* (ETSI EN
  319 142-1) recomienda omitirlo y usar `/M`. Se puede desactivar con la opción
  `incluirHoraFirma: false` de `firmarPdf`.
- **Sello de tiempo**: la TSA debe aceptar peticiones del navegador (CORS); muchas no lo hacen.
  No se ha probado contra una TSA real. **ECDSA** está implementado pero no se ha probado con un
  certificado real de curva elíptica. No se puede firmar con el **DNIe** ni con tarjetas (el
  navegador no tiene acceso a PKCS#11): hace falta el certificado exportado a `.p12`.
- El texto añadido usa Helvetica (WinAnsi): los caracteres fuera del alfabeto latino se
  sustituyen. El resaltado es un recuadro (no se ajusta a las líneas de texto) y no hay
  selección ni búsqueda de texto, ni edición del texto original, ni reordenación de páginas.
- En iOS, **Compartir** necesita un toque reciente: si preparar el PDF tarda, aparece una hoja
  con el botón «Compartir…» para un segundo toque. En modo app, «Guardar en Archivos» abre la
  vista previa de la descarga; desde ahí, «Guardar en Archivos» del menú Compartir.
- Safari puede borrar los datos de una web que no se usa en semanas; instalada en la pantalla
  de inicio el riesgo es menor (la app pide almacenamiento persistente). Los recientes guardan
  una copia de cada documento (máximo 12).
- El pellizco se ha probado con eventos táctiles simulados en Chrome (emulación móvil), no en
  un iPhone físico. Con zoom muy alto, cada página se pinta con un máximo de 10 megapíxeles en móviles
  (límite de memoria de iOS), por lo que puede verse algo menos nítida.
