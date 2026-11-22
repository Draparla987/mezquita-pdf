"""Escribir texto directamente sobre la página: lo que se ve al escribir es lo que queda en el PDF.

Hace clic con la herramienta Texto, escribe dos líneas y compara dónde están las letras en el cuadro
de edición y en el PDF ya guardado. Prueba también cambiar un texto añadido, cancelar con Esc y
cambiar una línea del PDF con «Editar texto».
Uso:  QT_QPA_PLATFORM=offscreen python pruebas/prueba_texto.py [carpeta_para_capturas]
(En Windows, sin «offscreen»: así Qt no carga las letras del sistema y el cuadro usaría otra.)
"""

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
TMP = Path(tempfile.mkdtemp(prefix="mezquita_texto_"))
os.environ["MEZQUITA_DATOS"] = str(TMP / "datos")
CAPTURAS = Path(sys.argv[1]) if len(sys.argv) > 1 else None

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QRect, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QFontInfo, QImage, QKeyEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
app.setOrganizationName("MezquitaPDFPruebas")
QSettings().clear()

from visor import tema  # noqa: E402
from visor.ventana import VentanaPrincipal  # noqa: E402
from visor.vista import Herramienta  # noqa: E402

tema.aplicar_tema(app, False)
app.setStyleSheet(tema.hoja_estilos(tema.paleta()))

d = pymupdf.open()
pag = d.new_page()
pag.insert_text((72, 100), "Línea original del documento", fontname="helv", fontsize=14)
d.save(TMP / "doc.pdf")

v = VentanaPrincipal()
v.resize(1200, 900)
v.show()
v.activateWindow()
QTest.qWaitForWindowActive(v, 2000)
assert v.abrir_ruta(str(TMP / "doc.pdf"))
QTest.qWait(200)
vista = v.vista
vista.set_zoom(2.0)
QTest.qWait(100)
w = vista.paginas[0]


def tinta(img: QImage, zona: QRect, oscuro: int = 90) -> QRect:
    """Recuadro de los píxeles casi negros (la letra) dentro de `zona` (en píxeles lógicos)."""
    r = img.devicePixelRatio()
    zona = QRect(round(zona.x() * r), round(zona.y() * r), round(zona.width() * r), round(zona.height() * r))
    x0 = y0 = 10 ** 6
    x1 = y1 = -1
    for y in range(zona.top(), zona.bottom()):
        for x in range(zona.left(), zona.right()):
            c = img.pixelColor(x, y)
            if max(c.red(), c.green(), c.blue()) < oscuro:
                x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
    return QRect(QPoint(round(x0 / r), round(y0 / r)), QPoint(round(x1 / r), round(y1 / r)))


def escribir(widget, texto: str) -> None:
    """Teclea `texto` letra a letra (QTest.keyClicks no admite «ñ», «¿» ni «€»)."""
    for letra in texto:
        for tipo in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(widget, QKeyEvent(tipo, Qt.Key_unknown, Qt.NoModifier, letra))


def clic_real(widget) -> None:
    """Clic como los de verdad: entra por la ventana (así Qt decide a quién da el foco) y con una
    pausa entre pulsar y soltar. Con QTest.mouseClick sobre el botón, el fallo del color no se veía."""
    punto = widget.mapTo(widget.window(), widget.rect().center())
    QTest.mousePress(widget.window().windowHandle(), Qt.LeftButton, Qt.NoModifier, punto)
    QTest.qWait(40)
    QTest.mouseRelease(widget.window().windowHandle(), Qt.LeftButton, Qt.NoModifier, punto)
    QTest.qWait(20)


def arrastrar(desde, hasta) -> None:
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, desde)
    for i in range(1, 7):
        QTest.mouseMove(w, desde + (hasta - desde) * i / 6)
        QTest.qWait(10)
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, hasta)
    QTest.qWait(30)


def captura_pagina() -> QImage:
    return vista.contenedor.grab(w.geometry()).toImage()


# 1. Herramienta Texto: clic, un cuadro justo ahí y escribir viendo el resultado
v.set_herramienta(Herramienta.TEXTO)
clic = w.punto_pantalla(pymupdf.Point(100, 250)).toPoint()
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, clic)
e = vista._edicion
assert e is not None and (e.cuadro.hasFocus() or not v.isActiveWindow()), "el clic abre un cuadro para escribir"
info = QFontInfo(e.cuadro.font())
print(f"  · letra en pantalla: {info.family()} ({info.pixelSize()} px)")
escribir(e.cuadro, "Hola, ¿qué tal?")
QTest.keyClick(e.cuadro, Qt.Key_Return)
escribir(e.cuadro, "Segunda línea con ñ y €")
assert vista._edicion is e, "Intro hace un salto de línea, no termina"
clic_real(e.barra.muestras[3])
assert vista._edicion is e and e.estilo.color == "#1c7ed6", "un clic en otro color lo cambia (y no termina)"
clic_real(e.barra.muestras[0])
assert vista._edicion is e and e.estilo.color == "#000000"
clic_real(e.caja)
assert vista._edicion is e, "un clic en el recuadro tampoco termina"
print("  ✔ los colores y el recuadro se pueden pulsar sin que se cierre el cuadro")
e.barra.spin.setValue(16)  # la letra cambia de tamaño en el cuadro al momento
QTest.qWait(50)
e.barra.hide()
e.cuadro.setCursorWidth(0)
e.caja.setStyleSheet("QFrame#cajaTexto { border: none; background: transparent; }")
QTest.qWait(50)
zona = QRect(int(70 * 2), int(220 * 2), int(400 * 2), int(80 * 2))
antes = captura_pagina()
tinta_antes = tinta(antes, zona)
QTest.keyClick(e.cuadro, Qt.Key_Return, Qt.ControlModifier)  # ⌘↩ termina
assert vista._edicion is None
QTest.qWait(100)
despues = captura_pagina()
tinta_despues = tinta(despues, zona)
if CAPTURAS:
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    antes.save(str(CAPTURAS / "texto_escribiendo.png"))
    despues.save(str(CAPTURAS / "texto_en_el_pdf.png"))
annots = [a for a in v.documento.pagina(0).annots() if a.type[0] == pymupdf.PDF_ANNOT_FREE_TEXT]
assert len(annots) == 1 and annots[0].info["content"] == "Hola, ¿qué tal?\nSegunda línea con ñ y €", annots
da = v.documento.doc.xref_get_key(annots[0].xref, "DA")[1]
assert "/Helv 16" in da, da
dif = [abs(a - b) for a, b in ((tinta_antes.left(), tinta_despues.left()), (tinta_antes.top(), tinta_despues.top()),
                               (tinta_antes.right(), tinta_despues.right()),
                               (tinta_antes.bottom(), tinta_despues.bottom()))]
print(f"  · letras al escribir {tinta_antes.getCoords()} · en el PDF {tinta_despues.getCoords()} · diferencia {dif} px")
tolerancia = 4 if sys.platform == "darwin" else 12  # en Windows, Arial y Times New Roman en vez de las del PDF
assert max(dif) <= tolerancia, f"el texto se mueve al terminar: {dif} px"
print("  ✔ lo que se ve al escribir es lo que queda en el PDF")
assert v.documento.puede_deshacer() and v.documento.modificado
assert v.ajustes.value("texto/tamano") in (16, 16.0, "16.0", "16"), "se recuerda el tamaño para la próxima vez"

# 2. Clic en el texto añadido (con la herramienta Texto): se cambia escribiendo sobre él
xref = annots[0].xref
pasos = len(v.documento._deshacer)
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, w.a_pantalla(annots[0].rect).center().toPoint())
e = vista._edicion
assert e is not None and e.texto() == "Hola, ¿qué tal?\nSegunda línea con ñ y €"
a = v.documento.pagina(0).load_annot(xref)
assert a.flags & pymupdf.PDF_ANNOT_IS_HIDDEN, "mientras se edita, el original no se dibuja debajo"
e.cuadro.selectAll()
escribir(e.cuadro, "Texto cambiado")
clic_real(e.barra.muestras[3])
e.terminar()
a = v.documento.pagina(0).load_annot(xref)
assert a.info["content"] == "Texto cambiado" and not a.flags & pymupdf.PDF_ANNOT_IS_HIDDEN
assert "0.109804 0.494118 0.839216 rg" in v.documento.doc.xref_get_key(xref, "DA")[1], "se guarda el color nuevo"
assert len(v.documento._deshacer) == pasos + 1, "un solo paso para deshacer"
print("  ✔ un texto añadido se cambia escribiendo sobre él")

# 3. Esc cancela: todo como estaba, sin pasos de más en Deshacer
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, w.a_pantalla(a.rect).center().toPoint())
e = vista._edicion
escribir(e.cuadro, " y esto no")
QTest.keyClick(e.cuadro, Qt.Key_Escape)
a = v.documento.pagina(0).load_annot(xref)
assert vista._edicion is None and a.info["content"] == "Texto cambiado" and not a.flags & pymupdf.PDF_ANNOT_IS_HIDDEN
assert len(v.documento._deshacer) == pasos + 1
print("  ✔ Esc deja el texto como estaba")

# 4. Un cambio del documento (p. ej. girar la página) guarda antes el texto a medio escribir
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, w.punto_pantalla(pymupdf.Point(100, 500)).toPoint())
escribir(vista._edicion.cuadro, "Sin terminar")
v.girar_pagina(90, [0])
assert vista._edicion is None
assert any(x.info["content"] == "Sin terminar" for x in v.documento.pagina(0).annots())
v.deshacer()  # deshace el giro
v.deshacer()  # y el texto
assert not any(x.info["content"] == "Sin terminar" for x in v.documento.pagina(0).annots())
print("  ✔ girar, guardar o deshacer no pierden el texto que se estaba escribiendo")

# 5. En una página girada, el texto queda donde se hizo clic
v.girar_pagina(90, [0])
QTest.qWait(50)
w = vista.paginas[0]
punto = pymupdf.Point(300, 300)
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, w.punto_pantalla(punto).toPoint())
escribir(vista._edicion.cuadro, "Girada")
vista.terminar_edicion()
girada = next(x for x in v.documento.pagina(0).annots() if x.info["content"] == "Girada")
assert (girada.rect + (-12, -12, 12, 12)).contains(punto), (girada.rect, punto)
v.deshacer()
v.deshacer()
QTest.qWait(50)
w = vista.paginas[0]
print("  ✔ también en páginas giradas")

# 6. Editar texto: clic en una línea del PDF y escribir encima (Intro termina)
v.set_herramienta(Herramienta.EDITAR_TEXTO)
linea = vista._lineas_de(0)[0]
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, w.a_pantalla(linea["rect"]).center().toPoint())
e = vista._edicion
assert e is not None and e.texto() == "Línea original del documento"
assert "original" not in v.documento.pagina(0).get_text(), "mientras se edita, la línea original no se ve"
e.cuadro.selectAll()
escribir(e.cuadro, "Línea corregida")
QTest.keyClick(e.cuadro, Qt.Key_Return)
assert vista._edicion is None
assert "Línea corregida" in v.documento.pagina(0).get_text()
print("  ✔ una línea del PDF se cambia escribiendo sobre ella")

# 7. Un texto añadido se mueve arrastrándolo también con Texto y con Editar texto (un clic lo abre)
for herramienta in (Herramienta.TEXTO, Herramienta.EDITAR_TEXTO):
    v.set_herramienta(herramienta)
    a = next(x for x in v.documento.pagina(0).annots() if x.info["content"] == "Texto cambiado")
    antes = pymupdf.Rect(a.rect)
    centro = w.a_pantalla(antes).center().toPoint()
    arrastrar(centro, centro + QPoint(80, 40))
    a = next(x for x in v.documento.pagina(0).annots() if x.info["content"] == "Texto cambiado")
    assert vista._edicion is None and abs(a.rect.x0 - antes.x0 - 40) < 2 and abs(a.rect.y0 - antes.y0 - 20) < 2, \
        (herramienta, antes, a.rect)
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, w.a_pantalla(a.rect).center().toPoint())
    assert vista._edicion is not None and vista._edicion.texto() == "Texto cambiado", herramienta
    vista.cancelar_edicion()
print("  ✔ un texto añadido se mueve arrastrándolo con Texto y con Editar texto")

v.documento.modificado = False
v.close()
QSettings().clear()
print("✅ Escribir sobre la página: correcto")
