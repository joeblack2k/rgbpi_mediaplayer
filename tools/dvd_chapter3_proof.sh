#!/usr/bin/env bash
set -euo pipefail
APP=/media/sd/roms/ports/dvdplayer-python
RUNTIME="$APP/state/runtime"
SHOT="/home/pi/plex-proof/dvd-chapter3-proof.png"
ANALYSIS_TXT="/home/pi/plex-proof/dvd-chapter3-proof.txt"
ANALYSIS_JSON="/home/pi/plex-proof/dvd-chapter3-proof.gemini.json"

export DVDPLAYER_CONTROL_SOCKET="$RUNTIME/rgbpi-dvdplayer-api.sock"
export DVDPLAYER_STATE_PATH="$RUNTIME/rgbpi-dvdplayer-state.json"

python3 "$APP/dvdplayer_api.py" play-dvd
sleep 1

python3 "$APP/dvdplayer_api.py" remote-set-chapter 2 || true
sleep 1
python3 "$APP/dvdplayer_api.py" show-overlay start || true

sleep 1
/usr/local/bin/rpi-cap png > "$SHOT"
python3 "$APP/tools/analyze_screenshot_gemini.py" "$SHOT" --out-json "$ANALYSIS_JSON" > "$ANALYSIS_TXT"

echo "SHOT=$SHOT"
echo "ANALYSIS=$ANALYSIS_TXT"
cat "$ANALYSIS_TXT"
