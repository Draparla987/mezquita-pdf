# Mezquita PDF

Visor y editor de PDF para **Mac e iPhone**, al estilo de Adobe Reader, con **firma manuscrita**,
**firma electrónica con certificado digital** (FNMT, ACCV, Izenpe, Camerfirma…) y opciones
para **compartir por correo o WhatsApp**. Su imagen (granate y crema, arcos de herradura) se
inspira en la Mezquita de Córdoba; se adapta automáticamente al modo claro u oscuro del Mac.

## Instalar en el Mac

1. Abre **`MezquitaPDF.dmg`** (o descárgalo de la pestaña *Actions* del repositorio: elige
   `MezquitaPDF-apple-silicon` para Mac con chip M1/M2/M3… o `MezquitaPDF-intel`).
2. Arrastra **Mezquita PDF** a la carpeta **Aplicaciones**.
3. Ábrela desde Aplicaciones o Launchpad. Si macOS avisa de que no puede comprobar el
   desarrollador (pasa con el `.dmg` descargado de GitHub): clic derecho sobre la app →
   **Abrir** → **Abrir**. Solo la primera vez.

Atajo para quien compila en su Mac: `./construir_app.sh --instalar` la copia a Aplicaciones.
Desde el código sin compilar: `./MezquitaPDF.command`.

## Abrir los PDF con Mezquita PDF por defecto

- **Mac:** en la pantalla de inicio de la app aparece «Usar por defecto» (o menú
  *Ayuda → Usar Mezquita PDF como app predeterminada para PDF*). Desde ese momento, el doble
  clic en cualquier PDF lo abre en Mezquita PDF. Alternativa manual: Finder → selecciona un PDF
  → ⌘I → *Abrir con* → Mezquita PDF → **Cambiar todo…**
- **iPhone (iOS 27):** en *Archivos*, mantén pulsado un PDF → **Obtener información** →
  *Abrir siempre con esta aplicación* → **Mezquita PDF** → **Abrir siempre archivos Documento
  PDF**. A partir de ahí, tocar un PDF en Archivos lo abre en la app. También aparece en
  *Abrir con* y en el menú *Compartir* de Mail, WhatsApp, etc.

## Qué puede hacer

| Ver | Editar | Firmar |
|---|---|---|
| Desplazamiento continuo, zoom (⌘+ / ⌘−, pellizco en el trackpad), ajustar al ancho o a la página | Resaltar, subrayar y tachar texto | Firma manuscrita: dibujada, escrita con letra caligráfica o desde una foto (se quita el fondo) |
| Miniaturas (arrástralas para reordenar) y marcadores | Añadir texto, notas, dibujo libre, rectángulos, elipses y flechas | Firma digital PAdES con certificado `.p12`/`.pfx`, visible (con tu rúbrica) o invisible |
| Búsqueda (⌘F, Intro = siguiente) | **Editar texto existente** (clic en una línea) | Sello de tiempo de una TSA (opcional) |
| Seleccionar y copiar texto | **Borrar zona** (elimina de verdad el contenido) | Verificación de firmas, con un aviso verde/rojo al abrir el documento |
| Rellenar formularios y seguir enlaces | Insertar imágenes, borrar anotaciones (doble clic sobre un texto añadido para editarlo) | Certificar el documento (bloquea cambios) |
| Documentos con contraseña | Girar, insertar, eliminar, mover y extraer páginas; combinar PDFs | |
| Imprimir (⌘P) | Deshacer/rehacer (⌘Z / ⇧⌘Z) | |

## Compartir

Botón **Compartir** (arriba a la derecha) o menú *Archivo → Compartir*:

- **Correo electrónico:** abre un mensaje nuevo en tu app de correo (Mail; también Outlook si
  es la predeterminada) con el PDF ya adjunto y el asunto relleno. Solo falta el destinatario y
  pulsar Enviar.
- **WhatsApp:** escribe (opcional) el teléfono del destinatario y pulsa *Abrir WhatsApp*: el PDF
  se copia automáticamente y se abre el chat; allí pulsa **⌘V** y envía. También puedes arrastrar
  la ficha del archivo al chat. Si no tienes WhatsApp para Mac, se usa WhatsApp Web.
- **AirDrop, Mensajes, Notas…:** los servicios para compartir de macOS aparecen en el mismo menú.
- **Copiar el archivo** (para pegarlo en cualquier sitio) y **Mostrar en Finder**.

Si el documento tiene cambios sin guardar, te ofrece guardarlo antes de compartirlo.

> WhatsApp para Mac no permite que otras apps le pasen un archivo directamente (no tiene
> extensión de compartir), por eso el último paso es pegar con ⌘V.

## Firmar con tu certificado digital

No hace falta exportar ni subir nada: Mezquita PDF usa directamente los certificados
instalados en el **Llavero de macOS** (los de la FNMT, ACCV, Camerfirma…, y también las
tarjetas como el DNIe si macOS las reconoce con su lector).

1. Pulsa **Firmar → Firmar con certificado digital…** y arrastra un recuadro donde quieras el
   sello (o elige *Firma digital invisible*).
2. Se abre una ventana con **la lista de tus certificados**: titular, emisor, caducidad y si
   está vigente. Elige uno (la próxima vez aparecerá ya seleccionado).
3. Pulsa **Firmar y guardar**. La primera vez, macOS pregunta si permites que Mezquita PDF use
   la clave del certificado: pulsa **Permitir siempre** para que no vuelva a preguntar.

La clave privada **nunca sale del Llavero**: es macOS quien realiza la operación de firma.
Como alternativa, el botón *Usar un archivo de certificado (.p12 / .pfx)* sigue disponible.

Para probarlo sin tu certificado real usa `ejemplos/certificado_prueba.p12` (contraseña `1234`).
Es un certificado de prueba autofirmado: la firma será íntegra, pero aparecerá como
"identidad no verificada".

La validez de las firmas se comprueba con los certificados raíz de macOS, que incluyen
AC RAIZ FNMT-RCM, ACCV, Izenpe y Firmaprofesional.

> **Importante:** tras firmar, cualquier cambio posterior se guarda de forma incremental para
> no romper la firma (Adobe se comporta igual: la firma sigue siendo válida, pero indica que
> hay cambios posteriores). Deshacer, eliminar páginas o reordenarlas sí invalidaría la
> firma, así que en ese caso el programa te pedirá guardar una copia aparte.

## Limitaciones conocidas

- **Editar texto** sustituye la línea con una fuente estándar (Helvetica, Times o Courier),
  elegida para parecerse a la original; no reutiliza la fuente incrustada.
- El **DNIe** y otras tarjetas solo aparecen si macOS las reconoce (lector y controlador
  CryptoTokenKit instalados); si no, pulsa ⟳ en la lista tras conectar el lector.
- Al ser una app sin firma de desarrollador de Apple, tras **actualizarla** macOS puede volver
  a pedir permiso para usar el certificado.
- La verificación no consulta la revocación del certificado (OCSP/CRL) en Internet.
- Los PDF escaneados no tienen texto seleccionable (no incluye OCR).

## App de iPhone

Está en `web/`: la misma interfaz como app web (PWA) y, empaquetada con Capacitor, como app
nativa de iPhone (`web/ios/`). Ver [web/README.md](web/README.md).

Para instalarla en tu iPhone:
1. En Xcode → *Ajustes → Cuentas*, añade tu Apple ID.
2. Conecta el iPhone por cable (la primera vez, acepta «Confiar en este ordenador» y activa el
   *Modo de desarrollador* en *Ajustes → Privacidad y seguridad*).
3. `cd web && npm run build && npx cap sync ios && npx cap open ios`, elige tu iPhone y pulsa ▶.
   Con una cuenta gratuita la app caduca a los 7 días (se vuelve a instalar igual); con
   Apple Developer (99 €/año) dura un año y permite TestFlight.

## Llevarla a otros Mac

El repositorio incluye un flujo de **GitHub Actions** (`.github/workflows/compilar-mac.yml`)
que, en cada cambio, ejecuta las pruebas y genera dos instaladores `.dmg`:
`MezquitaPDF-apple-silicon.dmg` (M1, M2, M3…) y `MezquitaPDF-intel.dmg`. Se descargan desde la
pestaña *Actions* del repositorio; al crear una etiqueta `v2.1.0` se publican en *Releases*.

En local: `./construir_app.sh --dmg` crea `MezquitaPDF.dmg` para la arquitectura de tu Mac.

Al abrirla por primera vez en otro Mac, como no está notarizada por Apple: clic derecho sobre
la app → **Abrir** → **Abrir** (o *Ajustes del Sistema → Privacidad y seguridad → Abrir
igualmente*).

Diagnóstico rápido (sin datos personales):
`"/Applications/Mezquita PDF.app/Contents/MacOS/Mezquita PDF" --diagnostico`

## Estructura

```
main.py                 Punto de entrada
visor/ventana.py        Ventana principal: menús, barras, páginas, firmas, impresión
visor/vista.py          Renderizado de páginas, zoom y herramientas de edición
visor/documento.py      Documento PDF con deshacer/rehacer y guardado incremental
visor/dialogos.py       Diálogos (texto, firmas manuscritas, certificado, verificación)
visor/firma_digital.py  Firma PAdES y verificación (pyHanko)
visor/llavero.py        Certificados del Llavero de macOS y firma sin exportar la clave
visor/compartir.py      Correo, WhatsApp y servicios de compartir de macOS
visor/tema.py           Paleta, estilos, iconos y logotipo (arco de la Mezquita)
visor/componentes.py    Bienvenida, avisos, barras flotantes, diálogo de WhatsApp
MezquitaPDF.spec        Configuración para crear la .app (PyInstaller)
pruebas/                Prueba de extremo a extremo (también se ejecuta en GitHub)
.github/workflows/      Compilación automática de los .dmg
```

Tecnologías: PySide6 (Qt 6), PyMuPDF (MuPDF), pyHanko, QtAwesome (iconos Material Design), PyObjC.
