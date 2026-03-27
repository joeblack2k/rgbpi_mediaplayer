from __future__ import annotations

import sys
import types

try:
    import pygame  # type: ignore  # noqa: F401
except ModuleNotFoundError:
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
        time=types.SimpleNamespace(Clock=lambda: None),
    )

from dvdplayer_python.core.models import (
    Action,
    BookmarkState,
    LastPlayedState,
    PlaybackKind,
    PlaybackPrefs,
    PlaybackSource,
    Screen,
)
from dvdplayer_python.main import App


def test_start_playback_with_bookmark_opens_resume_popup():
    source = PlaybackSource(title="Batman", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/batman.mkv", authored_dvd=False)
    bookmark = BookmarkState(
        title="Batman",
        uri="/tmp/batman.mkv",
        position_seconds=180.0,
        duration_seconds=1200.0,
        updated_at_unix_ms=1,
    )

    class DummyStore:
        def __init__(self):
            self.prefs = PlaybackPrefs()

        def bookmark(self, key: str):
            assert key == "video:/tmp/batman.mkv"
            return bookmark

    app = App.__new__(App)
    app.playback_state = DummyStore()
    app.screen = Screen.LIST
    app.section = "LOCAL"
    app.set_screen = lambda screen, section: (setattr(app, "screen", screen), setattr(app, "section", section))
    app.confirm_context = None
    app.confirm_options = []
    app.confirm_payload = {}
    app.confirm_selected = 0

    app.start_playback(source)

    assert app.confirm_context == "resume_playback"
    assert app.confirm_options == ["RESUME PLAYBACK", "START FROM BEGINNING"]


def test_home_row_shows_resume_playback_when_last_played_exists():
    source = PlaybackSource(title="Turtles", kind=PlaybackKind.PLEX_VIDEO, uri="http://plex/turtles.mp4", authored_dvd=False)

    class DummyStore:
        def __init__(self):
            self.prefs = PlaybackPrefs()
            self.last_played = LastPlayedState(
                source=source,
                position_seconds=145.0,
                duration_seconds=1200.0,
                updated_at_unix_ms=123,
            )

    app = App.__new__(App)
    app.playback_state = DummyStore()
    app.dvd_candidates = []
    app.plex = types.SimpleNamespace(has_token=lambda: True)

    title, subtitle, active = app._home_row(4)
    settings_kinds = [item.kind for item in app._settings_items()]

    assert title == "RESUME PLAYBACK"
    assert "Turtles" in subtitle
    assert active is True
    assert "settings_resume_playback" not in settings_kinds


def test_home_row_resume_playback_is_inactive_when_missing():
    class DummyStore:
        def __init__(self):
            self.prefs = PlaybackPrefs()
            self.last_played = None

    app = App.__new__(App)
    app.playback_state = DummyStore()
    app.dvd_candidates = []
    app.plex = types.SimpleNamespace(has_token=lambda: True)

    kinds = [item.kind for item in app._settings_items()]
    title, subtitle, active = app._home_row(4)

    assert title == "RESUME PLAYBACK"
    assert subtitle == "No resumable playback"
    assert active is False
    assert "settings_resume_playback" not in kinds
    assert "settings_cable_smooth_preset" in kinds
    assert "settings_deinterlace" not in kinds


def test_settings_left_right_changes_switchable_setting_without_accept():
    class DummyStore:
        def __init__(self):
            self.prefs = PlaybackPrefs(force_43=False, volume_normalization="light", motion_mode="smooth_tv")

        def write_prefs(self):
            return None

    app = App.__new__(App)
    app.playback_state = DummyStore()
    app.list_items = app._settings_items()
    app.list_selected = 3  # FORCE 4:3
    app.section = "SETTINGS"
    app.status_line = ""
    app.message = None
    app._save_selected_network_favorite = lambda: None
    app.go_home = lambda: None
    app._log_list_selection = lambda: None
    app.activate_list_item = lambda _item: (_ for _ in ()).throw(AssertionError("accept should not be called"))

    app.handle_list_action(Action.RIGHT)
    assert app.playback_state.prefs.force_43 is True
    app.handle_list_action(Action.LEFT)
    assert app.playback_state.prefs.force_43 is False

    app.handle_list_action(Action.ACCEPT)
    assert app.playback_state.prefs.force_43 is False
    assert app.status_line == "Use LEFT/RIGHT to change"
