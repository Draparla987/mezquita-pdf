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

shutil.rmtree(TMP, ignore_errors=True)
print("✅ Prueba básica superada")
