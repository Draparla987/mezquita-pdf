"""Integración con macOS: Mezquita PDF como app predeterminada para abrir PDF."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DISPONIBLE = False
if sys.platform == "darwin":
    try:
        from AppKit import NSWorkspace
        from Foundation import NSURL, NSBundle
        DISPONIBLE = True
    except ImportError:
        pass


def ruta_app() -> Path | None:
    """Ruta de «Mezquita PDF.app» si se está ejecutando la app empaquetada."""
    if not (DISPONIBLE and getattr(sys, "frozen", False)):
        return None
    ruta = Path(str(NSBundle.mainBundle().bundlePath()))
    return ruta if ruta.suffix == ".app" else None


def en_aplicaciones() -> bool:
    app = ruta_app()
    return bool(app) and (str(app).startswith("/Applications/")
                          or str(app).startswith(str(Path.home() / "Applications")))


def _pdf_de_muestra() -> NSURL:
    muestra = Path(tempfile.gettempdir()) / "mezquita_muestra.pdf"
    if not muestra.exists():
        muestra.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    return NSURL.fileURLWithPath_(str(muestra))


def app_predeterminada_pdf() -> str:
    """Nombre de la app que abre ahora los PDF (p. ej. «Vista Previa», «Adobe Acrobat»)."""
    if not DISPONIBLE:
        return ""
    url = NSWorkspace.sharedWorkspace().URLForApplicationToOpenURL_(_pdf_de_muestra())
    return Path(str(url.path())).stem if url is not None else ""


def es_predeterminada() -> bool:
    app = ruta_app()
    if app is None:
        return False
    url = NSWorkspace.sharedWorkspace().URLForApplicationToOpenURL_(_pdf_de_muestra())
    return url is not None and os.path.realpath(str(url.path())) == os.path.realpath(str(app))


def hacer_predeterminada(al_terminar) -> bool:
    """Pide a macOS que abra todos los PDF con esta app. `al_terminar(error|None)`."""
    app = ruta_app()
    if app is None:
        return False

    def completado(error):
        al_terminar(None if error is None else str(error.localizedDescription()))

    NSWorkspace.sharedWorkspace().setDefaultApplicationAtURL_toOpenContentTypeOfFileAtURL_completionHandler_(
        NSURL.fileURLWithPath_(str(app)), _pdf_de_muestra(), completado
    )
    return True
