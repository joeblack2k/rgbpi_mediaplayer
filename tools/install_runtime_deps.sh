#!/bin/sh
set -eu

MODE="${1:---auto}"

want_install=0
if [ "$MODE" = "--force" ]; then
  want_install=1
fi

if ! command -v mpv >/dev/null 2>&1; then
  want_install=1
fi

if ! dpkg -s libdvdcss2 >/dev/null 2>&1; then
  want_install=1
fi

if [ "$want_install" -eq 0 ]; then
  echo "runtime_deps_ok"
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y mpv libdvd-pkg
dpkg-reconfigure libdvd-pkg
ldconfig || true

command -v mpv >/dev/null 2>&1
dpkg -s libdvdcss2 >/dev/null 2>&1

echo "runtime_deps_installed"
