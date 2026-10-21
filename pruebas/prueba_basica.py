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

shutil.rmtree(TMP, ignore_errors=True)
print("✅ Prueba básica superada")
