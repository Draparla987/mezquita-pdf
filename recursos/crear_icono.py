"""Genera recursos/icono.icns y recursos/icono.png a partir del logotipo de Mezquita PDF."""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from visor.tema import imagen_icono_app

app = QGuiApplication(sys.argv)
base = os.path.dirname(os.path.abspath(__file__))
img = imagen_icono_app(1024)
carpeta = os.path.join(base, "icono.iconset")
os.makedirs(carpeta, exist_ok=True)
for t in (16, 32, 128, 256, 512):
    img.scaled(t, t, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(f"{carpeta}/icon_{t}x{t}.png")
    img.scaled(t * 2, t * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(f"{carpeta}/icon_{t}x{t}@2x.png")
img.save(os.path.join(base, "icono.png"))
subprocess.run(["iconutil", "-c", "icns", carpeta, "-o", os.path.join(base, "icono.icns")], check=True)
shutil.rmtree(carpeta)
print("icono.icns creado")
