"""Pruebas propias de Windows (se ejecutan en GitHub Actions, en una máquina con Windows).

Antes, el flujo de trabajo crea en el almacén «Personal» tres certificados de prueba (CNG RSA,
CNG EC y CryptoAPI). Aquí se comprueba que la app los encuentra, que firma un PDF con cada uno
sin exportar la clave y que las firmas son válidas; además, el canal con Claude por tubería con
nombre, el paso de archivos a la copia ya abierta y unas capturas de la interfaz.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
TMP = Path(tempfile.mkdtemp(prefix="mezquita_"))
os.environ["MEZQUITA_DATOS"] = str(TMP / "datos")
CAPTURAS = RAIZ / "pruebas" / "salida_windows"
CAPTURAS.mkdir(parents=True, exist_ok=True)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
app.setOrganizationName("MezquitaPDFPruebas")

from visor import actualizaciones, compartir, sistema, tema  # noqa: E402
from visor import firma_digital as fd  # noqa: E402
from visor import instancia, llavero, mcp_servidor, puente_claude  # noqa: E402
from visor.plataforma import ES_WINDOWS, teclas  # noqa: E402

assert ES_WINDOWS, "esta prueba es para Windows"
tema.aplicar_tema(app, False)
ok = lambda texto: print(f"  ✔ {texto}", flush=True)  # noqa: E731

# 1. Textos y detalles de Windows ------------------------------------------------------
assert teclas("⇧⌘Z · ⌘S · ⌫") == "Ctrl+Mayús+Z · Ctrl+S · Supr"
assert actualizaciones.nombre_instalador() == "MezquitaPDF-windows.exe"
assert mcp_servidor.CONFIG_CLAUDE.name == "claude_desktop_config.json" and "Claude" in str(mcp_servidor.CONFIG_CLAUDE)
print("WhatsApp instalado:", compartir.whatsapp_instalado(), "· PDF se abren con:", sistema.app_predeterminada_pdf() or "—")
ok("textos, instalador y rutas de Windows")

# 2. Certificados del almacén de Windows: firmar y verificar ------------------------------
certs = llavero.listar_certificados()
print("Certificados de firma en el almacén:", [(c.titular, c.emisor) for c in certs])
pruebas = {"Prueba Mezquita CNG RSA", "Prueba Mezquita CNG EC", "Prueba Mezquita CryptoAPI"}
encontrados = {c.titular: c for c in certs if c.titular in pruebas}
assert set(encontrados) == pruebas, f"faltan certificados: {pruebas - set(encontrados)}"
pdf = (RAIZ / "ejemplos" / "ejemplo.pdf").read_bytes()
for titular, cert in sorted(encontrados.items()):
    firmante = llavero.FirmanteLlavero(cert)
    firmado = fd.firmar_pdf(pdf, firmante, pagina=0, caja=(330, 50, 560, 120), motivo="Prueba en Windows")
    resultados = fd.verificar_firmas(firmado)
    assert len(resultados) == 1 and resultados[0].integra and resultados[0].cubre_todo, (titular, resultados)
    assert resultados[0].firmante == titular, resultados[0].firmante
    (TMP / f"{titular}.pdf").write_bytes(firmado)
    ok(f"firmado y verificado con «{titular}» ({cert.cert.public_key.algorithm.upper()})")
print("Raíces de confianza de Windows:", len(fd.raices_confianza_sistema()))
assert len(fd.raices_confianza_sistema()) > 10

# 3. Canal con Claude (tubería con nombre) y paso de archivos a la copia abierta --------------
from visor.ventana import VentanaPrincipal, _ventanas  # noqa: E402

v = VentanaPrincipal()
v.resize(1180, 800)
v.show()
assert v.abrir_ruta(str(RAIZ / "ejemplos" / "ejemplo.pdf"))
_ventanas.append(v)
puente = puente_claude.PuenteClaude(app)
assert puente.activar(True), "no se pudo abrir la tubería de Claude"
recibidos: list = []
ins = instancia.Instancia(app, recibidos.append)
assert ins.escuchando
resultados_hilo: dict = {}


def cliente():
    try:
        resultados_hilo["estado"] = mcp_servidor.pedir_a_la_app("estado", {})
        resultados_hilo["leer"] = mcp_servidor.pedir_a_la_app("leer_texto", {"paginas": "1"})
        resultados_hilo["instancia"] = instancia.enviar_a_la_abierta([r"C:\documentos\contrato.pdf"])
    except Exception as exc:  # se comprueba abajo
        resultados_hilo["error"] = repr(exc)


hilo = threading.Thread(target=cliente, daemon=True)
QTimer.singleShot(200, hilo.start)
reloj = QTimer()
reloj.timeout.connect(lambda: app.quit() if not hilo.is_alive() and hilo.ident else None)
reloj.start(100)
QTimer.singleShot(30000, app.quit)
app.exec()
assert "error" not in resultados_hilo, resultados_hilo.get("error")
estado = json.loads(resultados_hilo["estado"]["texto"])
assert estado["documentos"][0]["nombre"] == "ejemplo.pdf", estado
assert "Página 1" in resultados_hilo["leer"]["texto"]
ok("Claude habla con la app por la tubería con nombre")
assert resultados_hilo["instancia"] and recibidos == [[r"C:\documentos\contrato.pdf"]], recibidos
ok("una segunda copia le pasa los PDF a la que ya está abierta")

# 4. Capturas de la interfaz en Windows ---------------------------------------------------
from visor.dialogos import DialogoFirmaDigital  # noqa: E402

v.grab().save(str(CAPTURAS / "ventana.png"))
dlg = DialogoFirmaDigital(v)
dlg.resize(640, 760)
dlg.show()
QTimer.singleShot(400, app.quit)
app.exec()
dlg.grab().save(str(CAPTURAS / "certificados.png"))
dlg.close()
v.documento.modificado = False
v.close()
ok(f"capturas en {CAPTURAS}")

shutil.rmtree(TMP, ignore_errors=True)
print("✅ Pruebas de Windows superadas")
