#!/bin/bash
# Crea un instalador .dmg con la app y un acceso directo a Aplicaciones.
set -e
cd "$(dirname "$0")/.."
NOMBRE="${1:-MezquitaPDF.dmg}"
TMP="$(mktemp -d)"
cp -R "dist/Mezquita PDF.app" "$TMP/"
ln -s /Applications "$TMP/Aplicaciones"
rm -f "$NOMBRE"
# En las máquinas de GitHub, hdiutil a veces responde «Resource busy»: se reintenta
for intento in 1 2 3 4 5; do
  if hdiutil create -volname "Mezquita PDF" -srcfolder "$TMP" -ov -format UDZO "$NOMBRE" >/dev/null; then
    break
  fi
  if [ "$intento" -eq 5 ]; then
    echo "❌ hdiutil no ha podido crear el .dmg" >&2
    exit 1
  fi
  echo "hdiutil ocupado; reintento en $((intento * 5)) s…" >&2
  sleep $((intento * 5))
done
rm -rf "$TMP"
echo "✅ $NOMBRE"
