"""Extensión de Chrome: el programa que arranca Chrome (mensajes), el registro y la propia extensión.

Uso:  python pruebas/prueba_chrome.py [programa]
Sin argumentos prueba el código fuente (python main.py). Con la ruta de la app empaquetada
(…/Contents/MacOS/Mezquita PDF en el Mac, mezquita-mcp.exe en Windows) prueba esa.
"""

import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from visor import chrome  # noqa: E402
from visor.version import VERSION  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="mezquita_chrome_"))
DESCARGAS = TMP / "Descargas"
ok = lambda texto: print(f"  ✔ {texto}", flush=True)  # noqa: E731
programa = [sys.argv[1]] if len(sys.argv) > 1 else [sys.executable, str(RAIZ / "main.py")]
ORIGEN = f"chrome-extension://{chrome.ID_EXTENSION}/"
# Como lo arranca Chrome; en las pruebas, sin abrir la app de verdad
entorno = dict(os.environ, MEZQUITA_DESCARGAS=str(DESCARGAS), MEZQUITA_NO_ABRIR="1")


def pedir(mensaje: dict) -> dict:
    datos = json.dumps(mensaje).encode("utf-8")
    r = subprocess.run(programa + [ORIGEN, "--parent-window=0"], input=struct.pack("<I", len(datos)) + datos,
                       capture_output=True, env=entorno, timeout=180)
    assert r.returncode == 0, r.stderr.decode(errors="replace")
    (n,) = struct.unpack("<I", r.stdout[:4])
    return json.loads(r.stdout[4:4 + n].decode("utf-8"))


# 1. La extensión y la app se reconocen
manifest = json.loads((RAIZ / "extension_chrome" / "manifest.json").read_text(encoding="utf-8"))
der = base64.b64decode(manifest["key"])
ident = "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(der).hexdigest()[:32])
assert ident == chrome.ID_EXTENSION, (ident, chrome.ID_EXTENSION)
assert "nativeMessaging" in manifest["permissions"]
assert f'"{chrome.NOMBRE}"' in (RAIZ / "extension_chrome" / "fondo.js").read_text(encoding="utf-8")
for ruta in ("fondo.js", "utilidades.js", "ayuda.html", "ayuda.js", *manifest["icons"].values()):
    assert (RAIZ / "extension_chrome" / ruta).is_file(), ruta
ok(f"la extensión ({ident}) y la app usan el mismo identificador y el mismo nombre de conexión")

# 2. Mensajes, como los manda la extensión
assert pedir({"accion": "hola"}) == {"ok": True, "version": VERSION}
pdf = (RAIZ / "ejemplos" / "ejemplo.pdf").read_bytes()
b64 = base64.b64encode(pdf).decode()
r = pedir({"accion": "abrir", "nombre": "Contrato 2026.pdf", "datos": b64, "origen": "https://x.es/a.pdf"})
assert r["ok"] and Path(r["ruta"]) == DESCARGAS / "Contrato 2026.pdf" and Path(r["ruta"]).read_bytes() == pdf, r
r = pedir({"accion": "abrir", "nombre": "Contrato 2026.pdf", "datos": b64})
assert Path(r["ruta"]).name == "Contrato 2026 (2).pdf", r
r = pedir({"accion": "abrir", "nombre": "../../otra carpeta/malo<>.PDF", "datos": b64})
assert Path(r["ruta"]) == DESCARGAS / "malo.pdf", r
ok("el PDF llega entero a Descargas/Mezquita PDF, sin pisar otro con el mismo nombre ni salir de la carpeta")
r = pedir({"accion": "abrir", "nombre": "x.pdf", "datos": base64.b64encode(b"<html>no</html>").decode()})
assert not r["ok"] and "no es un PDF" in r["error"], r
assert not pedir({"accion": "abrir", "nombre": "x.pdf", "datos": "%%%"})["ok"]
assert pedir({"accion": "abrir_ruta", "ruta": str(DESCARGAS / "malo.pdf")})["ok"]
assert not pedir({"accion": "abrir_ruta", "ruta": str(TMP / "no_existe.pdf")})["ok"]
assert not pedir({"accion": "borrar_todo"})["ok"]
ok("rechaza lo que no es un PDF, las rutas que no existen y las peticiones desconocidas")

# 3. Registro para Chrome (en una carpeta de prueba)
carpeta = TMP / "Chrome" / "NativeMessagingHosts"
chrome.registrar(Path("/Aplicaciones/Mezquita PDF"), carpetas=[carpeta])
m = json.loads((carpeta / f"{chrome.NOMBRE}.json").read_text(encoding="utf-8"))
assert m == {"name": chrome.NOMBRE, "description": m["description"], "path": str(Path("/Aplicaciones/Mezquita PDF")),
             "type": "stdio", "allowed_origins": [ORIGEN]}, m
ok("el registro solo autoriza a la extensión de Mezquita PDF")

# 4. Funciones de la extensión (con Node, si está instalado)
node = shutil.which("node")
if node:
    r = subprocess.run([node, str(RAIZ / "pruebas" / "prueba_extension.js")], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
    ok("funciones de la extensión: direcciones de Drive, nombres, cabecera %PDF, base64 y rutas")
else:
    print("  (sin Node: no se prueban las funciones de la extensión)")

shutil.rmtree(TMP, ignore_errors=True)
print("✅ Extensión de Chrome: correcto")
