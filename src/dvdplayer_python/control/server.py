from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Any

from dvdplayer_python.core.debuglog import log_event
from dvdplayer_python.core.models import Action


class ControlServer:
    def __init__(self, socket_path: str, state_path: str, queue: Queue, fallback_dir: Path | None = None):
        self.socket_path = Path(socket_path)
        self.state_path = Path(state_path)
        self.queue = queue
        self.fallback_dir = fallback_dir
        self.endpoint = f"unix:{self.socket_path}"
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        unix_candidates = [self.socket_path]
        if self.fallback_dir:
            unix_candidates.append(self.fallback_dir / self.socket_path.name)

        for candidate in unix_candidates:
            try:
                candidate.unlink(missing_ok=True)
                server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server.bind(str(candidate))
            except OSError as exc:
                log_event("control_bind_failed", transport="unix", socket=str(candidate), error=str(exc))
                continue

            with server:
                try:
                    os.chmod(candidate, 0o666)
                except OSError:
                    pass
                server.listen(8)
                self.endpoint = f"unix:{candidate}"
                log_event("control_listening", endpoint=self.endpoint)
                self._serve_unix(server)
            return

        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", 0))
        except OSError as exc:
            log_event("control_bind_failed", transport="tcp", error=str(exc))
            return

        with server:
            server.listen(8)
            host, port = server.getsockname()
            self.endpoint = f"tcp:{host}:{port}"
            log_event("control_listening", endpoint=self.endpoint)
            self._serve_tcp(server)

    def _serve_unix(self, server: socket.socket) -> None:
        while True:
            conn, _ = server.accept()
            with conn:
                raw = _read_command(conn)
                if not raw:
                    continue
                reply = self._handle(raw)
                _write_reply(conn, reply)

    def _serve_tcp(self, server: socket.socket) -> None:
        while True:
            conn, _ = server.accept()
            with conn:
                raw = _read_command(conn)
                if not raw:
                    continue
                reply = self._handle(raw)
                _write_reply(conn, reply)

    def _emit_action(self, action: Action) -> str:
        self.queue.put(("action", action))
        return "ok"

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _wait_ready(self, timeout: float) -> str:
        end = time.time() + timeout
        while time.time() < end:
            state = self._read_state()
            if state.get("screen"):
                return json.dumps({"ok": True, "state": state})
            time.sleep(0.1)
        return json.dumps({"ok": False, "error": "timeout", "state": self._read_state()})

    def _wait_screen(self, screen: str, timeout: float) -> str:
        end = time.time() + timeout
        while time.time() < end:
            state = self._read_state()
            if state.get("screen") == screen:
                return json.dumps({"ok": True, "state": state})
            time.sleep(0.1)
        return json.dumps({"ok": False, "error": "timeout", "state": self._read_state()})

    def _handle(self, cmd: str) -> str:
        log_event("control_command", cmd=cmd)
        if cmd == "ping":
            return "pong"
        if cmd == "status":
            return json.dumps(self._read_state())
        if cmd == "raw-state":
            return json.dumps(self._read_state())
        if cmd.startswith("wait-ready"):
            parts = cmd.split()
            timeout = float(parts[1]) if len(parts) > 1 else 8.0
            return self._wait_ready(timeout)
        if cmd.startswith("wait-screen "):
            parts = cmd.split()
            if len(parts) < 2:
                return json.dumps({"ok": False, "error": "missing screen"})
            timeout = float(parts[2]) if len(parts) > 2 else 8.0
            return self._wait_screen(parts[1], timeout)

        if cmd == "wake":
            self.queue.put(("wake", None))
            return "ok"
        if cmd == "play-dvd":
            self.queue.put(("play-dvd", None))
            return "ok"
        if cmd.startswith("screenshot "):
            self.queue.put(("screenshot", Path(cmd.split(" ", 1)[1].strip())))
            return "ok"
        if cmd.startswith("show-overlay "):
            self.queue.put(("show-overlay", cmd.split(" ", 1)[1].strip()))
            return "ok"

        if cmd.startswith("debug-ui "):
            self.queue.put(("debug-ui", cmd.split(" ", 1)[1].strip()))
            return "ok"

        if cmd.startswith("keyboard-fill "):
            self.queue.put(("keyboard-fill", cmd.split(" ", 1)[1]))
            return "ok"
        if cmd.startswith("keyboard-submit "):
            self.queue.put(("keyboard-submit", cmd.split(" ", 1)[1]))
            return "ok"

        if cmd.startswith("remote-play-json "):
            try:
                payload = json.loads(cmd.split(" ", 1)[1].strip())
            except json.JSONDecodeError:
                return "invalid-json"
            self.queue.put(("remote-play-json", payload))
            return "ok"

        if cmd in {"youtube-link-start", "youtube_link_start"}:
            self.queue.put(("youtube_link_start", None))
            return "ok"
        if cmd in {"youtube-unlink", "youtube_unlink"}:
            self.queue.put(("youtube_unlink", None))
            return "ok"
        if cmd in {"youtube-queue-next", "youtube_queue_next"}:
            self.queue.put(("youtube_queue_next", None))
            return "ok"
        if cmd in {"youtube-queue-clear", "youtube_queue_clear"}:
            self.queue.put(("youtube_queue_clear", None))
            return "ok"

        mapping = {
            "up": Action.UP,
            "down": Action.DOWN,
            "left": Action.LEFT,
            "right": Action.RIGHT,
            "accept": Action.ACCEPT,
            "a": Action.ACCEPT,
            "back": Action.BACK,
            "b": Action.BACK,
            "start": Action.START,
            "select": Action.SELECT,
            "x": Action.X,
            "home": Action.HOME,
            "quit": Action.QUIT,
            "remote-menu": Action.START,
        }
        action = mapping.get(cmd)
        if action:
            return self._emit_action(action)

        if cmd == "remote-playpause":
            self.queue.put(("remote-playpause", None))
            return "ok"
        if cmd == "remote-pause":
            self.queue.put(("remote-pause", True))
            return "ok"
        if cmd == "remote-resume":
            self.queue.put(("remote-pause", False))
            return "ok"
        if cmd == "remote-stop":
            self.queue.put(("remote-stop", None))
            return "ok"
        if cmd.startswith("remote-seek-ms "):
            try:
                ms = int(cmd.split(" ", 1)[1])
            except ValueError:
                return "invalid-seek"
            self.queue.put(("remote-seek-ms", ms))
            return "ok"
        if cmd.startswith("remote-seek-relative "):
            try:
                sec = int(cmd.split(" ", 1)[1])
            except ValueError:
                return "invalid-seek"
            self.queue.put(("remote-seek-relative", sec))
            return "ok"
        if cmd.startswith("remote-set-chapter "):
            try:
                chapter = int(cmd.split(" ", 1)[1])
            except ValueError:
                return "invalid-chapter"
            self.queue.put(("remote-set-chapter", chapter))
            return "ok"
        if cmd.startswith("remote-step-chapter "):
            try:
                delta = int(cmd.split(" ", 1)[1])
            except ValueError:
                return "invalid-chapter"
            self.queue.put(("remote-step-chapter", delta))
            return "ok"

        return "unknown"


def _read_command(conn: Any) -> str:
    try:
        return conn.recv(65536).decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _write_reply(conn: Any, reply: str) -> None:
    try:
        conn.sendall((reply + "\n").encode("utf-8"))
    except Exception:
        pass
