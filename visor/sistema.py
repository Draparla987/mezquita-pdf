"""Mezquita PDF como app predeterminada para abrir PDF (macOS y Windows).

En macOS se cambia directamente (NSWorkspace). Windows no permite que una app se ponga a sí misma
como predeterminada: el instalador la registra para los PDF y aquí se abre Configuración en su página.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ES_WINDOWS = sys.platform == "win32"
PROGID = "MezquitaPDF.Documento"  # el que registra el instalador de Windows
DISPONIBLE = False
if sys.platform == "darwin":
    try:
        from AppKit import NSWorkspace
        from Foundation import NSURL, NSBundle
        DISPONIBLE = True
    except ImportError:
        pass


def ruta_app() -> Path | None:
    """Ruta de «Mezquita PDF.app» (o de «Mezquita PDF.exe» en Windows) si es la app empaquetada."""
    if ES_WINDOWS:
        return Path(sys.executable) if getattr(sys, "frozen", False) else None
    if not (DISPONIBLE and getattr(sys, "frozen", False)):
        return None
    ruta = Path(str(NSBundle.mainBundle().bundlePath()))
    return ruta if ruta.suffix == ".app" else None


def en_aplicaciones() -> bool:
    if ES_WINDOWS:
        return ruta_app() is not None
    app = ruta_app()
    return bool(app) and (str(app).startswith("/Applications/")
                          or str(app).startswith(str(Path.home() / "Applications")))


def _pdf_de_muestra() -> NSURL:
    muestra = Path(tempfile.gettempdir()) / "mezquita_muestra.pdf"
    if not muestra.exists():
        muestra.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    return NSURL.fileURLWithPath_(str(muestra))


def _progid_pdf_windows() -> str:
    """Programa que el usuario eligió para los .pdf (lo que Windows guarda en «UserChoice»)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                            r"\FileExts\.pdf\UserChoice") as clave:
            return str(winreg.QueryValueEx(clave, "ProgId")[0])
    except OSError:
        return ""


def app_predeterminada_pdf() -> str:
    """Nombre de la app que abre ahora los PDF (p. ej. «Vista Previa», «Adobe Acrobat»)."""
    if ES_WINDOWS:
        progid = _progid_pdf_windows()
        conocidos = {"MezquitaPDF": "Mezquita PDF", "Acro": "Adobe Acrobat", "MSEdge": "Microsoft Edge",
                     "Chrome": "Google Chrome", "Firefox": "Firefox", "Foxit": "Foxit PDF Reader"}
        return next((n for clave, n in conocidos.items() if clave.lower() in progid.lower()), "")
    if not DISPONIBLE:
        return ""
    url = NSWorkspace.sharedWorkspace().URLForApplicationToOpenURL_(_pdf_de_muestra())
    return Path(str(url.path())).stem if url is not None else ""


def es_predeterminada() -> bool:
    if ES_WINDOWS:
        return _progid_pdf_windows() == PROGID
    app = ruta_app()
    if app is None:
        return False
    url = NSWorkspace.sharedWorkspace().URLForApplicationToOpenURL_(_pdf_de_muestra())
    return url is not None and os.path.realpath(str(url.path())) == os.path.realpath(str(app))


CONFIGURACION = "configuracion"  # resultado en Windows: se ha abierto Configuración para elegirla


def hacer_predeterminada(al_terminar) -> bool:
    """Pide al sistema que abra todos los PDF con esta app. `al_terminar(error|None|CONFIGURACION)`."""
    app = ruta_app()
    if app is None:
        return False
    if ES_WINDOWS:
        import os
        try:  # Windows 11: la página de Mezquita PDF en «Aplicaciones predeterminadas»
            os.startfile("ms-settings:defaultapps?registeredAppUser=Mezquita%20PDF")
        except OSError:
            os.startfile("ms-settings:defaultapps")
        al_terminar(CONFIGURACION)
        return True

    def completado(error):
        al_terminar(None if error is None else str(error.localizedDescription()))

    NSWorkspace.sharedWorkspace().setDefaultApplicationAtURL_toOpenContentTypeOfFileAtURL_completionHandler_(
        NSURL.fileURLWithPath_(str(app)), _pdf_de_muestra(), completado
    )
    return True
