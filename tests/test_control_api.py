from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from queue import Queue

from dvdplayer_python.control.server import ControlServer
from dvdplayer_python.core.models import Action


def _load_helper_module():
    mod_path = Path(__file__).resolve().parents[1] / "dvdplayer_api.py"
    spec = importlib.util.spec_from_file_location("dvdplayer_api_helper", mod_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_control_server_dispatch_and_remote_play_json(tmp_path: Path):
    q: Queue = Queue()
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"screen": "home"}), encoding="utf-8")
    server = ControlServer(str(tmp_path / "sock.sock"), str(state_path), q)

    assert server._handle("ping") == "pong"
    assert server._handle("up") == "ok"
    event, payload = q.get_nowait()
    assert event == "action"
    assert payload == Action.UP

    assert server._handle("x") == "ok"
    event, payload = q.get_nowait()
    assert event == "action"
    assert payload == Action.X

    assert server._handle('remote-play-json {"title":"Demo","url":"http://example.com/v.mp4"}') == "ok"
    event, payload = q.get_nowait()
    assert event == "remote-play-json"
    assert payload["title"] == "Demo"

    assert server._handle("remote-play-json not-json") == "invalid-json"
    assert server._handle("status") == json.dumps({"screen": "home"})


def test_api_helper_endpoint_discovery_from_state(tmp_path: Path, monkeypatch):
    helper = _load_helper_module()
    state_path = tmp_path / "runtime-state.json"
    state_path.write_text(
        json.dumps(
            {
                "control_socket": "unix:/tmp/custom.sock",
                "pid": 1,
                "updated_at_unix_ms": 0,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(helper, "STATE_PATH", state_path)
    monkeypatch.delenv("DVDPLAYER_API_ENDPOINT", raising=False)

    transport, target = helper.discover_endpoint()
    assert transport == "unix"
    assert target == "/tmp/custom.sock"


def test_api_helper_env_endpoint_wins(monkeypatch):
    helper = _load_helper_module()
    monkeypatch.setenv("DVDPLAYER_API_ENDPOINT", "tcp:127.0.0.1:4242")
    transport, target = helper.discover_endpoint()
    assert transport == "tcp"
    assert target == ("127.0.0.1", 4242)
