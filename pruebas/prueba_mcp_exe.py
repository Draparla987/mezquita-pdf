"""Hace de «app de Claude» con el programa empaquetado: lo lanza con --mcp y le habla por JSON-RPC.

    python pruebas/prueba_mcp_exe.py "<ruta a mezquita-mcp.exe o a Mezquita PDF>" [--estado]

Con --estado también pide «estado», lo que obliga a abrir Mezquita PDF si no lo está (la prueba
completa del camino real: extensión → abre la app → canal local → respuesta).
"""

import json
import subprocess
import sys

exe = sys.argv[1]
peticiones = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "prueba", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]
if "--estado" in sys.argv:
    peticiones.append({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "estado", "arguments": {}}})
entrada = "".join(json.dumps(p) + "\n" for p in peticiones).encode()
salida = subprocess.run([exe, "--mcp"], input=entrada, capture_output=True, timeout=120).stdout.decode("utf-8")
respuestas = {r["id"]: r for r in map(json.loads, filter(None, salida.splitlines()))}

ini = respuestas[1]["result"]
assert ini["serverInfo"]["name"] == "mezquita-pdf", ini
print("✔ initialize:", ini["protocolVersion"], ini["serverInfo"]["version"])
herramientas = respuestas[2]["result"]["tools"]
assert len(herramientas) >= 18, len(herramientas)
print("✔ herramientas:", len(herramientas))
if 3 in respuestas:
    r = respuestas[3]["result"]
    texto = r["content"][0]["text"]
    assert not r["isError"], texto
    print("✔ estado (la app se abrió y respondió):", texto[:120].replace("\n", " "))
print("✅ Extensión para Claude correcta")
