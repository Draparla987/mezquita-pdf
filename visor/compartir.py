"""Compartir el PDF: correo electrónico, WhatsApp y servicios de macOS (AirDrop, Mensajes…).

En macOS se usan los servicios nativos (NSSharingService) mediante PyObjC; en otros
sistemas se recurre a mailto: y a abrir la carpeta del archivo.
"""

from __future__ import annotations

import re
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QApplication

ES_MAC = sys.platform == "darwin"
ID_WHATSAPP = "net.whatsapp.WhatsApp"

try:
    if not ES_MAC:
        raise ImportError
    from AppKit import (
        NSBitmapImageRep, NSPasteboard, NSSharingService, NSSharingServiceNameComposeEmail,
        NSWorkspace,
    )
    from Foundation import NSURL, NSBundle
    HAY_APPKIT = True
except ImportError:
    HAY_APPKIT = False

# Los servicios de AppKit deben seguir vivos mientras muestran su ventana.
_retenidos: list = []


def _url_archivo(ruta: str | Path):
    return NSURL.fileURLWithPath_(str(Path(ruta).resolve()))


# ----------------------------------------------------------------------------
# Correo electrónico
# ----------------------------------------------------------------------------
def app_correo_predeterminada() -> str:
    if not HAY_APPKIT:
        return ""
    url = NSWorkspace.sharedWorkspace().URLForApplicationToOpenURL_(NSURL.URLWithString_("mailto:"))
    if url is None:
        return ""
    bundle = NSBundle.bundleWithURL_(url)
    return str(bundle.bundleIdentifier() or "") if bundle else ""


def _applescript(guion: str) -> bool:
    try:
        r = subprocess.run(["osascript", "-e", guion], capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:
        return False


def _escapar_as(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace('"', '\\"')


def enviar_por_correo(ruta: str, asunto: str, cuerpo: str) -> str:
    """Abre un mensaje nuevo con el PDF adjunto. Devuelve el método usado.

    El mensaje no se envía: el usuario elige destinatario y pulsa Enviar en su app de correo.
    """
    ruta = str(Path(ruta).resolve())
    if HAY_APPKIT:
        app = app_correo_predeterminada().lower()
        if "outlook" in app:
            guion = f'''
            tell application "Microsoft Outlook"
                set m to make new outgoing message with properties {{subject:"{_escapar_as(asunto)}", plain text content:"{_escapar_as(cuerpo)}"}}
                make new attachment at m with properties {{file:POSIX file "{_escapar_as(ruta)}"}}
                open m
                activate
            end tell'''
            if _applescript(guion):
                return "Outlook"
        servicio = NSSharingService.sharingServiceNamed_(NSSharingServiceNameComposeEmail)
        elementos = [cuerpo, _url_archivo(ruta)]
        if servicio is not None and servicio.canPerformWithItems_(elementos):
            servicio.setSubject_(asunto)
            servicio.performWithItems_(elementos)
            _retenidos.append(servicio)
            return "Mail"
        guion = f'''
        tell application "Mail"
            set m to make new outgoing message with properties {{subject:"{_escapar_as(asunto)}", content:"{_escapar_as(cuerpo)}", visible:true}}
            tell m to make new attachment with properties {{file name:POSIX file "{_escapar_as(ruta)}"}} at after the last paragraph
            activate
        end tell'''
        if _applescript(guion):
            return "Mail"
    # Último recurso: mensaje vacío con mailto y la carpeta abierta para adjuntar a mano
    webbrowser.open(f"mailto:?subject={quote(asunto)}&body={quote(cuerpo)}")
    mostrar_en_carpeta(ruta)
    return "mailto"


# ----------------------------------------------------------------------------
# WhatsApp
# ----------------------------------------------------------------------------
def whatsapp_instalado() -> bool:
    if HAY_APPKIT:
        return NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(ID_WHATSAPP) is not None
    if sys.platform == "win32":
        return False  # en Windows se usa WhatsApp Web / app de la tienda
    return False


def normalizar_telefono(texto: str, prefijo_pais: str = "34") -> str:
    """Deja solo dígitos con prefijo internacional (9 dígitos → España)."""
    digitos = re.sub(r"\D", "", texto or "")
    if texto.strip().startswith("00"):
        digitos = digitos[2:]
    if len(digitos) == 9:
        digitos = prefijo_pais + digitos
    return digitos


def abrir_whatsapp(telefono: str = "") -> str:
    """Abre WhatsApp (en el chat del teléfono indicado, si lo hay). Devuelve 'app' o 'web'."""
    numero = normalizar_telefono(telefono) if telefono else ""
    if whatsapp_instalado():
        url = f"whatsapp://send?phone={numero}" if numero else "whatsapp://"
        if HAY_APPKIT:
            NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))
        else:
            QDesktopServices.openUrl(QUrl(url))
        return "app"
    QDesktopServices.openUrl(QUrl(f"https://web.whatsapp.com/send?phone={numero}" if numero
                                  else "https://web.whatsapp.com/"))
    return "web"


# ----------------------------------------------------------------------------
# Portapapeles, Finder y servicios de macOS
# ----------------------------------------------------------------------------
def copiar_archivo(ruta: str) -> None:
    """Copia el archivo (no su contenido) para pegarlo con ⌘V en WhatsApp, Mail, Finder…"""
    if HAY_APPKIT:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.writeObjects_([_url_archivo(ruta)])
        return
    datos = QMimeData()
    datos.setUrls([QUrl.fromLocalFile(str(Path(ruta).resolve()))])
    QApplication.clipboard().setMimeData(datos)


def mostrar_en_carpeta(ruta: str) -> None:
    ruta = str(Path(ruta).resolve())
    if ES_MAC:
        subprocess.run(["open", "-R", ruta], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", ruta], check=False)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(ruta).parent)))


@dataclass
class ServicioSistema:
    titulo: str
    icono: QPixmap | None
    _servicio: object

    def compartir(self, ruta: str) -> None:
        self._servicio.performWithItems_([_url_archivo(ruta)])
        _retenidos.append(self._servicio)


def servicios_sistema(ruta: str) -> list[ServicioSistema]:
    """Servicios de compartir de macOS disponibles para el archivo (AirDrop, Mensajes, Notas…)."""
    if not HAY_APPKIT:
        return []
    try:
        servicios = NSSharingService.sharingServicesForItems_([_url_archivo(ruta)])
    except Exception:
        return []
    resultado = []
    for s in servicios:
        nombre = str(s.name() or "")
        if "Mail.compose" in nombre:
            continue  # ya está como «Correo electrónico»
        resultado.append(ServicioSistema(str(s.title()), _nsimage_a_pixmap(s.image()), s))
    return resultado


def _nsimage_a_pixmap(imagen) -> QPixmap | None:
    if imagen is None:
        return None
    try:
        tiff = imagen.TIFFRepresentation()
        rep = NSBitmapImageRep.imageRepWithData_(tiff)
        png = rep.representationUsingType_properties_(4, None)  # NSBitmapImageFileTypePNG
        pix = QPixmap()
        pix.loadFromData(bytes(png))
        return pix
    except Exception:
        return None
