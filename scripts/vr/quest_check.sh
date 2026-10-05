#!/usr/bin/env bash
# Stage-1 check: adb + Quest 2 state, adb reverse, then a local WebXR page that reports
# controller poses/buttons back to this terminal.
# Usage: ./scripts/vr/quest_check.sh [port] [--no-open] [--teleop] [--motion-scale S] [--record FILE]
#   The page is opened in the headset browser over adb (fresh URL, so an old tab is never reused);
#   --no-open skips that.
set -uo pipefail
PORT=8012
if [[ "${1:-}" =~ ^[0-9]+$ ]]; then PORT="$1"; shift; fi
OPEN=1; ARGS=()
for x in "$@"; do [ "$x" = "--no-open" ] && OPEN=0 || ARGS+=("$x"); done
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ok() { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
bad() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
info() { printf '       %s\n' "$*"; }

echo "[1] adb"
if ! command -v adb >/dev/null; then
  bad "adb not installed:  sudo apt install -y adb android-sdk-platform-tools-common"; exit 1
fi
ok "$(adb version | head -1)"

echo "[2] USB device"
if lsusb | grep -qi '2833:'; then ok "Meta/Oculus USB device: $(lsusb | grep -i '2833:' | head -1 | cut -d' ' -f6-)"
else bad "no Meta/Oculus device (vendor 2833) on USB: check the cable (data, not charge-only) and the port"; fi

echo "[3] adb authorisation"
adb start-server >/dev/null 2>&1
STATE="$(adb devices | awk 'NR>1 && $2!="" {print $2; exit}')"
case "$STATE" in
  device) ok "authorised: $(adb devices -l | awk 'NR==2')";;
  unauthorized) bad "unauthorised: put the headset on and accept 'Allow USB debugging' (tick 'Always allow')"; exit 1;;
  "no permissions"*|"") bad "no device/permission: developer mode on? udev rule? (see the stage-1 guide)"; adb devices; exit 1;;
  *) bad "state: $STATE"; exit 1;;
esac

echo "[4] headset"
info "model:    $(adb shell getprop ro.product.model | tr -d '\r') ($(adb shell getprop ro.product.device | tr -d '\r'))"
info "build:    $(adb shell getprop ro.build.display.id | tr -d '\r')"
info "battery:  $(adb shell dumpsys battery | awk -F': ' '/level/ {print $2"%"; exit}' | tr -d '\r')"
BROWSER="$(adb shell dumpsys package com.oculus.browser 2>/dev/null | awk -F= '/versionName/ {print $2; exit}' | tr -d '\r')"
[ -n "$BROWSER" ] && ok "Meta Quest Browser $BROWSER" || bad "Meta Quest Browser (com.oculus.browser) not found"

echo "[5] adb reverse tcp:$PORT"
adb reverse "tcp:$PORT" "tcp:$PORT" >/dev/null && ok "$(adb reverse --list | grep ":$PORT" | head -1)" || { bad "adb reverse failed"; exit 1; }

echo
URL="http://localhost:$PORT/?v=$(date +%s)"
if [ "$OPEN" = 1 ]; then
  echo "[6] opening $URL in the headset browser (a fresh tab: no stale page)"
  ( sleep 1.5; adb shell am start -a android.intent.action.VIEW -d "$URL" com.oculus.browser >/dev/null 2>&1 \
      || echo "  could not open the page over adb: open http://localhost:$PORT in the headset yourself" ) &
fi
echo "In the headset: Meta Quest Browser -> http://localhost:$PORT  -> check the 3 OK lines -> Enter VR"
echo "The terminal must show '[page] connected' after the page opens."
echo "Move both controllers and press buttons; poses/buttons appear below. Ctrl+C to stop."
echo
trap 'adb reverse --remove "tcp:$PORT" >/dev/null 2>&1' EXIT
python3 "$HERE/quest_check.py" "$PORT" ${ARGS[@]+"${ARGS[@]}"}
