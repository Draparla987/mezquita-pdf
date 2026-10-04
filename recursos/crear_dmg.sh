#!/bin/bash
# Crea un instalador .dmg con la app y un acceso directo a Aplicaciones.
set -e
cd "$(dirname "$0")/.."
NOMBRE="${1:-MezquitaPDF.dmg}"
TMP="$(mktemp -d)"
cp -R "dist/Mezquita PDF.app" "$TMP/"
ln -s /Applications "$TMP/Aplicaciones"
rm -f "$NOMBRE"
hdiutil create -volname "Mezquita PDF" -srcfolder "$TMP" -ov -format UDZO "$NOMBRE" >/dev/null
rm -rf "$TMP"
echo "✅ $NOMBRE"
