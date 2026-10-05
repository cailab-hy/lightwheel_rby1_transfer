#!/usr/bin/env bash
# Meta Quest 2 VR collection: checks the USB/adb link, forwards the page port to the headset, then runs
# the collector with --input vr (it opens the page in the headset browser; press Enter VR there).
#   ./collect_vr.sh --task T1
#   ./collect_vr.sh --task T1 --motion-scale 0.8 --vr-record ~/vr_T1_input.jsonl
# Guide: README.md, section "VR(Meta Quest 2) 데이터 수집"
set -uo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PORT=8012
args=("$@")
for i in "${!args[@]}"; do
  [ "${args[$i]}" = "--vr-port" ] && PORT="${args[$((i + 1))]:-8012}"
done

if ! command -v adb >/dev/null; then
  echo "adb not installed: sudo apt install -y adb android-sdk-platform-tools-common" >&2; exit 1
fi
adb start-server >/dev/null 2>&1
STATE="$(adb devices | awk 'NR>1 && $2!="" {print $2; exit}')"
case "$STATE" in
  device) echo "Quest: $(adb shell getprop ro.product.model | tr -d '\r'), battery $(adb shell dumpsys battery | awk -F': ' '/level/ {print $2"%"; exit}' | tr -d '\r')";;
  unauthorized) echo "Headset not authorised: put it on and accept 'Allow USB debugging' (tick 'Always allow')" >&2; exit 1;;
  no) echo "No USB permission for the headset: add the Meta udev rule (README: VR 데이터 수집 > 1. PC 설정), adb kill-server, then replug" >&2; exit 1;;
  "") echo "No headset on USB: connect the data cable, wake the headset, check developer mode" >&2; exit 1;;
  *) echo "adb device state: $STATE" >&2; exit 1;;
esac
adb reverse "tcp:$PORT" "tcp:$PORT" >/dev/null || { echo "adb reverse tcp:$PORT failed" >&2; exit 1; }
trap 'adb reverse --remove "tcp:$PORT" >/dev/null 2>&1' EXIT
"$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/scripts/collect_keyboard.py" --input vr "$@"
