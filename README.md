# rgbpi_mediaplayer

Python implementation of the RGB-Pi media player, intended to run from the RGB-Pi
ports directory.

## Expected install path

```bash
/media/sd/roms/ports/rgbpi_mediaplayer
```

The launch scripts resolve `DVDPLAYER_APP_DIR` from their own location, so this
folder can be moved if needed.

## Standalone runtime

This folder is shipped as a standalone app package for Linux ARM.
No runtime `apt`, `pip`, or `npm` install steps are required by the launcher.

## Run

```bash
cd /media/sd/roms/ports/rgbpi_mediaplayer
./start_rgbpi_dvdplayer_python.sh
```

## Runtime files

Default runtime directory:

```bash
state/runtime
```

Key files:
- control socket: `state/runtime/rgbpi-dvdplayer-api.sock`
- state snapshot: `state/runtime/rgbpi-dvdplayer-state.json`
- player log: `state/runtime/rgbpi-dvdplayer-python.log`
- launch log: `state/runtime/rgbpi-dvdplayer-python-launch.log`

Useful environment overrides:
- `DVDPLAYER_APP_DIR`
- `DVDPLAYER_WINDOWED=1`
- `DVDPLAYER_CONTROL_SOCKET`
- `DVDPLAYER_STATE_PATH`
- `DVDPLAYER_DEBUG_LOG`
- `DVDPLAYER_MPV_LOG`

## API helper

```bash
./dvdplayer_api.py status
./dvdplayer_api.py wait-ready 15
./dvdplayer_api.py show-overlay start
./dvdplayer_api.py screenshot /tmp/shot.png
./dvdplayer_api.py remote-play-json '{"title":"Trailer","url":"https://example/media.mp4","kind":"video_file"}'
```

## YouTube TV Code (Standalone)

This app now expects YouTube TV Code support to be self-contained inside this
folder, without runtime `apt/pip/npm` installs.

Bundled runtime paths:
- bundled MPV binary: `bin/mpv`
- bundled Linux ARM rootfs libs (incl. `libdvdcss`): `runtime/linux-arm64-rootfs/`
- sidecar script: `runtime/youtube_receiver/sidecar.mjs`
- sidecar packages: `runtime/youtube_receiver/node_modules/`
- vendored `yt_dlp` module: `src/dvdplayer_python/vendor/yt_dlp/`
- bundled `yt-dlp` fallback binary: `runtime/yt_dlp/linux-arm/yt-dlp`
- bundled Linux ARM Node runtime: `runtime/node/linux-arm/node`

Expected target:
- Linux ARM devices (RGB-Pi style deployment)

Optional overrides:
- `DVDPLAYER_YOUTUBE_NODE_BIN` (explicit Node binary override)
- `DVDPLAYER_YOUTUBE_SIDECAR_CMD` (fully custom sidecar command)
- `DVDPLAYER_YOUTUBE_DEVICE_NAME`
- `DVDPLAYER_YOUTUBE_SCREEN_NAME`
- `DVDPLAYER_YOUTUBE_FORMAT`
- `DVDPLAYER_YTDLP_BIN` (external fallback binary, development only)
- `DVDPLAYER_MPV_BIN` (override bundled mpv binary)

Quick validation:

```bash
./dvdplayer_api.py youtube-link-start
./dvdplayer_api.py status
```

## Runtime checker

`runtime/check_runtime_bundle.sh` validates that bundled runtime files are present.
The launcher runs this check at startup and aborts if the bundle is incomplete.
