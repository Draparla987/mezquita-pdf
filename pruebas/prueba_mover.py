"""Mover texto original y anotaciones con el ratón y el teclado, como lo haría el usuario.

Uso:  QT_QPA_PLATFORM=offscreen python pruebas/prueba_mover.py [carpeta_para_capturas]
"""

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
TMP = Path(tempfile.mkdtemp(prefix="mezquita_"))
os.environ["MEZQUITA_DATOS"] = str(TMP / "datos")
CAPTURAS = Path(sys.argv[1]) if len(sys.argv) > 1 else None

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
app.setOrganizationName("MezquitaPDFPruebas")

from visor import tema  # noqa: E402
from visor.ventana import VentanaPrincipal  # noqa: E402
from visor.vista import Herramienta  # noqa: E402

tema.aplicar_tema(app, False)
ok = lambda texto: print(f"  ✔ {texto}", flush=True)  # noqa: E731

# Documento: una línea con negrita y «€», otra en Times y color, dos más, y anotaciones
d = pymupdf.open()
p = d.new_page()
tw = pymupdf.TextWriter(p.rect)
tw.append((72, 100), "Precio total: ", font=pymupdf.Font("helv"), fontsize=14)
tw.append(tw.last_point, "1.250 €", font=pymupdf.Font("hebo"), fontsize=14)
tw.write_text(p)
p.insert_text((72, 140), "Firmado en Córdoba", fontname="tiro", fontsize=12, color=(0.56, 0.1, 0.17))
p.insert_text((72, 200), "Primera línea del bloque", fontsize=11)
p.insert_text((72, 216), "Segunda línea del bloque", fontsize=11)
p.add_freetext_annot(pymupdf.Rect(300, 400, 500, 440), "Mi cuadro de texto", fontsize=12).update()
flecha = p.add_line_annot((300, 600), (420, 640))
flecha.set_line_ends(0, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
flecha.set_colors(stroke=(1, 0, 0))
flecha.update()
ruta = TMP / "mover.pdf"
d.save(ruta)

v = VentanaPrincipal()
v.resize(1100, 900)
v.show()
assert v.abrir_ruta(str(ruta))
QTest.qWait(200)
vista = v.vista
vista.set_zoom(1.0)
QTest.qWait(100)
w = vista.paginas[0]
pag = lambda: v.documento.pagina(0)  # noqa: E731
editados = []
vista.pedir_editar_texto.disconnect()
vista.pedir_editar_texto.connect(lambda i, linea: editados.append(linea["texto"]))


def pantalla(x: float, y: float) -> QPoint:
    q = w.punto_pantalla(pymupdf.Point(x, y))
    return QPoint(round(q.x()), round(q.y()))


def arrastrar(desde: QPoint, hasta: QPoint, pasos: int = 6, captura: str | None = None) -> None:
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, desde)
    for i in range(1, pasos + 1):
        QTest.mouseMove(w, desde + (hasta - desde) * i / pasos)
        QTest.qWait(10)
    if captura and CAPTURAS:
        w.grab().save(str(CAPTURAS / captura))
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, hasta)
    QTest.qWait(30)


def palabras(texto: str):
    return [x for x in pag().get_text("words") if x[4] == texto]


def spans():
    return [s for b in pag().get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]


# 1. Editar texto: un clic sigue abriendo la edición; arrastrar mueve la línea
v.set_herramienta(Herramienta.EDITAR_TEXTO)
QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, pantalla(100, 136))
assert editados == ["Firmado en Córdoba"], editados
ok("un clic en una línea abre su edición, como antes")
arrastrar(pantalla(100, 96), pantalla(250, 296), captura="arrastrando_linea.png")
precio = next(s for s in spans() if s["text"].startswith("Precio"))
euros = next(s for s in spans() if "€" in s["text"])
assert abs(precio["origin"][0] - 222) < 2 and abs(precio["origin"][1] - 300) < 2, precio["origin"]
# NimbusSans es la Helvetica que lleva PyMuPDF (misma forma y medidas)
assert "Bold" in euros["font"] and ("Helvetica" in euros["font"] or "NimbusSans" in euros["font"]), euros
assert abs(euros["size"] - 14) < 0.3, euros
assert not palabras("Precio") or palabras("Precio")[0][1] > 250
ok(f"línea movida de (72, 100) a {tuple(round(c) for c in precio['origin'])}, con su negrita, su «€» y tamaño 14")

# 2. Ajuste fino con las flechas (la línea sigue seleccionada) y sin que crezca la letra
for _ in range(3):
    QTest.keyClick(vista, Qt.Key_Right)
QTest.keyClick(vista, Qt.Key_Down, Qt.ShiftModifier)
precio2 = next(s for s in spans() if s["text"].startswith("Precio"))
assert abs(precio2["origin"][0] - precio["origin"][0] - 3) < 0.6 and abs(precio2["origin"][1] - precio["origin"][1] - 10) < 0.6
tamanos = {round(s["size"], 1) for s in spans() if s["text"].startswith(("Precio", "1.250"))}
assert all(abs(t - 14) < 0.3 for t in tamanos), tamanos
ok("flechas: 3 pt a la derecha y ⇧↓ 10 pt; la letra no crece al moverla varias veces")

# 3. Varias líneas a la vez: recuadro alrededor del bloque y arrastrar
arrastrar(pantalla(60, 185), pantalla(260, 222))
assert vista._lineas_sel and len(vista._lineas_sel[1]) == 2, vista._lineas_sel
arrastrar(pantalla(90, 196), pantalla(90, 496))
y1, y2 = palabras("Primera")[0][1], palabras("Segunda")[0][1]
assert 480 < y1 < 500 and 14 < y2 - y1 < 18, (y1, y2)
ok("bloque de dos líneas seleccionado con un recuadro y movido 300 pt hacia abajo")

# 4. Seleccionar: mover un cuadro de texto, cambiar su tamaño, flechas y ⌫
v.set_herramienta(Herramienta.SELECCIONAR)
caja = next(a for a in pag().annots() if a.type[1] == "FreeText")
arrastrar(pantalla(400, 420), pantalla(400, 520), captura="arrastrando_cuadro.png")
caja = next(a for a in pag().annots() if a.type[1] == "FreeText")
assert abs(caja.rect.y0 - 500) < 1.5 and abs(caja.rect.x0 - 300) < 1.5, caja.rect
arrastrar(pantalla(caja.rect.x1, caja.rect.y1), pantalla(caja.rect.x1 + 60, caja.rect.y1 + 40))
caja = next(a for a in pag().annots() if a.type[1] == "FreeText")
assert abs(caja.rect.width - 260) < 2 and abs(caja.rect.height - 80) < 2, caja.rect
QTest.keyClick(vista, Qt.Key_Left, Qt.ShiftModifier)
caja = next(a for a in pag().annots() if a.type[1] == "FreeText")
assert abs(caja.rect.x0 - 290) < 1.5, caja.rect
ok(f"cuadro de texto movido, ampliado a {caja.rect.width:.0f}×{caja.rect.height:.0f} y ajustado con ⇧←")
if CAPTURAS:
    w.grab().save(str(CAPTURAS / "cuadro_seleccionado.png"))

# 5. La flecha (se vuelve a crear igual) y ⌫ para borrar
arrastrar(pantalla(360, 620), pantalla(360, 700))
linea = next(a for a in pag().annots() if a.type[1] == "Line")
assert abs(linea.vertices[0][1] - 680) < 2 and linea.colors["stroke"] == [1.0, 0.0, 0.0] and linea.line_ends[1] == 5
ok("flecha movida con su color y su punta")
QTest.keyClick(vista, Qt.Key_Backspace)
assert not any(a.type[1] == "Line" for a in pag().annots())
ok("⌫ borra la anotación seleccionada")

# 6. Todo se deshace
while v.documento.puede_deshacer():
    v.deshacer()
assert palabras("Precio")[0][1] < 100 and any(a.type[1] == "Line" for a in pag().annots())
ok("⌘Z lo deshace todo y el documento vuelve a estar como al principio")
v.documento.modificado = False
v.close()
print("✅ Mover texto y anotaciones: correcto")
