#!/bin/bash
# Abre Mezquita PDF desde el código fuente (doble clic en Finder).
cd "$(dirname "$0")"
[ -d .venv ] || ./instalar.sh
exec .venv/bin/python main.py "$@"
