#!/bin/sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
STATE_FILE="$APP_DIR/state/runtime/test-mode.json"

pkill -f 'python.*-m dvdplayer_python.main' >/dev/null 2>&1 || true
pkill -x mpv >/dev/null 2>&1 || true
pkill -x ffplay >/dev/null 2>&1 || true

PREV_TTY="$(sed -n 's/.*\"previous_tty\":\"\\([0-9][0-9]*\\)\".*/\\1/p' "$STATE_FILE" 2>/dev/null | head -n 1)"
if [ -n "${PREV_TTY:-}" ]; then
  chvt "$PREV_TTY" >/dev/null 2>&1 || true
fi

rm -f "$STATE_FILE"
