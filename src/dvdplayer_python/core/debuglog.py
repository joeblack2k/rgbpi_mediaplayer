from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

LOG_PATH = Path(os.environ.get("DVDPLAYER_DEBUG_LOG", "/tmp/rgbpi-dvdplayer-python.log"))
_LOCK = threading.Lock()


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "ts": int(time.time() * 1000),
        "pid": os.getpid(),
        "event": event,
    }
    payload.update(fields)
    line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    with _LOCK:
        candidates = [LOG_PATH]
        try:
            app_dir = Path(os.environ.get("DVDPLAYER_APP_DIR", "")).expanduser()
        except Exception:
            app_dir = Path(".")
        candidates.append(app_dir / "state" / "runtime" / "rgbpi-dvdplayer-python.log")
        for path in candidates:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                return
            except Exception:
                continue


def log_path() -> str:
    return str(LOG_PATH)
