#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

APP_RUNTIME_DIR = Path("/media/sd/roms/ports/dvdplayer-python/state/runtime")
DEFAULT_SOCKET_PATH = Path(
    os.environ.get(
        "DVDPLAYER_CONTROL_SOCKET",
        str(APP_RUNTIME_DIR / "rgbpi-dvdplayer-api.sock" if APP_RUNTIME_DIR.exists() else "/tmp/rgbpi-dvdplayer-api.sock"),
    )
)
STATE_PATH = Path(
    os.environ.get(
        "DVDPLAYER_STATE_PATH",
        str(APP_RUNTIME_DIR / "rgbpi-dvdplayer-state.json" if APP_RUNTIME_DIR.exists() else "/tmp/rgbpi-dvdplayer-state.json"),
    )
)
STATE_MAX_AGE_MS = 5000


def _parse_endpoint(value: str | None) -> Tuple[str, object]:
    raw = (value or "").strip()
    if not raw:
        return ("unix", str(DEFAULT_SOCKET_PATH))
    if raw.startswith("unix:"):
        return ("unix", raw.split(":", 1)[1])
    if raw.startswith("tcp:"):
        rest = raw.split(":", 1)[1]
        host, _, port_s = rest.rpartition(":")
        if not host or not port_s:
            raise ValueError(f"invalid tcp endpoint: {raw}")
        return ("tcp", (host, int(port_s)))
    if raw.startswith("/"):
        return ("unix", raw)
    raise ValueError(f"unsupported endpoint: {raw}")


def read_state_file() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def discover_endpoint() -> Tuple[str, object]:
    env = os.environ.get("DVDPLAYER_API_ENDPOINT")
    if env:
        return _parse_endpoint(env)

    try:
        state = read_state_file()
    except Exception:
        state = None

    if isinstance(state, dict):
        endpoint = state.get("control_socket")
        if isinstance(endpoint, str) and endpoint.strip():
            try:
                return _parse_endpoint(endpoint)
            except Exception:
                pass

    return ("unix", str(DEFAULT_SOCKET_PATH))


def send_command(command: str, timeout: float = 1.5) -> str:
    transport, target = discover_endpoint()
    if transport == "unix":
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(target))
            client.sendall(command.encode("utf-8"))
            client.shutdown(socket.SHUT_WR)
            return client.recv(65536).decode("utf-8", "replace").strip()

    if transport == "tcp":
        host, port = target
        with socket.create_connection((host, port), timeout=timeout) as client:
            client.sendall(command.encode("utf-8"))
            client.shutdown(socket.SHUT_WR)
            return client.recv(65536).decode("utf-8", "replace").strip()

    raise RuntimeError(f"unsupported endpoint transport: {transport}")


def pid_alive(pid: Optional[int]) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def runtime_status() -> dict:
    state = None
    state_error = None
    try:
        state = read_state_file()
    except Exception as exc:
        state_error = str(exc)

    endpoint = discover_endpoint()
    endpoint_text = state.get("control_socket") if isinstance(state, dict) else None
    if not isinstance(endpoint_text, str) or not endpoint_text:
        kind, target = endpoint
        endpoint_text = f"{kind}:{target[0]}:{target[1]}" if kind == "tcp" else f"unix:{target}"

    socket_ok = False
    socket_error = None
    try:
        socket_ok = send_command("ping") == "pong"
    except Exception as exc:
        socket_error = str(exc)

    pid = state.get("pid") if isinstance(state, dict) else None
    updated_at = state.get("updated_at_unix_ms") if isinstance(state, dict) else None
    now_ms = int(time.time() * 1000)
    state_age_ms = now_ms - updated_at if isinstance(updated_at, int) else None
    healthy = bool(socket_ok and isinstance(state_age_ms, int) and state_age_ms <= STATE_MAX_AGE_MS and pid_alive(pid))

    endpoint_kind, endpoint_target = endpoint
    default_socket_exists = DEFAULT_SOCKET_PATH.exists()
    active_socket_exists = Path(endpoint_target).exists() if endpoint_kind == "unix" else True

    return {
        "endpoint": endpoint_text,
        "socket_path": str(DEFAULT_SOCKET_PATH),
        "socket_exists": default_socket_exists,
        "active_socket_exists": active_socket_exists,
        "socket_responding": socket_ok,
        "socket_error": socket_error,
        "state_path": str(STATE_PATH),
        "state_exists": STATE_PATH.exists(),
        "state_error": state_error,
        "state_age_ms": state_age_ms,
        "pid": pid,
        "pid_alive": pid_alive(pid),
        "healthy": healthy,
        "state": state,
    }


def wait_ready(timeout: float) -> dict:
    end = time.time() + timeout
    last = runtime_status()
    while time.time() < end:
        last = runtime_status()
        if last["healthy"]:
            return last
        time.sleep(0.1)
    raise RuntimeError(json.dumps(last, indent=2))


def wait_screen(screen: str, timeout: float) -> dict:
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = runtime_status()
        state = last.get("state") if isinstance(last, dict) else None
        if isinstance(state, dict) and state.get("screen") == screen:
            return state
        time.sleep(0.1)
    raise RuntimeError(json.dumps(last, indent=2) if last else f"timeout waiting for {screen}")


def print_json(obj: dict) -> None:
    print(json.dumps(obj, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="dvdplayer-python API helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping")
    sub.add_parser("status")
    sub.add_parser("state")
    sub.add_parser("raw-state")

    wr = sub.add_parser("wait-ready")
    wr.add_argument("timeout", nargs="?", type=float, default=8.0)

    ws = sub.add_parser("wait-screen")
    ws.add_argument("screen")
    ws.add_argument("timeout", nargs="?", type=float, default=8.0)

    shot = sub.add_parser("screenshot")
    shot.add_argument("path")

    send = sub.add_parser("send")
    send.add_argument("raw", nargs=argparse.REMAINDER)

    act = sub.add_parser("action")
    act.add_argument("name")

    kf = sub.add_parser("keyboard-fill")
    kf.add_argument("text", nargs=argparse.REMAINDER)

    ks = sub.add_parser("keyboard-submit")
    ks.add_argument("text", nargs=argparse.REMAINDER)

    du = sub.add_parser("debug-ui")
    du.add_argument("name")

    rp = sub.add_parser("remote-play-json")
    rp.add_argument("payload")

    for name in [
        "wake",
        "home",
        "up",
        "down",
        "left",
        "right",
        "accept",
        "back",
        "start",
        "select",
        "x",
        "quit",
        "play-dvd",
        "remote-menu",
        "remote-playpause",
        "remote-pause",
        "remote-resume",
        "remote-stop",
    ]:
        sub.add_parser(name)

    rsm = sub.add_parser("remote-seek-ms")
    rsm.add_argument("ms", type=int)

    rsr = sub.add_parser("remote-seek-relative")
    rsr.add_argument("sec", type=int)

    rch = sub.add_parser("remote-set-chapter")
    rch.add_argument("chapter", type=int)

    rcs = sub.add_parser("remote-step-chapter")
    rcs.add_argument("delta", type=int)

    so = sub.add_parser("show-overlay")
    so.add_argument("name")

    args = parser.parse_args()

    try:
        if args.cmd == "ping":
            print(send_command("ping"))
        elif args.cmd == "status":
            print_json(runtime_status())
        elif args.cmd == "state":
            print_json(read_state_file())
        elif args.cmd == "raw-state":
            print_json(read_state_file())
        elif args.cmd == "wait-ready":
            print_json(wait_ready(args.timeout))
        elif args.cmd == "wait-screen":
            print_json(wait_screen(args.screen, args.timeout))
        elif args.cmd == "screenshot":
            print(send_command(f"screenshot {args.path}"))
        elif args.cmd == "send":
            if not args.raw:
                raise RuntimeError("send requires raw command")
            print(send_command(" ".join(args.raw)))
        elif args.cmd == "action":
            print(send_command(args.name))
        elif args.cmd == "keyboard-fill":
            print(send_command(f"keyboard-fill {' '.join(args.text)}"))
        elif args.cmd == "keyboard-submit":
            print(send_command(f"keyboard-submit {' '.join(args.text)}"))
        elif args.cmd == "debug-ui":
            print(send_command(f"debug-ui {args.name}"))
        elif args.cmd == "remote-play-json":
            print(send_command(f"remote-play-json {args.payload}"))
        elif args.cmd == "remote-seek-ms":
            print(send_command(f"remote-seek-ms {args.ms}"))
        elif args.cmd == "remote-seek-relative":
            print(send_command(f"remote-seek-relative {args.sec}"))
        elif args.cmd == "remote-set-chapter":
            print(send_command(f"remote-set-chapter {args.chapter}"))
        elif args.cmd == "remote-step-chapter":
            print(send_command(f"remote-step-chapter {args.delta}"))
        elif args.cmd == "show-overlay":
            print(send_command(f"show-overlay {args.name}"))
        else:
            print(send_command(args.cmd))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
