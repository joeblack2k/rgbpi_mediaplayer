from __future__ import annotations

import sys
import types

try:
    import pygame  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    class _DummySurface:
        def __init__(self, width=320, height=240):
            self._width = width
            self._height = height

        def fill(self, _color):
            return None

        def blit(self, _surface, _rect):
            return None

        def get_rect(self, **kwargs):
            rect = types.SimpleNamespace(topleft=(0, 0), topright=(0, 0), center=(0, 0))
            for key, value in kwargs.items():
                setattr(rect, key, value)
            return rect

        def get_width(self):
            return self._width

        def get_height(self):
            return self._height

    class _DummyFont:
        def __init__(self, _name, size, bold=False):
            self._size = int(size)
            self._char_w = max(4, self._size // 2 + (1 if bold else 0))

        def render(self, text, _antialias, _color):
            width, height = self.size(text)
            return _DummySurface(width, height)

        def size(self, text):
            return (len(str(text)) * self._char_w, self._size + 2)

    class _DummyClock:
        def tick(self, _fps):
            return None

    _dummy_screen = _DummySurface(320, 240)
    sys.modules["pygame"] = types.SimpleNamespace(
        K_UP=273,
        K_DOWN=274,
        K_LEFT=276,
        K_RIGHT=275,
        K_RETURN=13,
        K_SPACE=32,
        K_ESCAPE=27,
        K_b=98,
        K_s=115,
        K_TAB=9,
        K_BACKSPACE=8,
        K_x=120,
        K_h=104,
        K_q=113,
        QUIT=12,
        KEYDOWN=2,
        FULLSCREEN=0,
        init=lambda: None,
        quit=lambda: None,
        Rect=lambda x, y, w, h: (x, y, w, h),
        display=types.SimpleNamespace(set_mode=lambda *_args, **_kwargs: _dummy_screen, flip=lambda: None),
        mouse=types.SimpleNamespace(set_visible=lambda *_args, **_kwargs: None),
        font=types.SimpleNamespace(SysFont=lambda name, size, bold=False: _DummyFont(name, size, bold)),
        draw=types.SimpleNamespace(rect=lambda *_args, **_kwargs: None),
        event=types.SimpleNamespace(get=lambda: []),
        image=types.SimpleNamespace(save=lambda *_args, **_kwargs: None),
        time=types.SimpleNamespace(Clock=lambda: _DummyClock()),
    )

from dvdplayer_python.core.models import ListItem, Screen
from dvdplayer_python.main import App
from dvdplayer_python.media.network_backend import BrowseEntry


def test_scan_network_sets_busy_label(monkeypatch):
    app = App.__new__(App)
    seen: dict[str, str] = {}

    def fake_start_busy(context, label, return_screen, return_section):
        seen["context"] = context
        seen["label"] = label
        seen["section"] = return_section
        seen["screen"] = return_screen.value

    class DummyThread:
        def __init__(self, target=None, args=(), daemon=False):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr("dvdplayer_python.main.threading.Thread", DummyThread)
    app._start_busy = fake_start_busy
    app._scan_network_worker = lambda protocol: None

    app.scan_network("SMB")
    assert seen["label"] == "SCANNING FOR SMB"

    app.scan_network("NFS")
    assert seen["label"] == "SCANNING FOR NFS"


def test_smb_host_opens_auth_popup():
    app = App.__new__(App)
    app.section = "SCAN SMB"
    app.set_screen = lambda screen, section: (setattr(app, "screen", screen), setattr(app, "section", section))

    app._open_smb_auth_popup({"protocol": "SMB", "host": "smb-host-a", "display_name": "NAS"})

    assert app.screen == Screen.CONFIRM
    assert app.confirm_options == ["GUEST", "LOGIN"]
    assert app.confirm_payload["host"]["host"] == "smb-host-a"


def test_nfs_host_bypasses_auth_popup():
    app = App.__new__(App)
    called: dict[str, object] = {}
    app._open_smb_auth_popup = lambda host: called.setdefault("popup", host)
    app._start_network_host_browse = lambda host, username, password: called.setdefault(
        "browse", (host, username, password)
    )

    item = ListItem(
        title="nfs-host-a",
        subtitle="NFS nfs-host-a",
        kind="host",
        payload={"host": {"protocol": "NFS", "host": "nfs-host-a", "display_name": "NFS NAS"}},
    )

    app.activate_list_item(item)
    assert "popup" not in called
    assert called["browse"][0]["protocol"] == "NFS"


def test_login_submit_saves_credentials_and_browses():
    class DummyNetwork:
        def __init__(self):
            self.saved = None

        def save_credentials(self, protocol, host, address, username, password):
            self.saved = (protocol, host, address, username, password)

    app = App.__new__(App)
    app.network = DummyNetwork()
    app.keyboard_context = "smb_pass"
    app.keyboard_host = {"protocol": "SMB", "host": "smb-host-b", "address": "smb-host-b"}
    app.keyboard_username = "alice"
    app.keyboard_value = "secret"
    seen: dict[str, object] = {}
    app._start_network_host_browse = lambda host, username, password: seen.setdefault(
        "browse", (host, username, password)
    )

    app._submit_keyboard_value()

    assert app.network.saved == ("SMB", "smb-host-b", "smb-host-b", "alice", "secret")
    assert seen["browse"][1] == "alice"
    assert seen["browse"][2] == "secret"


def test_x_on_network_folder_saves_favorite_and_shows_popup():
    class DummyNetwork:
        def __init__(self):
            self.saved_root = None

        def add_root(self, root):
            self.saved_root = root

    app = App.__new__(App)
    app.network = DummyNetwork()
    app.list_selected = 0
    app.message = None
    app.list_items = [
        ListItem(
            title="Series",
            subtitle="Folder",
            kind="network_entry",
            payload={
                "entry": {
                    "protocol": "SMB",
                    "title": "Series",
                    "subtitle": "Folder",
                    "root_name": "media",
                    "path": "/Series",
                    "is_dir": True,
                    "size": None,
                },
                "host": {
                    "protocol": "SMB",
                    "host": "smb-host-c",
                    "display_name": "NAS",
                    "address": "smb-host-c",
                    "username": "alice",
                    "password": "secret",
                },
            },
        )
    ]

    app._save_selected_network_favorite()

    assert app.message is not None
    assert app.message.body == "SAVED AS FAV."
    assert app.network.saved_root is not None
    assert app.network.saved_root.path == "/Series"


def test_finish_network_browse_entry_does_not_auto_save_favorite():
    class DummyNetwork:
        def __init__(self):
            self.add_calls = 0

        def add_root(self, _root):
            self.add_calls += 1

    app = App.__new__(App)
    app.network = DummyNetwork()
    app.busy_return_screen = Screen.LIST
    app.busy_return_section = "NETWORK"
    app._clear_busy = lambda: None
    app._log_list_selection = lambda: None
    app.set_screen = lambda screen, section: (setattr(app, "screen", screen), setattr(app, "section", section))
    app.message = None

    payload = {
        "kind": "entry",
        "entry": {"root_name": "media", "path": "/", "protocol": "SMB"},
        "host": {
            "protocol": "SMB",
            "host": "smb-host-d",
            "display_name": "NAS",
            "address": "smb-host-d",
            "username": "alice",
            "password": "secret",
        },
    }
    entries = [
        BrowseEntry(
            protocol="SMB",
            title="Series",
            subtitle="Folder",
            root_name="media",
            path="/Series",
            is_dir=True,
            size=None,
        )
    ]

    app._finish_network_browse(payload, entries, None)
    assert app.network.add_calls == 0
