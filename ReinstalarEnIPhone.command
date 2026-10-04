#!/bin/bash
# Reinstala Mezquita PDF en el iPhone (por cable o por Wi-Fi) y renueva los 7 días
# de la firma gratuita. Doble clic en Finder o: ./ReinstalarEnIPhone.command
set -e
cd "$(dirname "$0")/web"
echo "📱 Buscando el iPhone (mismo Wi-Fi y desbloqueado, o conectado por cable)…"
TMP="$(mktemp)"
xcrun devicectl list devices --json-output "$TMP" >/dev/null 2>&1 || true
UDID="$(/usr/bin/python3 - "$TMP" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit()
for x in d.get("result", {}).get("devices", []):
    hw, c = x.get("hardwareProperties", {}), x.get("connectionProperties", {})
    if hw.get("reality") == "physical" and hw.get("platform") == "iOS" and c.get("pairingState") == "paired":
        print(hw.get("udid", "")); break
PY
)"
rm -f "$TMP"
if [ -z "$UDID" ]; then
  echo "❌ No encuentro el iPhone. Desbloquéalo, comprueba que está en el mismo Wi-Fi que el Mac"
  echo "   (o conéctalo por cable) y vuelve a intentarlo."
  read -n 1 -s -r -p "Pulsa una tecla para cerrar…" || true; exit 1
fi
echo "🔨 Compilando y firmando (renueva el permiso de 7 días)…"
[ -d node_modules ] || npm ci --silent
npm run build --silent >/dev/null
npx cap sync ios >/dev/null
xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Debug \
  -destination "generic/platform=iOS" -derivedDataPath ios/App/build_dispositivo \
  -allowProvisioningUpdates -quiet
echo "📲 Instalando en el iPhone…"
xcrun devicectl device install app --device "$UDID" ios/App/build_dispositivo/Build/Products/Debug-iphoneos/App.app >/dev/null
echo "✅ Listo: Mezquita PDF está instalada y funcionará 7 días más."
read -n 1 -s -r -p "Pulsa una tecla para cerrar…" || true
