from __future__ import annotations

import importlib
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Optional

from dvdplayer_python.core.debuglog import log_event


YOUTUBE_LINK_UNLINKED = "unlinked"
YOUTUBE_LINK_CODE_PENDING = "code_pending"
YOUTUBE_LINK_LINKED = "linked"
BUNDLED_NODE_RELATIVE_PATH = Path("runtime/node/linux-arm/node")
BUNDLED_YTDLP_RELATIVE_PATH = Path("runtime/yt_dlp/linux-arm/yt-dlp")
RECEIVER_PACKAGE_RELATIVE_PATH = Path("node_modules/yt-cast-receiver/package.json")


def _app_dir_for_runtime() -> Path:
    # src/dvdplayer_python/media/youtube_receiver.py -> app dir
    return Path(__file__).resolve().parents[3]


def _vendored_ytdlp_root() -> Path:
    return Path(__file__).resolve().parents[1] / "vendor"


def _module_is_within(module: object, root: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str) or not module_file.strip():
        return False
    module_path = Path(module_file).resolve()
    root_path = root.resolve()
    try:
        return module_path.is_relative_to(root_path)
    except AttributeError:
        module_text = str(module_path)
        root_text = str(root_path)
        return module_text == root_text or module_text.startswith(root_text + os.sep)


def _which(binary: str) -> Optional[str]:
    preferred = os.environ.get("DVDPLAYER_YTDLP_BIN") if binary == "yt-dlp" else ""
    if preferred:
        p = Path(preferred).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    if binary == "yt-dlp":
        bundled = _app_dir_for_runtime() / BUNDLED_YTDLP_RELATIVE_PATH
        if bundled.is_file() and os.access(bundled, os.X_OK):
            return str(bundled)
    return _which_in_path(binary)


def _which_in_path(binary: str) -> Optional[str]:
    for root in os.environ.get("PATH", "").split(":"):
        candidate = Path(root) / binary
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _resolve_node_binary(app_dir: Path) -> tuple[Optional[str], Optional[str], str]:
    override = os.environ.get("DVDPLAYER_YOUTUBE_NODE_BIN", "").strip()
    if override:
        candidate = Path(override).expanduser()
        if not candidate.exists():
            return None, "node_override_missing", "env"
        if not candidate.is_file():
            return None, "node_override_not_file", "env"
        if not os.access(candidate, os.X_OK):
            return None, "node_override_not_executable", "env"
        return str(candidate), None, "env"

    bundled = app_dir / BUNDLED_NODE_RELATIVE_PATH
    if bundled.exists():
        if bundled.is_file() and os.access(bundled, os.X_OK):
            return str(bundled), None, "bundled"
        return None, "node_bundled_not_executable", "bundled"

    path_node = _which_in_path("node")
    if path_node:
        return path_node, None, "path"
    return None, "node_bundled_missing", "bundled"


@dataclass
class YouTubeReceiverState:
    link_state: str = YOUTUBE_LINK_UNLINKED
    code: str = ""
    screen_name: Optional[str] = None
    queue_size: int = 0
    receiver_healthy: bool = False
    receiver_version: Optional[str] = None
    last_error: Optional[str] = None


class YouTubeReceiverManager:
    def __init__(self, app_dir: Path, state_dir: Path, control_queue: Queue):
        self.app_dir = app_dir
        self.state_dir = state_dir
        self.control_queue = control_queue
        self.receiver_dir = self.app_dir / "runtime" / "youtube_receiver"
        self.receiver_script = self.receiver_dir / "sidecar.mjs"
        self.receiver_package = self.receiver_dir / RECEIVER_PACKAGE_RELATIVE_PATH
        self.receiver_state_dir = self.state_dir / "youtube"
        self.receiver_state_dir.mkdir(parents=True, exist_ok=True)
        self.receiver_log = self.receiver_state_dir / "youtube-sidecar.log"
        self.state = YouTubeReceiverState()
        self._proc: Optional[subprocess.Popen] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._running = True
        self._enabled = False
        self._last_start_attempt = 0.0
        self._lock = threading.Lock()

    def ensure_started(self) -> bool:
        self._enabled = True
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return True
            return self._start_locked()

    def tick(self, now: float) -> None:
        if not self._running or not self._enabled:
            return
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return
            if now - self._last_start_attempt < 3.0:
                return
            self._start_locked()

    def stop(self) -> None:
        self._running = False
        self._enabled = False
        with self._lock:
            proc = self._proc
            self._proc = None
        if not proc:
            return
        self._send_json({"command": "shutdown"}, proc)
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self.state.receiver_healthy = False
        self.state.link_state = YOUTUBE_LINK_UNLINKED
        self.state.code = ""
        self.state.queue_size = 0

    def link_start(self) -> bool:
        if not self.ensure_started():
            return False
        self.state.link_state = YOUTUBE_LINK_CODE_PENDING
        self._send_json({"command": "link_start"})
        return True

    def unlink(self) -> bool:
        if not self.ensure_started():
            return False
        self._send_json({"command": "unlink"})
        self.state.link_state = YOUTUBE_LINK_UNLINKED
        self.state.code = ""
        self.state.queue_size = 0
        return True

    def queue_next(self) -> bool:
        if not self.ensure_started():
            return False
        self._send_json({"command": "queue_next"})
        return True

    def queue_clear(self) -> bool:
        if not self.ensure_started():
            return False
        self._send_json({"command": "queue_clear"})
        return True

    def _start_locked(self) -> bool:
        self._last_start_attempt = time.time()
        node, node_error, node_source = _resolve_node_binary(self.app_dir)
        if not node:
            self.state.receiver_healthy = False
            self.state.last_error = node_error or "node_missing"
            log_event("youtube_receiver_start_failed", error=self.state.last_error)
            return False
        if node_source == "path":
            log_event(
                "youtube_receiver_node_fallback",
                reason="node_bundled_missing",
                node=node,
                bundled_path=str(self.app_dir / BUNDLED_NODE_RELATIVE_PATH),
            )
        if not self.receiver_script.exists():
            self.state.receiver_healthy = False
            self.state.last_error = "sidecar_missing"
            log_event("youtube_receiver_start_failed", error="sidecar_missing", script=str(self.receiver_script))
            return False
        if not self.receiver_package.exists():
            self.state.receiver_healthy = False
            self.state.last_error = "node_modules_missing"
            log_event(
                "youtube_receiver_start_failed",
                error="node_modules_missing",
                package=str(self.receiver_package),
            )
            return False

        cmd_env = os.environ.get("DVDPLAYER_YOUTUBE_SIDECAR_CMD", "").strip()
        if cmd_env:
            cmd = shlex.split(cmd_env)
        else:
            cmd = [
                node,
                str(self.receiver_script),
                "--state-dir",
                str(self.receiver_state_dir),
                "--device-name",
                os.environ.get("DVDPLAYER_YOUTUBE_DEVICE_NAME", "RGBPI Mediaplayer"),
                "--screen-name",
                os.environ.get("DVDPLAYER_YOUTUBE_SCREEN_NAME", "YouTube on RGBPI"),
            ]

        try:
            self.receiver_log.parent.mkdir(parents=True, exist_ok=True)
            log_file = self.receiver_log.open("ab")
        except Exception:
            log_file = subprocess.DEVNULL

        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(self.receiver_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=log_file,
                text=True,
                env=dict(os.environ),
                bufsize=1,
            )
        except Exception as exc:
            self._proc = None
            self.state.receiver_healthy = False
            self.state.last_error = str(exc)
            log_event("youtube_receiver_start_failed", error=str(exc), cmd=" ".join(cmd))
            return False

        self.state.receiver_healthy = False
        self.state.last_error = None
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stdout_thread.start()
        log_event("youtube_receiver_started", cmd=" ".join(cmd), pid=self._proc.pid)
        return True

    def _send_json(self, payload: dict, proc: Optional[subprocess.Popen] = None) -> None:
        target = proc or self._proc
        if not target or target.poll() is not None or not target.stdin:
            return
        try:
            target.stdin.write(json.dumps(payload) + "\n")
            target.stdin.flush()
        except Exception as exc:
            self.state.receiver_healthy = False
            self.state.last_error = str(exc)
            log_event("youtube_receiver_send_failed", error=str(exc), payload=payload.get("command"))

    def _read_stdout(self) -> None:
        proc = self._proc
        if not proc or not proc.stdout:
            return
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                log_event("youtube_receiver_line_invalid", line=line[:300])
                continue
            self._apply_sidecar_state(payload)
            self.control_queue.put(("youtube-sidecar-event", payload))
        code = proc.poll()
        self.state.receiver_healthy = False
        self.control_queue.put(("youtube-sidecar-event", {"event": "receiver_exit", "exit_code": code}))
        log_event("youtube_receiver_exited", code=code)

    def _apply_sidecar_state(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        event = str(payload.get("event") or "").strip().lower()
        if event in {"receiver_ready", "status"}:
            self.state.receiver_healthy = True
            version = payload.get("receiver_version")
            if isinstance(version, str) and version.strip():
                self.state.receiver_version = version.strip()
            screen_name = payload.get("screen_name")
            if isinstance(screen_name, str) and screen_name.strip():
                self.state.screen_name = screen_name.strip()
        if event == "link_state":
            state = str(payload.get("state") or "").strip().lower()
            if state in {YOUTUBE_LINK_UNLINKED, YOUTUBE_LINK_CODE_PENDING, YOUTUBE_LINK_LINKED}:
                self.state.link_state = state
            code = payload.get("code")
            self.state.code = str(code).strip() if isinstance(code, str) else ""
            screen_name = payload.get("screen_name")
            if isinstance(screen_name, str) and screen_name.strip():
                self.state.screen_name = screen_name.strip()
        queue_size = payload.get("queue_size")
        if isinstance(queue_size, (int, float)):
            self.state.queue_size = max(0, int(queue_size))
        if event == "receiver_error":
            self.state.receiver_healthy = False
            self.state.last_error = str(payload.get("error") or "receiver_error")


def _load_vendored_ytdlp_class():
    vendored_root = _vendored_ytdlp_root()
    vendored_package = vendored_root / "yt_dlp" / "__init__.py"
    if not vendored_package.exists():
        return None
    try:
        existing = sys.modules.get("yt_dlp")
        if existing is not None and not _module_is_within(existing, vendored_root):
            # Avoid mixing system yt_dlp modules with our vendored package.
            for name in list(sys.modules):
                if name == "yt_dlp" or name.startswith("yt_dlp."):
                    sys.modules.pop(name, None)

        root_text = str(vendored_root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)

        yt_dlp = importlib.import_module("yt_dlp")
        if not _module_is_within(yt_dlp, vendored_root):
            return None
        YoutubeDL = getattr(yt_dlp, "YoutubeDL", None)
        if YoutubeDL is None:
            return None

        return YoutubeDL
    except Exception:
        return None


def _resolve_with_vendored_ytdlp(ref: str, fmt: str, timeout_s: float) -> dict:
    youtube_dl_cls = _load_vendored_ytdlp_class()
    if youtube_dl_cls is None:
        raise ModuleNotFoundError("vendored_yt_dlp_missing")

    attempts = [fmt, None]
    last_error = "vendored yt_dlp resolution failed"
    for attempt_format in attempts:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": max(1.0, float(timeout_s)),
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        if attempt_format:
            ydl_opts["format"] = attempt_format
        try:
            with youtube_dl_cls(ydl_opts) as ydl:
                payload = ydl.extract_info(ref, download=False)
            if isinstance(payload, dict):
                return payload
            last_error = "vendored yt_dlp returned invalid payload"
        except Exception as exc:
            detail = str(exc).strip()
            if detail:
                last_error = detail
    raise RuntimeError(last_error)


def _resolve_with_ytdlp_binary(ref: str, fmt: str, timeout_s: float) -> dict:
    ytdlp = _which("yt-dlp")
    if not ytdlp:
        bundled = _app_dir_for_runtime() / BUNDLED_YTDLP_RELATIVE_PATH
        raise FileNotFoundError(f"yt-dlp not found (expected bundled: {bundled})")

    attempts: list[list[str]] = [
        [
            ytdlp,
            "--no-warnings",
            "--no-playlist",
            "-f",
            fmt,
            "--extractor-args",
            "youtube:player_client=android,web",
            "--print-json",
            ref,
        ],
        [
            ytdlp,
            "--no-warnings",
            "--no-playlist",
            "--print-json",
            ref,
        ],
    ]
    payload: Optional[dict] = None
    last_error = "yt-dlp resolution failed"
    for cmd in attempts:
        try:
            out = subprocess.check_output(
                cmd,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.output or "").strip()
            if detail:
                last_error = detail
            continue
        line = ""
        for candidate in out.splitlines():
            c = candidate.strip()
            if c:
                line = c
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        break
    if not isinstance(payload, dict):
        raise RuntimeError(last_error)
    return payload


def _payload_to_stream_result(payload: dict, fallback_ref: str) -> dict:
    stream_url = str(payload.get("url") or "").strip()
    if not stream_url:
        requested_formats = payload.get("requested_formats")
        if isinstance(requested_formats, list):
            for fmt_item in requested_formats:
                if not isinstance(fmt_item, dict):
                    continue
                candidate = str(fmt_item.get("manifest_url") or fmt_item.get("url") or "").strip()
                if candidate:
                    stream_url = candidate
                    break
    if not stream_url:
        formats = payload.get("formats")
        if isinstance(formats, list):
            for fmt_item in formats:
                if not isinstance(fmt_item, dict):
                    continue
                candidate = str(fmt_item.get("manifest_url") or fmt_item.get("url") or "").strip()
                if candidate:
                    stream_url = candidate
                    break
    if not stream_url:
        raise RuntimeError("yt-dlp returned no playable stream url")

    width = payload.get("width")
    height = payload.get("height")
    fps = payload.get("fps")
    return {
        "stream_url": stream_url,
        "title": str(payload.get("title") or "YouTube"),
        "webpage_url": str(payload.get("webpage_url") or fallback_ref),
        "width": int(width) if isinstance(width, (int, float)) else None,
        "height": int(height) if isinstance(height, (int, float)) else None,
        "fps": float(fps) if isinstance(fps, (int, float)) else None,
        "video_id": str(payload.get("id") or ""),
    }


def resolve_youtube_stream(video_ref: str, timeout_s: float = 25.0) -> dict:
    ref = str(video_ref or "").strip()
    if not ref:
        raise ValueError("missing YouTube video reference")
    if not ref.startswith("http://") and not ref.startswith("https://"):
        ref = f"https://www.youtube.com/watch?v={ref}"

    fmt = os.environ.get(
        "DVDPLAYER_YOUTUBE_FORMAT",
        "best[height<=576]/best",
    )
    errors: list[str] = []
    payload: Optional[dict] = None

    try:
        payload = _resolve_with_vendored_ytdlp(ref, fmt, timeout_s)
    except Exception as exc:
        detail = str(exc).strip() or "vendored_yt_dlp_failed"
        errors.append(f"vendored:{detail}")
        log_event("youtube_resolve_vendored_failed", error=detail)

    if not isinstance(payload, dict):
        try:
            payload = _resolve_with_ytdlp_binary(ref, fmt, timeout_s)
        except Exception as exc:
            detail = str(exc).strip() or "binary_yt_dlp_failed"
            errors.append(f"binary:{detail}")
            raise RuntimeError("; ".join(errors)) from exc

    return _payload_to_stream_result(payload, ref)
