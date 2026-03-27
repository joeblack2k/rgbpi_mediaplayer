#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _run(cmd: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _api_call(api: Path, *args: str, expect_json: bool = False) -> Any:
    proc = _run(["python3", str(api), *args], timeout=25.0)
    if proc.returncode != 0:
        raise RuntimeError(f"api failed ({' '.join(args)}): {proc.stderr.strip() or proc.stdout.strip()}")
    out = proc.stdout.strip()
    if expect_json:
        return json.loads(out) if out else {}
    return out


def _status(api: Path) -> dict[str, Any]:
    data = _api_call(api, "status", expect_json=True)
    if not isinstance(data, dict):
        raise RuntimeError("invalid status payload")
    state = data.get("state")
    if isinstance(state, dict):
        return state
    return data


def _wait_screen(api: Path, screen: str, timeout: float = 20.0) -> dict[str, Any]:
    data = _api_call(api, "wait-screen", screen, str(timeout), expect_json=True)
    # Helper currently returns plain state on success, and raises on timeout.
    if isinstance(data, dict) and data.get("screen") == screen:
        return data
    if isinstance(data, dict) and data.get("ok") and isinstance(data.get("state"), dict):
        return data.get("state") or {}
    raise RuntimeError(f"wait-screen failed for {screen}: {json.dumps(data, ensure_ascii=False)}")


def _wait_not_playback(api: Path, timeout: float = 12.0) -> dict[str, Any]:
    end = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < end:
        last = _status(api)
        if last.get("screen") != "playback":
            return last
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting to leave playback: {json.dumps(last, ensure_ascii=False)}")


def _overlay_items(api: Path, expected_overlay: str, timeout: float = 4.0) -> list[str]:
    end = time.time() + timeout
    state: dict[str, Any] = {}
    while time.time() < end:
        state = _status(api)
        if state.get("overlay") == expected_overlay:
            break
        time.sleep(0.15)
    if state.get("overlay") != expected_overlay:
        raise RuntimeError(f"expected overlay {expected_overlay}, got {state.get('overlay')}")
    items = state.get("overlay_items") or []
    if not isinstance(items, list):
        raise RuntimeError("overlay_items is not a list")
    return [str(x) for x in items]


def _screenshot(api: Path, out_dir: Path, name: str) -> None:
    _api_call(api, "screenshot", str(out_dir / name))


def _action(api: Path, name: str) -> None:
    _api_call(api, "action", name)
    time.sleep(0.18)


def _open_overlay(api: Path, name: str) -> None:
    _api_call(api, "show-overlay", name)
    time.sleep(0.25)


def _select_overlay_index(api: Path, idx: int) -> None:
    for _ in range(idx):
        _action(api, "down")
    _action(api, "accept")


def _mpv_pids() -> list[int]:
    proc = _run(["pgrep", "-f", r"/usr/bin/mpv .*rgbpi-dvdplayer-ipc"], timeout=3.0)
    if proc.returncode != 0:
        return []
    pids: list[int] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _record(steps: list[dict[str, Any]], name: str, ok: bool, detail: str = "") -> None:
    steps.append(
        {
            "ts": int(time.time() * 1000),
            "step": name,
            "ok": ok,
            "detail": detail,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate every playback overlay option via dvdplayer API")
    parser.add_argument(
        "--app-dir",
        default=str(Path(__file__).resolve().parents[1]),
        help="dvdplayer-python app directory",
    )
    parser.add_argument(
        "--video-path",
        default=os.environ.get("DVDPLAYER_OVERLAY_TEST_VIDEO", ""),
        help="Absolute path to a non-DVD test video file",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Output directory for screenshots/results (default: state/runtime/overlay-matrix-<timestamp>)",
    )
    parser.add_argument(
        "--dvd-uri",
        default=os.environ.get("DVDPLAYER_OVERLAY_TEST_DVD_URI", ""),
        help="Authored-DVD test URI (default: re-use --video-path as authored DVD source)",
    )
    parser.add_argument(
        "--dvd-kind",
        default="video_file",
        choices=["video_file", "dvd_iso", "dvd_folder", "optical_drive"],
        help="Kind used for authored-DVD overlay matrix",
    )
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    api = app_dir / "dvdplayer_api.py"
    runtime_dir = app_dir / "state" / "runtime"
    log_file = runtime_dir / "rgbpi-dvdplayer-python.log"
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (runtime_dir / f"overlay-matrix-{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    result_path = out_dir / "result.json"
    log_extract = out_dir / "log-extract.jsonl"
    steps: list[dict[str, Any]] = []
    errors: list[str] = []
    start_line = 0

    try:
        if log_file.exists():
            start_line = len(log_file.read_text(encoding="utf-8", errors="ignore").splitlines())

        if not api.exists():
            raise RuntimeError(f"missing API helper: {api}")
        _api_call(api, "wait-ready", "20", expect_json=True)
        _record(steps, "wait_ready", True)

        # Non-DVD matrix
        if not args.video_path:
            raise RuntimeError("missing --video-path (or DVDPLAYER_OVERLAY_TEST_VIDEO) for non-DVD matrix")
        is_remote_uri = "://" in args.video_path
        video_path = Path(args.video_path).expanduser()
        if not is_remote_uri and not video_path.is_file():
            raise RuntimeError(f"non-DVD test file not found: {video_path}")

        _api_call(api, "home")
        payload = json.dumps(
            {
                "title": video_path.name if not is_remote_uri else "overlay-test-video",
                "url": args.video_path if is_remote_uri else str(video_path),
                "kind": "video_file",
                "authored_dvd": False,
            }
        )
        _api_call(api, "remote-play-json", payload)
        _wait_screen(api, "playback", timeout=25.0)
        _record(steps, "non_dvd_playback_start", True, str(video_path))
        _screenshot(api, out_dir, "non_dvd-playback.png")

        _open_overlay(api, "start")
        non_dvd_items = _overlay_items(api, "start_menu")
        if non_dvd_items != ["TOGGLE PAUSE", "RETURN TO BROWSER"]:
            raise RuntimeError(f"non-DVD overlay mismatch: {non_dvd_items}")
        _record(steps, "non_dvd_overlay_items", True, json.dumps(non_dvd_items))
        _screenshot(api, out_dir, "non_dvd-start-overlay.png")

        _open_overlay(api, "start")
        _select_overlay_index(api, 0)
        st = _status(api)
        if st.get("screen") != "playback":
            raise RuntimeError(f"toggle pause left playback: {json.dumps(st, ensure_ascii=False)}")
        _record(steps, "non_dvd_toggle_pause", True)

        _open_overlay(api, "seek")
        seek_items = _overlay_items(api, "seek")
        _record(steps, "non_dvd_seek_overlay_open", True, json.dumps(seek_items))
        _screenshot(api, out_dir, "non_dvd-seek-overlay.png")
        _action(api, "left")
        _action(api, "right")
        _action(api, "accept")
        _action(api, "start")
        st = _status(api)
        if st.get("screen") != "playback":
            raise RuntimeError(f"seek overlay flow left playback unexpectedly: {json.dumps(st, ensure_ascii=False)}")
        _record(steps, "non_dvd_seek_overlay_actions", True)

        _open_overlay(api, "start")
        _select_overlay_index(api, 1)
        st = _wait_not_playback(api, timeout=12.0)
        _record(steps, "non_dvd_return_to_browser", True, st.get("screen", ""))

        # Authored DVD matrix
        _api_call(api, "home")
        dvd_uri = args.dvd_uri or args.video_path
        dvd_payload = json.dumps(
            {
                "title": "overlay-test-dvd",
                "url": dvd_uri,
                "kind": args.dvd_kind,
                "authored_dvd": True,
            }
        )
        _api_call(api, "remote-play-json", dvd_payload)
        _wait_screen(api, "playback", timeout=25.0)
        _record(steps, "dvd_playback_start", True, f"{args.dvd_kind}:{dvd_uri}")
        _screenshot(api, out_dir, "dvd-playback.png")

        _open_overlay(api, "start")
        dvd_items = _overlay_items(api, "start_menu")
        expected_dvd = ["TOGGLE PAUSE", "DVD MENU", "CHAPTER -", "CHAPTER +", "RETURN TO BROWSER"]
        if dvd_items != expected_dvd:
            raise RuntimeError(f"DVD overlay mismatch: {dvd_items}")
        _record(steps, "dvd_overlay_items", True, json.dumps(dvd_items))
        _screenshot(api, out_dir, "dvd-start-overlay.png")

        for idx, name in enumerate(expected_dvd[:-1]):
            _open_overlay(api, "start")
            _select_overlay_index(api, idx)
            st = _status(api)
            if st.get("screen") != "playback":
                raise RuntimeError(f"{name} left playback unexpectedly: {json.dumps(st, ensure_ascii=False)}")
            _record(steps, f"dvd_{name.lower().replace(' ', '_').replace('+', 'plus').replace('-', 'minus')}", True)

        _open_overlay(api, "seek")
        _overlay_items(api, "seek")
        _screenshot(api, out_dir, "dvd-seek-overlay.png")
        _action(api, "left")
        _action(api, "right")
        _action(api, "accept")
        _action(api, "start")
        st = _status(api)
        if st.get("screen") != "playback":
            raise RuntimeError(f"dvd seek flow left playback unexpectedly: {json.dumps(st, ensure_ascii=False)}")
        _record(steps, "dvd_seek_overlay_actions", True)

        _open_overlay(api, "start")
        _select_overlay_index(api, 4)
        st = _wait_not_playback(api, timeout=12.0)
        _record(steps, "dvd_return_to_browser", True, st.get("screen", ""))

        # Ensure no orphan mpv after returning to browser
        state_after = _status(api)
        if state_after.get("screen") != "playback":
            time.sleep(0.7)
            if _mpv_pids():
                raise RuntimeError(f"orphan mpv detected: {_mpv_pids()}")
        _record(steps, "orphan_check", True)

    except Exception as exc:
        errors.append(str(exc))
        _record(steps, "failure", False, str(exc))
        # Only mark orphan mpv when app is dead/unreachable.
        app_alive = False
        try:
            st = _status(api)
            app_alive = bool(st.get("pid_alive", True))
        except Exception:
            app_alive = False
        pids = _mpv_pids()
        if (not app_alive) and pids:
            errors.append(f"orphan mpv detected: {pids}")
            _record(steps, "orphan_check_on_failure", False, json.dumps(pids))
    finally:
        try:
            if log_file.exists():
                lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                excerpt = lines[start_line:] if start_line < len(lines) else []
                log_extract.write_text("\n".join(excerpt) + ("\n" if excerpt else ""), encoding="utf-8")
        except Exception as exc:
            errors.append(f"log extract failed: {exc}")

        result = {
            "ok": len(errors) == 0,
            "started_at": ts,
            "finished_at": time.strftime("%Y%m%d-%H%M%S"),
            "app_dir": str(app_dir),
            "video_path": args.video_path,
            "out_dir": str(out_dir),
            "errors": errors,
            "steps": steps,
            "log_extract": str(log_extract),
        }
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
