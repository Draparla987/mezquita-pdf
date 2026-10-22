"""Abre todas las ventanas de la app en la pantalla de un portátil y comprueba que caben.

Simula 1366×768 con el zoom de Windows al 125 % (1093×566 libres sin la barra de tareas): cada
ventana debe abrirse sin errores, caber en la pantalla y tener sus botones a la vista.
Así se detectaron la ventana de la firma con certificado (los botones quedaban fuera) y la de
WhatsApp de la 2.7.0 (no se abría). Uso:  python pruebas/prueba_pantallas.py
"""

import atexit
import json
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
TMP = Path(tempfile.mkdtemp(prefix="mezquita_"))
os.environ["MEZQUITA_DATOS"] = str(TMP / "datos")
# Ruta relativa: Qt separa las opciones con «:», y en Windows la letra de unidad («C:») las rompería
pantalla = Path(f".pantalla_portatil_{os.getpid()}.json")
pantalla.write_text(json.dumps({"screens": [{"name": "portatil", "x": 0, "y": 0, "width": 1093, "height": 566,
                                             "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}))
atexit.register(lambda: pantalla.unlink(missing_ok=True))
os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={pantalla}"

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

app = QApplication([])
app.setOrganizationName("MezquitaPDFPruebas")

from visor import actualizaciones, tema  # noqa: E402
from visor import firma_digital as fd  # noqa: E402
from visor.combinar import DialogoCombinar  # noqa: E402
from visor.componentes import DialogoWhatsApp  # noqa: E402
from visor.dialogos import (  # noqa: E402
    DialogoContrasena, DialogoFirmaDigital, DialogoFirmas, DialogoNuevaFirma, DialogoTexto,
    DialogoVerificacion, carpeta_datos,
)
from visor.puente_claude import DialogoClaude  # noqa: E402
from visor.ventana import VentanaPrincipal  # noqa: E402

tema.aplicar_tema(app, False)
area = app.primaryScreen().availableGeometry()
assert (area.width(), area.height()) == (1093, 566), area
ejemplo = str(RAIZ / "ejemplos" / "ejemplo.pdf")
# Una firma guardada: si no hay ninguna, «Mis firmas» abre directamente la ventana para crearla
firma = QImage(300, 100, QImage.Format_ARGB32)
firma.fill(0)
firma.save(str(carpeta_datos() / "firmas" / "firma_prueba.png"))
firmado = fd.firmar_pdf(Path(ejemplo).read_bytes(), fd.cargar_certificado(
    str(RAIZ / "ejemplos" / "certificado_prueba.p12"), "1234"), pagina=0, caja=(330, 50, 560, 120))
fallos = []


def revisar(nombre: str, ventana) -> None:
    ventana.show()
    QTest.qWait(120)
    botones = [b for b in ventana.findChildren(QPushButton) if b.isVisible() and b.window() is ventana]
    abajo = max((b.mapTo(ventana, b.rect().bottomLeft()).y() for b in botones), default=0)
    cabe = ventana.height() + 30 <= area.height() and ventana.width() <= area.width() and abajo <= ventana.height()
    print(f"  {'✔' if cabe else '✘'} {nombre}: {ventana.width()}×{ventana.height()}", flush=True)
    if not cabe:
        fallos.append(nombre)


v = VentanaPrincipal()
revisar("ventana principal", v)
assert v.abrir_ruta(ejemplo)
QTest.qWait(150)
ventanas = [
    ("firma con certificado", lambda: DialogoFirmaDigital(v)),
    ("combinar documentos", lambda: DialogoCombinar(v, actual=v.documento)),
    ("nueva firma manuscrita", lambda: DialogoNuevaFirma(v)),
    ("mis firmas", lambda: DialogoFirmas(v, seleccionar=False)),
    ("añadir texto", lambda: DialogoTexto(v)),
    ("verificar firmas", lambda: DialogoVerificacion(fd.verificar_firmas(firmado), v)),
    ("contraseña", lambda: DialogoContrasena("documento.pdf", v)),
    ("enviar por WhatsApp", lambda: DialogoWhatsApp(ejemplo, v)),
    ("conectar con Claude", lambda: DialogoClaude(None, v)),
    ("actualización", lambda: actualizaciones.DialogoActualizacion(
        actualizaciones.Version("9.9.9", "## Novedades\n" + "- Una novedad\n" * 15, "", "x"), v)),
]
for nombre, crear in ventanas:
    try:
        dialogo = crear()
    except Exception as exc:  # no se abre: también es un fallo
        print(f"  ✘ {nombre}: no se abre ({type(exc).__name__}: {exc})", flush=True)
        fallos.append(nombre)
        continue
    revisar(nombre, dialogo)
    dialogo.close()
v.documento.modificado = False
v.close()
if fallos:
    sys.exit(f"Ventanas con problemas: {', '.join(fallos)}")
print("✅ Todas las ventanas caben en la pantalla de un portátil")
