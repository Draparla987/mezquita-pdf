#!/bin/bash
# Prepara el entorno de Python con las dependencias.
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
echo "✅ Dependencias instaladas. Ejecuta ./MezquitaPDF.command para abrir el programa."
