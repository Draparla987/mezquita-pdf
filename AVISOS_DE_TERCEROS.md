# Avisos de terceros

Mezquita PDF © 2026 Antonio P. Arenas de Larriva se distribuye bajo la licencia
**GNU Affero General Public License v3.0** (archivo [`LICENSE`](LICENSE)).
El código fuente completo está en <https://github.com/Draparla987/mezquita-pdf>.

Mezquita PDF incluye o utiliza los siguientes componentes de terceros, cada uno
sujeto a su propia licencia. Los textos completos de cada licencia acompañan a
cada componente en su paquete original (PyPI / npm) y están disponibles en la web
de cada proyecto.

## App de Mac (`visor/`, instaladores `.dmg`)

| Componente | Licencia | Proyecto |
|---|---|---|
| PyMuPDF / MuPDF | GNU AGPL v3.0 (o licencia comercial de Artifex) | https://github.com/pymupdf/PyMuPDF |
| PySide6 / Qt 6 | GNU LGPL v3.0 | https://www.qt.io/qt-for-python |
| pyHanko y pyhanko-certvalidator | MIT | https://github.com/MatthiasValvekens/pyHanko |
| cryptography | Apache 2.0 o BSD de 3 cláusulas | https://github.com/pyca/cryptography |
| asn1crypto | MIT | https://github.com/wbond/asn1crypto |
| Pillow | MIT-CMU (HPND) | https://python-pillow.org |
| aiohttp | Apache 2.0 y MIT | https://github.com/aio-libs/aiohttp |
| QtAwesome | MIT | https://github.com/spyder-ide/qtawesome |
| Fuentes de iconos incluidas en QtAwesome (Font Awesome, Material Design Icons, Phosphor, Remix Icon, Codicons, Elusive) | SIL OFL 1.1, CC BY 4.0, Apache 2.0 o MIT, según la fuente | https://github.com/spyder-ide/qtawesome#license |
| PyObjC | MIT | https://github.com/ronaldoussoren/pyobjc |
| Python | Python Software Foundation License | https://www.python.org |
| PyInstaller (cargador de arranque) | GPL v2 con excepción para el cargador de arranque | https://pyinstaller.org |

Además se incluyen las dependencias indirectas que instalan estos paquetes, cada
una con su propia licencia (consultables con `pip show <paquete>`).

**Qt (LGPL v3):** la app incluye las bibliotecas de Qt como archivos dinámicos
independientes dentro de `Mezquita PDF.app/Contents/Frameworks`, que pueden
sustituirse por otra versión compatible de Qt. El código fuente de Qt está
disponible en <https://download.qt.io/official_releases/qt/> y el de PySide6 en
<https://code.qt.io/cgit/pyside/pyside-setup.git/>.

Las fuentes caligráficas que usa la firma manuscrita en el Mac (Snell Roundhand,
Bradley Hand, Apple Chancery, Zapfino…) son fuentes del sistema macOS: no se
incluyen en la app.

## App web y de iPhone (`web/`)

| Componente | Licencia | Proyecto |
|---|---|---|
| PDF.js (`pdfjs-dist`) | Apache 2.0 | https://github.com/mozilla/pdf.js |
| pdf-lib | MIT | https://github.com/Hopding/pdf-lib |
| node-forge | BSD de 3 cláusulas (o GPL v2) | https://github.com/digitalbazaar/forge |
| Capacitor (`@capacitor/core`, `app`, `filesystem`, `share`) | MIT | https://capacitorjs.com |
| Fuente Allura (`@fontsource/allura`) | SIL OFL 1.1 | https://fonts.google.com/specimen/Allura |
| Fuente Dancing Script (`@fontsource/dancing-script`) | SIL OFL 1.1 | https://fonts.google.com/specimen/Dancing+Script |
| Fuente Great Vibes (`@fontsource/great-vibes`) | SIL OFL 1.1 | https://fonts.google.com/specimen/Great+Vibes |

## Marcas

FNMT, ACCV, Izenpe, Camerfirma, Firmaprofesional, Adobe, Apple, macOS, iPhone,
WhatsApp, Outlook y demás nombres citados son marcas de sus respectivos titulares
y se mencionan solo para describir la compatibilidad. Mezquita PDF no está
afiliado a ninguno de ellos. La imagen de la app se inspira en la arquitectura de
la Mezquita-Catedral de Córdoba, sin reproducir ningún logotipo ni marca.
