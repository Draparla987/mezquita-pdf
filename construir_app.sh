#!/bin/bash
# Crea "Mezquita PDF.app" en dist/.
#   ./construir_app.sh             → solo la app
#   ./construir_app.sh --dmg       → además, el instalador MezquitaPDF.dmg
#   ./construir_app.sh --instalar  → además, la copia a /Applications
set -e
cd "$(dirname "$0")"
[ -d .venv ] || ./instalar.sh
# Si Xcode está instalado pero sin aceptar su licencia, usar las herramientas de línea de comandos
if [ -d /Library/Developer/CommandLineTools ]; then export DEVELOPER_DIR=/Library/Developer/CommandLineTools; fi
.venv/bin/pip install -q pyinstaller
.venv/bin/pyinstaller --noconfirm --clean MezquitaPDF.spec
rm -rf "dist/Mezquita PDF" build
# Firma ad hoc: macOS identifica la app de forma estable (necesario para el Llavero)
codesign --force --deep --sign - "dist/Mezquita PDF.app"
echo
echo "✅ Aplicación creada en: $(pwd)/dist/Mezquita PDF.app"
for opcion in "$@"; do
  case "$opcion" in
    --dmg) ./recursos/crear_dmg.sh "MezquitaPDF.dmg" ;;
    --instalar)
      rm -rf "/Applications/Mezquita PDF.app"
      cp -R "dist/Mezquita PDF.app" /Applications/
      echo "✅ Copiada a /Applications" ;;
  esac
done
