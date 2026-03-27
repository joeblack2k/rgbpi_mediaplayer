# dvdplayer-python

Python port scaffold for the RGB-Pi DVDPlayer Rust app.

## Setup

```bash
cd /home/homelab/rgbpi/dvdplayer-python
python3 -m venv .venv
.venv/bin/pip install pygame pytest requests
```

## Run

```bash
cd /home/homelab/rgbpi/dvdplayer-python
./start_rgbpi_dvdplayer_python.sh
```

Environment:
- `DVDPLAYER_APP_DIR`: app working directory for state/config files.
- `DVDPLAYER_WINDOWED=1`: disable fullscreen.
- `DVDPLAYER_CONTROL_SOCKET`: override control socket path.
- `DVDPLAYER_STATE_PATH`: override runtime state JSON path.
- `DVDPLAYER_DEBUG_LOG`: override debug log file path.

Runtime paths (compatible with current tooling):
- control endpoint: `unix:/tmp/rgbpi-dvdplayer-api.sock` (auto-fallback to `state/rgbpi-dvdplayer-api.sock` or `tcp:127.0.0.1:<port>` if unix bind fails)
- state snapshot: `/tmp/rgbpi-dvdplayer-state.json`
- debug log: `/tmp/rgbpi-dvdplayer-python.log`

## Debugging

Follow live behavior:

```bash
tail -f /tmp/rgbpi-dvdplayer-python.log
```

API helper:

```bash
./dvdplayer_api.py status
./dvdplayer_api.py debug-ui browser-mode
./dvdplayer_api.py down
./dvdplayer_api.py accept
./dvdplayer_api.py show-overlay start
./dvdplayer_api.py screenshot /tmp/shot.png
./dvdplayer_api.py remote-play-json '{"title":"Trailer","url":"https://example/media.mp4","kind":"plex_video"}'
```
