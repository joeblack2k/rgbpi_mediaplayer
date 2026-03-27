#!/bin/sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
API="$APP_DIR/dvdplayer_api.py"
OUT_DIR="${1:-$APP_DIR/state/runtime/validation}"
TOKEN_FILE="${DVDPLAYER_GEMINI_TOKEN_FILE:-/home/pi/token.key}"

mkdir -p "$OUT_DIR"

python3 "$API" wait-ready 15 >/dev/null
python3 "$API" screenshot "$OUT_DIR/home.png" >/dev/null
python3 "$API" action down >/dev/null
python3 "$API" action down >/dev/null
python3 "$API" action down >/dev/null
python3 "$API" screenshot "$OUT_DIR/settings.png" >/dev/null

python3 "$API" show-overlay start >/dev/null || true
sleep 1
python3 "$API" screenshot "$OUT_DIR/start-overlay.png" >/dev/null || true

python3 "$API" show-overlay seek >/dev/null || true
sleep 1
python3 "$API" screenshot "$OUT_DIR/seek-overlay.png" >/dev/null || true

if [ -f "$TOKEN_FILE" ]; then
  for image in "$OUT_DIR"/*.png; do
    [ -f "$image" ] || continue
    python3 "$APP_DIR/tools/analyze_screenshot_gemini.py" \
      "$image" \
      --token-file "$TOKEN_FILE" \
      --prompt "Inspect this RGB-Pi DVD player screen. Report clipped text, off-screen UI, selected row, footer readability, and whether the layout matches a compact CRT menu." \
      --out-json "$image.json" \
      >"$image.txt" || true
  done
fi
