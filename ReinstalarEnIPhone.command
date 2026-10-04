#!/bin/bash
# Reinstala Mezquita PDF en el iPhone (por cable o por Wi-Fi) y renueva los 7 días
# de la firma gratuita.
#   Doble clic en Finder (o ./ReinstalarEnIPhone.command)  → reinstala ahora
#   ./ReinstalarEnIPhone.command --auto  → modo automático (tarea diaria): solo actúa si
#       han pasado 5 días o más desde la última vez y avisa con una notificación.
set -o pipefail
export PATH="$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")/web" || exit 1

AUTO=0; [ "$1" == "--auto" ] && AUTO=1
DATOS="$HOME/Library/Application Support/MezquitaPDF"
MARCA="$DATOS/ultima_reinstalacion_iphone"
DIAS_MIN=5
mkdir -p "$DATOS"

avisar() {  # título, mensaje
  osascript -e "display notification \"$2\" with title \"$1\" sound name \"default\"" >/dev/null 2>&1 || true
}
terminar() {  # código
  [ $AUTO -eq 0 ] && { read -n 1 -s -r -p "Pulsa una tecla para cerrar…" || true; echo; }
  exit "$1"
}

if [ $AUTO -eq 1 ] && [ -f "$MARCA" ]; then
  ultima=$(cat "$MARCA"); ahora=$(date +%s)
  dias=$(( (ahora - ultima) / 86400 ))
  if [ $dias -lt $DIAS_MIN ]; then
    echo "$(date '+%F %T') · Última reinstalación hace $dias día(s): no hace falta."
    exit 0
  fi
fi

echo "$(date '+%F %T') · 📱 Buscando el iPhone (mismo Wi-Fi y desbloqueado, o por cable)…"
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
  echo "❌ No encuentro el iPhone."
  avisar "Mezquita PDF" "No encuentro tu iPhone para renovar la app. Desbloquéalo en el mismo Wi-Fi y abre ReinstalarEnIPhone.command"
  terminar 1
fi

# Copia automática: trae la última versión publicada en GitHub antes de compilar
if [ $AUTO -eq 1 ] && [ -d ../.git ]; then
  git -C .. pull --ff-only -q >/dev/null 2>&1 && echo "↻ Código actualizado desde GitHub" || echo "(sin actualizar desde GitHub)"
  npm ci --silent >/dev/null 2>&1 || true
fi

echo "🔨 Compilando y firmando (renueva el permiso de 7 días)…"
LOG_COMPILACION="$DATOS/compilacion_iphone.log"
{ [ -d node_modules ] || npm ci --silent; } && npm run build --silent >/dev/null && npx cap sync ios >/dev/null \
  && xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Debug \
       -destination "generic/platform=iOS" -derivedDataPath ios/App/build_dispositivo \
       -allowProvisioningUpdates -quiet >"$LOG_COMPILACION" 2>&1 || {
  echo "❌ Falló la compilación (detalles en $LOG_COMPILACION)."
  avisar "Mezquita PDF" "No se pudo preparar la app del iPhone. Abre ReinstalarEnIPhone.command para ver el error."
  terminar 1
}

echo "📲 Instalando en el iPhone…"
if xcrun devicectl device install app --device "$UDID" ios/App/build_dispositivo/Build/Products/Debug-iphoneos/App.app >/dev/null 2>&1; then
  date +%s > "$MARCA"
  echo "✅ Listo: Mezquita PDF está instalada y funcionará 7 días más."
  [ $AUTO -eq 1 ] && avisar "Mezquita PDF" "App del iPhone renovada: funcionará 7 días más ✅"
  terminar 0
else
  echo "❌ No se pudo instalar (¿iPhone bloqueado o fuera del Wi-Fi?)."
  avisar "Mezquita PDF" "No se pudo renovar la app del iPhone. Desbloquéalo y abre ReinstalarEnIPhone.command"
  terminar 1
fi
