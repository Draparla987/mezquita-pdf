"""Prueba rápida de extremo a extremo (se ejecuta también en GitHub Actions).

Abre un PDF, anota, guarda, firma con el certificado de prueba y verifica la firma.
Uso:  QT_QPA_PLATFORM=offscreen python pruebas/prueba_basica.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
TMP = Path(tempfile.mkdtemp(prefix="mezquita_"))
os.environ["MEZQUITA_DATOS"] = str(TMP / "datos")  # no tocar las firmas reales del usuario

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
app.setOrganizationName("MezquitaPDFPruebas")

from visor import firma_digital as fd, tema  # noqa: E402
from visor.documento import Documento  # noqa: E402
from visor.ventana import VentanaPrincipal  # noqa: E402

tema.aplicar_tema(app, False)
origen = TMP / "ejemplo.pdf"
shutil.copy(RAIZ / "ejemplos" / "ejemplo.pdf", origen)

# 1. Abrir, anotar y guardar
doc = Documento(str(origen))
doc.instantanea()
doc.pagina(0).add_highlight_annot(doc.pagina(0).search_for("Lorem")[0])
doc.guardar(str(TMP / "anotado.pdf"))
assert any(a.type[1] == "Highlight" for a in pymupdf.open(TMP / "anotado.pdf")[0].annots())
doc.deshacer() if doc.puede_deshacer() else None
doc.cerrar()

# 2. Firmar con el certificado de prueba y verificar
firmante = fd.cargar_certificado(str(RAIZ / "ejemplos" / "certificado_prueba.p12"), "1234")
datos = (TMP / "anotado.pdf").read_bytes()
firmado = fd.firmar_pdf(datos, firmante, pagina=0, caja=(330, 50, 560, 120), motivo="Prueba")
resultados = fd.verificar_firmas(firmado)
assert len(resultados) == 1 and resultados[0].integra and resultados[0].cubre_todo, resultados

# 3. Segunda firma: la primera debe seguir siendo válida
firmado2 = fd.firmar_pdf(firmado, firmante)
assert [r.integra for r in fd.verificar_firmas(firmado2)] == [True, True]

# 4. La ventana principal se construye y abre el documento
v = VentanaPrincipal()
assert v.abrir_ruta(str(TMP / "anotado.pdf"))
v.documento.modificado = False
v.close()

# 5. Miniaturas: reordenar, insertar archivos soltados y borrar con ⌫ (todo se puede deshacer)
varias = pymupdf.open()
for i in range(5):
    varias.new_page().insert_text((72, 72), f"P{i + 1}")
varias.save(TMP / "varias.pdf")
v = VentanaPrincipal()
assert v.abrir_ruta(str(TMP / "varias.pdf"))
textos = lambda: [v.documento.pagina(i).get_text().strip() for i in range(v.documento.num_paginas)]  # noqa: E731
v.mover_paginas_a([3, 4], 0)
assert textos() == ["P4", "P5", "P1", "P2", "P3"], textos()
v.insertar_archivos([str(origen)], 2)
assert v.documento.num_paginas == 5 + pymupdf.open(origen).page_count
v.eliminar_paginas([0, 1], confirmar=False)
assert textos()[0] not in ("P4", "P5")
while v.documento.puede_deshacer():
    v.deshacer()
assert textos() == ["P1", "P2", "P3", "P4", "P5"], textos()

# 6. Extensión para Claude: protocolo MCP y herramientas (sin socket ni app de Claude)
import json  # noqa: E402
from visor import mcp_servidor, puente_claude, ventana  # noqa: E402
ini = mcp_servidor._atender({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                             "params": {"protocolVersion": "2025-06-18"}})["result"]
assert ini["protocolVersion"] == "2025-06-18" and ini["serverInfo"]["name"] == "mezquita-pdf"
nombres = {h["name"] for h in mcp_servidor._atender({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
assert nombres == set(puente_claude.HERRAMIENTAS)
ventana._ventanas.append(v)
pedir = lambda h, **a: puente_claude.atender(json.dumps({"herramienta": h, "argumentos": a}).encode())  # noqa: E731
assert "P3" in pedir("leer_texto", paginas="3")["texto"]
assert pedir("resaltar", textos=["P2"])["texto"].startswith("1 marcas")
assert "error" in pedir("ver_pagina", pagina=99)
assert pedir("ver_pagina", pagina=1)["imagen"]["tipo"] == "image/jpeg"
ventana._ventanas.remove(v)
v.documento.modificado = False
v.close()

# 7. Actualizaciones (sin red): versiones, elección del instalador y guion de sustitución
from visor import actualizaciones as act  # noqa: E402
assert act.es_mas_nueva("2.10.0", "2.9.9") and not act.es_mas_nueva("2.5.0", "2.5.0")
publicada = {"tag_name": "v9.0.0", "body": "Instaladores\n## Novedades\n- x", "html_url": "https://x", "assets": [
    {"name": "MezquitaPDF-intel.dmg", "browser_download_url": "https://i", "size": 1, "digest": "sha256:AA"},
    {"name": "MezquitaPDF-apple-silicon.dmg", "browser_download_url": "https://a", "size": 2, "digest": "sha256:BB"}]}
nueva = act.interpretar(publicada, "MezquitaPDF-intel.dmg")
assert (nueva.numero, nueva.url, nueva.sha256, nueva.notas) == ("9.0.0", "https://i", "aa", "## Novedades\n- x")
if sys.platform == "win32":
    guion = act.guion_windows(1, Path(r"C:\N\MezquitaPDF-windows.exe"), Path(r"C:\A\Mezquita PDF.exe"), True)
    assert "Wait-Process -Id 1" in guion and "'/VERYSILENT'" in guion and guion.endswith(r"'C:\A\Mezquita PDF.exe'")
else:
    guion = act.guion_sustitucion(1, Path("/A/Mezquita PDF.app"), Path("/N/Mezquita PDF.app"), Path("/C/anterior.app"), False)
    assert "mv '/A/Mezquita PDF.app' /C/anterior.app" in guion and "open" not in guion.split("fi\n")[-1]

# 8. Marca de agua del sello: logotipo propio (JPG con fondo blanco) en lugar del arco
from PIL import Image, ImageDraw  # noqa: E402
from visor import llavero, marcas  # noqa: E402
from visor.dialogos import DialogoFirmaDigital  # noqa: E402
logo = Image.new("RGB", (300, 120), "white")
dibujo = ImageDraw.Draw(logo)
dibujo.ellipse((20, 20, 100, 100), fill=(0, 90, 160))
dibujo.rectangle((130, 50, 280, 70), fill=(60, 60, 60))
logo.save(TMP / "Mi organización.jpg", quality=92)
ruta_logo = marcas.anadir(TMP / "Mi organización.jpg")
limpio = Image.open(ruta_logo)
assert ruta_logo.name == "Mi organización.png" and limpio.mode == "RGBA"
assert limpio.getpixel((0, limpio.height - 1))[3] == 0, "el fondo blanco debe quedar transparente"
r, g, b, a = limpio.getpixel((40, limpio.height // 2))
assert a > 240 and abs(r - 0) < 25 and abs(g - 90) < 25 and abs(b - 160) < 25, (r, g, b, a)
sellos = {m: fd.componer_sello(ancho_pt=200, alto_pt=80, titular="PRUEBA", motivo="", lugar="", rubrica_png=None,
                               marca=m).tobytes() for m in (None, fd.MARCA_MEZQUITA, str(ruta_logo))}
assert len(set(sellos.values())) == 3, "cada marca de agua debe cambiar el sello"
con_logo = fd.firmar_pdf(datos, firmante, pagina=0, caja=(330, 50, 560, 120), marca=str(ruta_logo))
assert fd.verificar_firmas(con_logo)[0].integra
# La marca se elige una vez en Firmar → Marca de agua del sello; la ventana de firma no pregunta
llavero.listar_certificados = lambda *a, **k: []  # sin leer el Llavero de nadie
from PySide6.QtCore import QSettings  # noqa: E402
QSettings().setValue("firma/marca", "Mi organización")  # por nombre, como el instalador de una edición
assert marcas.elegida() == str(ruta_logo), marcas.elegida()
v = VentanaPrincipal()
v._rellenar_menu_marca()
opciones = [a for a in v.menu_marca.actions() if a.isCheckable()]
assert [(a.text(), a.isChecked()) for a in opciones] == [
    ("Arco de Mezquita PDF", False), ("Mi organización", True), ("Sin marca de agua", False)]
dlg = DialogoFirmaDigital(v)
assert dlg.marca == str(ruta_logo) and "Mi organización" in dlg.etiqueta_marca.text()
dlg.close()
opciones[2].trigger()
assert marcas.elegida() is None and DialogoFirmaDigital(v).marca is None
v._rellenar_menu_marca()
next(a for a in v.menu_marca.actions() if a.text() == "Arco de Mezquita PDF").trigger()
assert marcas.elegida() == marcas.MEZQUITA
v.close()
marcas.quitar(ruta_logo)
assert marcas.guardadas() == []

shutil.rmtree(TMP, ignore_errors=True)
print("✅ Prueba básica superada")
