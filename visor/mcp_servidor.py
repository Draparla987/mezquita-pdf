"""Extensión de Mezquita PDF para la app de Claude (servidor MCP por stdio).

Claude Desktop lanza «Mezquita PDF --mcp». Este proceso no abre ventanas: traduce las
peticiones de Claude (JSON-RPC, una por línea) y se las pasa a Mezquita PDF por un socket
local privado (solo accesible para tu usuario). Es Mezquita PDF quien hace los cambios, a la
vista y con ⌘Z para deshacer; nada se guarda en disco sin que tú lo hagas.

Este módulo no usa Qt: así arranca rápido y también sirve para instalar la extensión.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

NOMBRE_SERVIDOR = "mezquita-pdf"
PROTOCOLOS = ("2025-06-18", "2025-03-26", "2024-11-05")
LISTAS_VACIAS = {"resources/list": "resources", "resources/templates/list": "resourceTemplates", "prompts/list": "prompts"}
ESPERA_RESPUESTA = 600  # s: puede haber diálogos (p. ej. la contraseña de un PDF)
CONFIG_CLAUDE = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
APP_INSTALADA = Path("/Applications/Mezquita PDF.app/Contents/MacOS/Mezquita PDF")

INSTRUCCIONES = (
    "Mezquita PDF es el visor y editor de PDF del usuario en su Mac. Usa «estado» para ver qué "
    "documentos tiene abiertos (y el texto que tenga seleccionado). Lee el texto antes de resaltar o "
    "anotar, y no inventes contenido. Los cambios se ven al momento en Mezquita PDF, el usuario puede "
    "deshacerlos con ⌘Z y no se guardan en disco hasta que él los guarde con ⌘S. Las páginas se "
    "numeran desde 1. Si un documento es un escaneo sin texto, usa «ver_pagina»."
)


# ----------------------------------------------------------------------------
# Rutas e instalación en la app de Claude
# ----------------------------------------------------------------------------
def carpeta_datos() -> Path:
    if os.environ.get("MEZQUITA_DATOS"):  # pruebas
        return Path(os.environ["MEZQUITA_DATOS"])
    return Path.home() / "Library" / "Application Support" / "MezquitaPDF"


def ruta_socket() -> str:
    return str(carpeta_datos() / "claude.sock")


def comando_mcp() -> tuple[str, list[str]]:
    """Programa que debe lanzar Claude: la app instalada, si existe."""
    if APP_INSTALADA.exists():
        return str(APP_INSTALADA), ["--mcp"]
    if getattr(sys, "frozen", False):
        return sys.executable, ["--mcp"]
    return sys.executable, [str(Path(__file__).resolve().parent.parent / "main.py"), "--mcp"]


def claude_disponible() -> bool:
    return CONFIG_CLAUDE.parent.is_dir() or Path("/Applications/Claude.app").exists()


def _leer_config() -> dict:
    if not CONFIG_CLAUDE.exists():
        return {}
    texto = CONFIG_CLAUDE.read_text(encoding="utf-8").strip()
    datos = json.loads(texto) if texto else {}  # si no es JSON válido, mejor no tocarlo
    if not isinstance(datos, dict):
        raise ValueError("la configuración de Claude no tiene el formato esperado")
    return datos


def _escribir_config(datos: dict) -> None:
    CONFIG_CLAUDE.parent.mkdir(parents=True, exist_ok=True)
    copia = CONFIG_CLAUDE.with_name(CONFIG_CLAUDE.name + ".antes-de-mezquita")
    if CONFIG_CLAUDE.exists() and not copia.exists():
        copia.write_bytes(CONFIG_CLAUDE.read_bytes())
    tmp = CONFIG_CLAUDE.with_name(CONFIG_CLAUDE.name + ".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, CONFIG_CLAUDE)


def extension_instalada() -> bool:
    try:
        return NOMBRE_SERVIDOR in (_leer_config().get("mcpServers") or {})
    except Exception:
        return False


def instalar_extension() -> None:
    """Añade Mezquita PDF a la app de Claude conservando el resto de su configuración."""
    datos = _leer_config()
    comando, argumentos = comando_mcp()
    servidores = datos.get("mcpServers")
    if not isinstance(servidores, dict):
        servidores = datos["mcpServers"] = {}
    servidores[NOMBRE_SERVIDOR] = {"command": comando, "args": argumentos}
    _escribir_config(datos)


def quitar_extension() -> None:
    datos = _leer_config()
    if NOMBRE_SERVIDOR in (datos.get("mcpServers") or {}):
        del datos["mcpServers"][NOMBRE_SERVIDOR]
        _escribir_config(datos)


# ----------------------------------------------------------------------------
# Herramientas que se ofrecen a Claude (las ejecuta la app: visor/puente_claude.py)
# ----------------------------------------------------------------------------
_DOC = {"type": "string", "description": "Nombre o número del documento (según «estado»). Si se omite, el de la ventana activa."}
_PAGINAS = {"type": "string", "description": "Páginas, p. ej. «1-3, 5, 8-» (desde 1)."}
_PAGINA = {"type": "integer", "minimum": 1, "description": "Número de página (desde 1)."}
_RUTAS = {"type": "array", "items": {"type": "string"}, "description": "Rutas de archivos PDF o imágenes (JPG, PNG…). Se admite «~/»."}


def _h(nombre, descripcion, propiedades=None, obligatorias=(), solo_lectura=False, destructiva=False):
    return {
        "name": nombre,
        "description": descripcion,
        "inputSchema": {"type": "object", "properties": propiedades or {}, "required": list(obligatorias)},
        "annotations": {"readOnlyHint": solo_lectura, "destructiveHint": destructiva, "openWorldHint": False},
    }


HERRAMIENTAS = [
    _h("estado", "Documentos abiertos en Mezquita PDF: nombre, ruta, páginas, página visible, si tiene cambios "
       "sin guardar, si está firmado, campos de formulario y el texto que el usuario tenga seleccionado.",
       solo_lectura=True),
    _h("abrir_documento", "Abre un PDF en Mezquita PDF (si tiene contraseña, la escribe el usuario).",
       {"ruta": {"type": "string", "description": "Ruta del PDF; se admite «~/»."}}, ["ruta"]),
    _h("leer_texto", "Texto del documento, página a página (todas si no se indican).",
       {"paginas": _PAGINAS, "documento": _DOC}, solo_lectura=True),
    _h("ver_pagina", "Imagen de una página tal como se ve (útil para escaneos, tablas, sellos o firmas).",
       {"pagina": _PAGINA, "documento": _DOC}, ["pagina"], solo_lectura=True),
    _h("buscar", "Busca un texto y devuelve en qué páginas aparece, con la línea en la que está.",
       {"texto": {"type": "string"}, "documento": _DOC}, ["texto"], solo_lectura=True),
    _h("leer_anotaciones", "Anotaciones del documento: resaltados (con el texto marcado), notas, comentarios…",
       {"paginas": _PAGINAS, "documento": _DOC}, solo_lectura=True),
    _h("resaltar", "Resalta, subraya o tacha todas las apariciones de uno o varios textos exactos "
       "(cópialos tal cual aparecen en el documento).",
       {"textos": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "estilo": {"type": "string", "enum": ["resaltar", "subrayar", "tachar"], "default": "resaltar"},
        "color": {"type": "string", "enum": ["amarillo", "verde", "azul", "rosa", "naranja", "rojo"]},
        "paginas": _PAGINAS, "documento": _DOC}, ["textos"]),
    _h("anadir_nota", "Añade una nota adhesiva (comentario) en una página, junto a un texto si se indica.",
       {"pagina": _PAGINA, "texto": {"type": "string", "description": "Contenido de la nota."},
        "cerca_de": {"type": "string", "description": "Texto de la página junto al que poner la nota (opcional)."},
        "documento": _DOC}, ["pagina", "texto"]),
    _h("campos_formulario", "Campos del formulario del PDF: nombre, tipo, valor actual y opciones posibles.",
       {"documento": _DOC}, solo_lectura=True),
    _h("rellenar_formulario", "Rellena campos del formulario. Casillas: true/false. Listas y botones de opción: "
       "uno de los valores posibles (ver «campos_formulario»).",
       {"valores": {"type": "object", "description": "{nombre del campo: valor}",
                    "additionalProperties": {"type": ["string", "boolean", "number"]}},
        "documento": _DOC}, ["valores"]),
    _h("ir_a_pagina", "Muestra una página en la ventana de Mezquita PDF.",
       {"pagina": _PAGINA, "documento": _DOC}, ["pagina"]),
    _h("girar_paginas", "Gira páginas.",
       {"paginas": _PAGINAS, "grados": {"type": "integer", "enum": [90, -90, 180]}, "documento": _DOC},
       ["paginas", "grados"]),
    _h("eliminar_paginas", "Elimina páginas del documento abierto (se puede deshacer con ⌘Z).",
       {"paginas": _PAGINAS, "documento": _DOC}, ["paginas"], destructiva=True),
    _h("mover_paginas", "Cambia el orden: lleva las páginas indicadas delante de la página «delante_de» "
       "(usa el nº de páginas + 1 para llevarlas al final).",
       {"paginas": _PAGINAS, "delante_de": {"type": "integer", "minimum": 1}, "documento": _DOC},
       ["paginas", "delante_de"]),
    _h("insertar_archivos", "Inserta PDF o imágenes en el documento abierto, delante de una página (al final si se omite).",
       {"rutas": _RUTAS, "delante_de": {"type": "integer", "minimum": 1}, "documento": _DOC}, ["rutas"]),
    _h("combinar_documentos", "Une varios PDF o imágenes, en ese orden, en un documento nuevo que se abre en "
       "Mezquita PDF sin guardar.",
       {"rutas": _RUTAS,
        "incluir_abierto": {"type": "boolean", "default": False, "description": "Poner primero el documento activo."},
        "marcadores": {"type": "boolean", "default": True, "description": "Un marcador por cada documento."}},
       ["rutas"]),
    _h("extraer_paginas", "Copia páginas a un documento nuevo que se abre en otra ventana (sin guardar).",
       {"paginas": _PAGINAS, "documento": _DOC}, ["paginas"]),
    _h("deshacer", "Deshace el último cambio del documento (como ⌘Z).", {"documento": _DOC}),
]


# ----------------------------------------------------------------------------
# Comunicación con la app
# ----------------------------------------------------------------------------
class SinConexion(Exception):
    pass


def _conectar() -> socket.socket:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(ruta_socket())
    return s


def _abrir_app() -> None:
    """Abre Mezquita PDF en segundo plano (sin quitarle el foco a Claude)."""
    if os.environ.get("MEZQUITA_DATOS"):
        return  # pruebas: nunca se abre la app real
    if getattr(sys, "frozen", False):
        paquete = Path(sys.executable).resolve().parents[2]  # …/Mezquita PDF.app
        orden = ["/usr/bin/open", "-g", "-a", str(paquete)]
    else:
        orden = ["/usr/bin/open", "-g", "-b", "local.mezquitapdf.app"]
    subprocess.run(orden, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pedir_a_la_app(herramienta: str, argumentos: dict) -> dict:
    try:
        s = _conectar()
    except OSError:
        _abrir_app()
        limite = time.time() + 25
        while True:
            time.sleep(0.3)
            try:
                s = _conectar()
                break
            except OSError:
                if time.time() > limite:
                    raise SinConexion(
                        "No he podido conectar con Mezquita PDF. Ábrela y comprueba en "
                        "Herramientas → Conectar con Claude… que el acceso está permitido.") from None
    with s:
        s.settimeout(ESPERA_RESPUESTA)
        s.sendall(json.dumps({"herramienta": herramienta, "argumentos": argumentos}).encode() + b"\n")
        recibido = bytearray()
        while not recibido.endswith(b"\n"):
            trozo = s.recv(1 << 16)
            if not trozo:
                break
            recibido += trozo
    if not recibido:
        raise SinConexion("Mezquita PDF ha cerrado la conexión sin responder.")
    return json.loads(recibido)


def _llamar(nombre: str, argumentos: dict) -> dict:
    if nombre not in {h["name"] for h in HERRAMIENTAS}:
        return {"content": [{"type": "text", "text": f"Herramienta desconocida: {nombre}"}], "isError": True}
    try:
        r = pedir_a_la_app(nombre, argumentos or {})
    except SinConexion as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    except Exception as exc:  # p. ej. tiempo de espera agotado
        return {"content": [{"type": "text", "text": f"Error al hablar con Mezquita PDF: {exc}"}], "isError": True}
    if "error" in r:
        return {"content": [{"type": "text", "text": r["error"]}], "isError": True}
    contenido = [{"type": "text", "text": r.get("texto", "Hecho.")}]
    if r.get("imagen"):
        contenido.append({"type": "image", "data": r["imagen"]["datos"], "mimeType": r["imagen"]["tipo"]})
    return {"content": contenido, "isError": False}


# ----------------------------------------------------------------------------
# Bucle JSON-RPC por stdio
# ----------------------------------------------------------------------------
def _atender(msg: dict) -> dict | None:
    metodo, ident = msg.get("method"), msg.get("id")
    if ident is None:  # notificación (p. ej. notifications/initialized): no se responde
        return None
    try:
        if metodo == "initialize":
            pedido = (msg.get("params") or {}).get("protocolVersion")
            from visor.version import VERSION
            resultado = {
                "protocolVersion": pedido if pedido in PROTOCOLOS else PROTOCOLOS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": NOMBRE_SERVIDOR, "title": "Mezquita PDF", "version": VERSION},
                "instructions": INSTRUCCIONES,
            }
        elif metodo == "ping":
            resultado = {}
        elif metodo == "tools/list":
            resultado = {"tools": HERRAMIENTAS}
        elif metodo == "tools/call":
            p = msg.get("params") or {}
            resultado = _llamar(p.get("name", ""), p.get("arguments") or {})
        elif metodo in LISTAS_VACIAS:
            resultado = {LISTAS_VACIAS[metodo]: []}
        else:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Método no admitido: {metodo}"}}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": ident, "result": resultado}


def main() -> int:
    salida = sys.stdout.buffer
    for linea in sys.stdin.buffer:
        if not linea.strip():
            continue
        try:
            msg = json.loads(linea)
        except json.JSONDecodeError:
            respuesta = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON no válido"}}
        else:
            respuesta = _atender(msg) if isinstance(msg, dict) else None
        if respuesta is not None:
            salida.write(json.dumps(respuesta, ensure_ascii=False).encode() + b"\n")
            salida.flush()
    return 0
