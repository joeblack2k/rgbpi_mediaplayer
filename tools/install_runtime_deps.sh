#!/bin/sh
set -eu

MODE="${1:---check}"
SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
APP_DIR="$(CDPATH='' cd -- "${SCRIPT_DIR}/.." && pwd)"
YOUTUBE_DIR="${APP_DIR}/tools/youtube_receiver"
BUNDLED_NODE="${APP_DIR}/tools/node_runtime/linux-arm/node"
BUNDLED_YTDLP_BIN="${APP_DIR}/tools/yt_dlp/linux-arm/yt-dlp"
VENDORED_YTDLP_DIR="${APP_DIR}/src/dvdplayer_python/vendor/yt_dlp"
BUNDLED_MPV_BIN="${APP_DIR}/bin/mpv"
BUNDLED_RUNTIME_ROOT="${APP_DIR}/runtime/linux-arm64-rootfs"
BUNDLED_DVDCSS_SO2="${BUNDLED_RUNTIME_ROOT}/usr/lib/aarch64-linux-gnu/libdvdcss.so.2"
BUNDLED_DVDCSS_REAL="${BUNDLED_RUNTIME_ROOT}/usr/lib/aarch64-linux-gnu/libdvdcss.so.2.2.0"

missing=0

check_exec() {
  path="$1"
  label="$2"
  if [ ! -x "$path" ]; then
    echo "$label" >&2
    missing=1
  fi
}

check_file() {
  path="$1"
  label="$2"
  if [ ! -f "$path" ]; then
    echo "$label" >&2
    missing=1
  fi
}

check_dir() {
  path="$1"
  label="$2"
  if [ ! -d "$path" ]; then
    echo "$label" >&2
    missing=1
  fi
}

# Standalone mode: validate only, never install from apt/pip/npm.
[ "$MODE" = "--check" ] || [ "$MODE" = "--auto" ] || [ "$MODE" = "--force" ] || true

check_file "${YOUTUBE_DIR}/sidecar.mjs" "youtube_runtime_missing_sidecar"
check_file "${YOUTUBE_DIR}/node_modules/yt-cast-receiver/package.json" "youtube_runtime_missing_node_modules"
check_dir "${VENDORED_YTDLP_DIR}" "youtube_runtime_missing_vendored_yt_dlp"
check_exec "${BUNDLED_NODE}" "youtube_runtime_missing_node_binary"
check_exec "${BUNDLED_YTDLP_BIN}" "youtube_runtime_missing_ytdlp_binary"
check_exec "${BUNDLED_MPV_BIN}" "runtime_missing_mpv_binary"
check_file "${BUNDLED_DVDCSS_REAL}" "runtime_missing_libdvdcss_real"
if [ ! -e "${BUNDLED_DVDCSS_SO2}" ]; then
  echo "runtime_missing_libdvdcss_so2" >&2
  missing=1
fi
check_dir "${BUNDLED_RUNTIME_ROOT}/lib/aarch64-linux-gnu" "runtime_missing_rootfs_lib"
check_dir "${BUNDLED_RUNTIME_ROOT}/usr/lib/aarch64-linux-gnu" "runtime_missing_rootfs_usr_lib"

if [ "$missing" -ne 0 ]; then
  echo "runtime_deps_missing" >&2
  exit 1
fi

echo "runtime_deps_ok"
