#!/bin/sh
# Genera los iconos PNG de la PWA a partir de ../recursos/icono.png (1024×1024).
# Requiere macOS (sips) y el entorno virtual de la app de escritorio (Pillow) para
# quitar las transparencias del icono (iOS las pintaría de negro).
set -e
cd "$(dirname "$0")/.."
ORIGEN=../recursos/icono.png
DEST=public/icons
TMP=$(mktemp -d)
mkdir -p "$DEST"
PY=../.venv/bin/python
[ -x "$PY" ] || PY=python3
"$PY" scripts/generar_iconos.py "$ORIGEN" "$TMP"
# Icono «any» (con su margen y esquinas redondeadas, como en macOS)
sips -z 192 192 "$ORIGEN" --out "$DEST/icon-192.png" >/dev/null
sips -z 512 512 "$ORIGEN" --out "$DEST/icon-512.png" >/dev/null
# iOS: a sangre y opaco
sips -z 180 180 "$TMP/maestro_lleno.png" --out "$DEST/apple-touch-icon.png" >/dev/null
# Android y otros: maskable
sips -z 512 512 "$TMP/maestro_maskable.png" --out "$DEST/icon-maskable-512.png" >/dev/null
sips -z 192 192 "$TMP/maestro_maskable.png" --out "$DEST/icon-maskable-192.png" >/dev/null
# Favicon y logotipo de la interfaz
sips -z 32 32 "$ORIGEN" --out "$DEST/favicon-32.png" >/dev/null
sips -z 256 256 "$TMP/maestro_lleno.png" --out "$DEST/logo-256.png" >/dev/null
rm -rf "$TMP"
ls -l "$DEST"
