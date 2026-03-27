#!/bin/sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
TARGET_TTY="${1:-tty2}"
TARGET_DEV="/dev/${TARGET_TTY#/dev/}"
RUNTIME_DIR="$APP_DIR/state/runtime"
STATE_FILE="$RUNTIME_DIR/test-mode.json"
PREV_TTY="$(fgconsole 2>/dev/null || echo 1)"

mkdir -p "$RUNTIME_DIR"
cat >"$STATE_FILE" <<EOF
{"previous_tty":"$PREV_TTY","target_tty":"${TARGET_TTY#/dev/}","started_at":"$(date -Iseconds)"}
EOF

cleanup() {
  PREV="$(sed -n 's/.*\"previous_tty\":\"\\([0-9][0-9]*\\)\".*/\\1/p' "$STATE_FILE" 2>/dev/null | head -n 1)"
  if [ -n "${PREV:-}" ]; then
    chvt "$PREV" >/dev/null 2>&1 || true
  fi
  rm -f "$STATE_FILE"
}

trap cleanup EXIT INT TERM

export DVDPLAYER_ACTIVE_TTY="$TARGET_DEV"
openvt -f -c "${TARGET_TTY#tty}" -- /bin/sh -lc "export DVDPLAYER_ACTIVE_TTY='$TARGET_DEV'; exec '$APP_DIR/start_rgbpi_dvdplayer_python.sh'"
exit 0
