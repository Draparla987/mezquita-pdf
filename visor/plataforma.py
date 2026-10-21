"""Diferencias entre Mac y Windows que se notan en la interfaz (sin Qt: lo usa también la
extensión para Claude)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ES_MAC = sys.platform == "darwin"
ES_WINDOWS = sys.platform == "win32"

# Dónde guarda el sistema los certificados y cómo se llama el explorador de archivos
NOMBRE_ALMACEN = "Llavero" if ES_MAC else "almacén de certificados de Windows"
NOMBRE_EXPLORADOR = "Finder" if ES_MAC else "el Explorador de archivos"


def teclas(texto: str) -> str:
    """Atajos escritos al estilo Mac («⌘Z», «⇧⌘Z», «⌫») → en Windows «Ctrl+Z», «Ctrl+Mayús+Z», «Supr»."""
    if ES_MAC:
        return texto

    def combinacion(m: re.Match) -> str:
        mods, tecla = m.group(1), m.group(2)
        partes = [n for s, n in (("⌘", "Ctrl"), ("⌥", "Alt"), ("⇧", "Mayús")) if s in mods]
        return "+".join(partes + [tecla])

    return re.sub(r"([⇧⌥⌘]+)(\S)", combinacion, texto).replace("⌫", "Supr")


def carpeta_base(nombre: str = "MezquitaPDF") -> Path:
    """Carpeta de datos del usuario (firmas, socket de Claude, actualizaciones…)."""
    if ES_MAC:
        return Path.home() / "Library" / "Application Support" / nombre
    if ES_WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home())) / nombre
    return Path.home() / ".local" / "share" / nombre


def carpeta_cache(nombre: str = "MezquitaPDF") -> Path:
    if ES_MAC:
        return Path.home() / "Library" / "Caches" / nombre
    if ES_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / nombre
    return Path.home() / ".cache" / nombre


def usuario() -> str:
    """Identificador del usuario para nombres de canales locales (Windows los comparte entre usuarios)."""
    nombre = os.environ.get("USERNAME") or os.environ.get("USER") or "usuario"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", nombre)
