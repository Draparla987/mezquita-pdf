"""Extensión de Chrome «Firmar con Mezquita PDF»: la parte de la app (sin Qt).

La extensión (carpeta extension_chrome/) le pasa a la app el PDF que se está viendo en Chrome o en
Google Drive mediante la mensajería nativa de Chrome: Chrome arranca este programa con el origen de
la extensión como argumento, le envía un mensaje por la entrada estándar (4 bytes con la longitud y
JSON) y espera la respuesta por la salida estándar. Aquí el PDF se guarda en Descargas/Mezquita PDF
y se abre en la app, listo para firmar.

Para que Chrome encuentre este programa, la app se registra al arrancar (registrar()): un pequeño
JSON por navegador que solo autoriza a esta extensión (allowed_origins).
"""

from __future__ import annotations

import base64
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

from .version import VERSION

NOMBRE = "es.mezquitapdf.chrome"
# Sale de la clave pública («key») de extension_chrome/manifest.json; las pruebas lo comprueban
ID_EXTENSION = "hilbdbfcnkfdibahiomnigmjhjcpnkaj"
MAX_PDF = 48 * 1024 * 1024  # Chrome admite mensajes de hasta 64 MB (el PDF va en base64)
ES_MAC = sys.platform == "darwin"
ES_WINDOWS = sys.platform == "win32"

# Navegadores basados en Chrome que admiten la extensión
CARPETAS_MAC = ["Google/Chrome", "Microsoft Edge", "BraveSoftware/Brave-Browser", "Chromium"]
CLAVES_WINDOWS = [r"Software\Google\Chrome\NativeMessagingHosts", r"Software\Microsoft\Edge\NativeMessagingHosts",
                  r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts"]


def es_llamada_de_chrome(argv: list[str]) -> bool:
    return any(a.startswith("chrome-extension://") for a in argv[1:])


# ----------------------------------------------------------------------------
# Mensajes (formato de Chrome: longitud en 4 bytes del sistema y JSON en UTF-8)
# ----------------------------------------------------------------------------
def leer_mensaje(entrada) -> dict | None:
    cabecera = entrada.read(4)
    if len(cabecera) < 4:
        return None
    (longitud,) = struct.unpack("<I", cabecera)
    return json.loads(entrada.read(longitud).decode("utf-8"))


def escribir_mensaje(salida, mensaje: dict) -> None:
    datos = json.dumps(mensaje, ensure_ascii=False).encode("utf-8")
    salida.write(struct.pack("<I", len(datos)) + datos)
    salida.flush()


# ----------------------------------------------------------------------------
# Guardar y abrir el PDF
# ----------------------------------------------------------------------------
def carpeta_descargas() -> Path:
    if os.environ.get("MEZQUITA_DESCARGAS"):  # pruebas
        return Path(os.environ["MEZQUITA_DESCARGAS"])
    return Path.home() / "Downloads" / "Mezquita PDF"


def nombre_seguro(nombre: str) -> str:
    """Solo el nombre (sin carpetas), sin caracteres que el sistema no admite y acabado en .pdf."""
    nombre = re.split(r"[\\/]", str(nombre or ""))[-1]
    nombre = re.sub(r'[\x00-\x1f<>:"|?*]+', " ", nombre).strip(" .")
    if nombre.lower().endswith(".pdf"):
        nombre = nombre[:-4].rstrip(" .")
    return (nombre[:120] or "documento") + ".pdf"


def guardar(nombre: str, datos: bytes) -> Path:
    carpeta = carpeta_descargas()
    carpeta.mkdir(parents=True, exist_ok=True)
    base = nombre_seguro(nombre)[:-4]
    ruta, n = carpeta / f"{base}.pdf", 2
    while ruta.exists():
        ruta, n = carpeta / f"{base} ({n}).pdf", n + 1
    ruta.write_bytes(datos)
    return ruta


def abrir_en_app(ruta: Path) -> None:
    """Abre el PDF en Mezquita PDF (si ya está abierta, en esa misma)."""
    if os.environ.get("MEZQUITA_NO_ABRIR"):  # pruebas
        return
    if getattr(sys, "frozen", False) and ES_MAC:
        app = Path(sys.executable).resolve().parents[2]  # …/Mezquita PDF.app
        subprocess.Popen(["open", "-a", str(app), str(ruta)])
    elif getattr(sys, "frozen", False) and ES_WINDOWS:
        exe = Path(sys.executable).with_name("Mezquita PDF.exe")  # le pasa el PDF a la abierta, si la hay
        sueltos = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:  # Chrome mete a este programa en un «job»: la app tiene que salir de él para no cerrarse con él
            subprocess.Popen([str(exe), str(ruta)], creationflags=sueltos | subprocess.CREATE_BREAKAWAY_FROM_JOB,
                             close_fds=True)
        except OSError:
            subprocess.Popen([str(exe), str(ruta)], creationflags=sueltos, close_fds=True)
    else:  # desde el código fuente
        main_py = Path(__file__).resolve().parent.parent / "main.py"
        subprocess.Popen([sys.executable, str(main_py), str(ruta)], start_new_session=True)


def atender(mensaje: dict) -> dict:
    accion = mensaje.get("accion")
    if accion == "hola":
        return {"ok": True, "version": VERSION}
    if accion == "abrir":  # el PDF de una página web o de Drive
        try:
            datos = base64.b64decode(mensaje.get("datos") or "", validate=True)
        except ValueError:
            return {"ok": False, "error": "Los datos del PDF han llegado dañados."}
        if len(datos) > MAX_PDF:
            return {"ok": False, "error": "El PDF es demasiado grande para pasarlo desde el navegador."}
        if b"%PDF" not in datos[:1024]:
            return {"ok": False, "error": "Lo que se ha descargado no es un PDF."}
        ruta = guardar(mensaje.get("nombre") or "documento.pdf", datos)
        abrir_en_app(ruta)
        return {"ok": True, "ruta": str(ruta)}
    if accion == "abrir_ruta":  # un PDF del propio ordenador abierto en Chrome (file://)
        ruta = Path(str(mensaje.get("ruta") or ""))
        if ruta.suffix.lower() != ".pdf" or not ruta.is_file():
            return {"ok": False, "error": "No se encuentra ese PDF en el ordenador."}
        abrir_en_app(ruta)
        return {"ok": True, "ruta": str(ruta)}
    return {"ok": False, "error": f"Petición desconocida: {accion}"}


def main() -> int:
    """Lo que hace el programa cuando lo arranca Chrome: un mensaje, una respuesta y fin."""
    try:
        mensaje = leer_mensaje(sys.stdin.buffer)
        respuesta = atender(mensaje) if mensaje is not None else {"ok": False, "error": "Sin mensaje"}
    except Exception as exc:  # que la extensión siempre reciba una respuesta
        respuesta = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    escribir_mensaje(sys.stdout.buffer, respuesta)
    return 0


# ----------------------------------------------------------------------------
# Registro para que Chrome (y Edge, Brave…) encuentren este programa
# ----------------------------------------------------------------------------
def ejecutable() -> Path | None:
    """Programa que arranca Chrome: la propia app en el Mac y la versión con consola en Windows."""
    if not getattr(sys, "frozen", False):
        return None
    if ES_WINDOWS:
        return Path(sys.executable).with_name("mezquita-mcp.exe")
    return Path(sys.executable).resolve()


def manifiesto(ruta_exe: Path) -> dict:
    return {
        "name": NOMBRE,
        "description": "Mezquita PDF: abre para firmar los PDF que le pasa la extensión de Chrome",
        "path": str(ruta_exe),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ID_EXTENSION}/"],
    }


def _escribir_si_cambia(ruta: Path, contenido: str) -> None:
    if not ruta.exists() or ruta.read_text(encoding="utf-8") != contenido:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")


def registrar(ruta_exe: Path | None = None, carpetas: list[Path] | None = None) -> list[str]:
    """Registra este programa en los navegadores instalados. Devuelve dónde.

    `carpetas` (pruebas) son carpetas «NativeMessagingHosts» concretas donde dejar el manifiesto.
    """
    ruta_exe = ruta_exe or ejecutable()
    if ruta_exe is None:  # desde el código fuente no se registra nada
        return []
    contenido = json.dumps(manifiesto(ruta_exe), ensure_ascii=False, indent=2)
    if carpetas is not None:
        for carpeta in carpetas:
            _escribir_si_cambia(carpeta / f"{NOMBRE}.json", contenido)
        return [str(c) for c in carpetas]
    hechos = []
    if ES_MAC:
        soporte = Path.home() / "Library" / "Application Support"
        for nombre in CARPETAS_MAC:
            if (soporte / nombre).is_dir():  # solo los navegadores que estén instalados
                _escribir_si_cambia(soporte / nombre / "NativeMessagingHosts" / f"{NOMBRE}.json", contenido)
                hechos.append(nombre.split("/")[-1])
    elif ES_WINDOWS:
        import winreg

        from .plataforma import carpeta_base
        ruta_json = carpeta_base() / "chrome" / f"{NOMBRE}.json"
        _escribir_si_cambia(ruta_json, contenido)
        for clave in CLAVES_WINDOWS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{clave}\{NOMBRE}") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(ruta_json))
            hechos.append(clave.split("\\")[-2])
    return hechos
