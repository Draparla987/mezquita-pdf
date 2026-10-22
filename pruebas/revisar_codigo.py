"""Falla si algún archivo usa un nombre que no está definido ni importado.

Así se detectó (tarde) que la ventana de WhatsApp de la 2.7.0 usaba `teclas` sin importarla.
Uso:  pip install pyflakes && python pruebas/revisar_codigo.py
"""

import sys
from pathlib import Path

from pyflakes import api, messages
from pyflakes.reporter import Reporter

RAIZ = Path(__file__).resolve().parent.parent
GRAVES = (messages.UndefinedName, messages.UndefinedExport, messages.UndefinedLocal)


class Recoger(Reporter):
    def __init__(self):
        super().__init__(sys.stdout, sys.stderr)
        self.graves = []

    def flake(self, mensaje):
        if isinstance(mensaje, GRAVES):
            self.graves.append(mensaje)


informe = Recoger()
archivos = [RAIZ / "main.py", *sorted((RAIZ / "visor").glob("*.py")), *sorted((RAIZ / "pruebas").glob("*.py"))]
for archivo in archivos:
    api.checkPath(str(archivo), informe)
for m in informe.graves:
    print(f"✘ {Path(m.filename).relative_to(RAIZ)}:{m.lineno}: {m.message % m.message_args}")
if informe.graves:
    sys.exit(1)
print(f"✅ Sin nombres sin definir ({len(archivos)} archivos revisados)")
