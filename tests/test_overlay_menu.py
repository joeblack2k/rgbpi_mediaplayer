from __future__ import annotations

import sys
import types
from pathlib import Path

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

from dvdplayer_python.core.models import PlaybackKind, PlaybackPrefs, PlaybackSource
import dvdplayer_python.main as app_main


def test_start_menu_entries_for_non_dvd_video_has_two_items():
    source = PlaybackSource(title="Braceface", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/braceface.mp4", authored_dvd=False)
    entries = app_main.start_menu_entries_for_source(source)
    assert entries == [
        (app_main.OVERLAY_ACTION_TOGGLE_PAUSE, "TOGGLE PAUSE"),
        (app_main.OVERLAY_ACTION_RETURN_TO_BROWSER, "RETURN TO BROWSER"),
    ]


def test_start_menu_entries_for_authored_dvd_has_subtitle_item():
    source = PlaybackSource(title="Disc", kind=PlaybackKind.DVD_FOLDER, uri="/tmp/VIDEO_TS", authored_dvd=True)
    entries = app_main.start_menu_entries_for_source(source)
    assert entries == [
        (app_main.OVERLAY_ACTION_TOGGLE_PAUSE, "TOGGLE PAUSE"),
        (app_main.OVERLAY_ACTION_DVD_MENU, "DVD MENU"),
        (app_main.OVERLAY_ACTION_CHAPTER_PREV, "CHAPTER -"),
        (app_main.OVERLAY_ACTION_CHAPTER_NEXT, "CHAPTER +"),
        (app_main.OVERLAY_ACTION_SUBTITLES, "ENABLE SUBTITLES"),
        (app_main.OVERLAY_ACTION_RETURN_TO_BROWSER, "RETURN TO BROWSER"),
    ]


def test_start_menu_entries_for_plex_has_subtitle_option():
    source = PlaybackSource(title="Episode", kind=PlaybackKind.PLEX_VIDEO, uri="http://plex/media.mp4", authored_dvd=False)
    entries = app_main.start_menu_entries_for_source(source)
    assert entries == [
        (app_main.OVERLAY_ACTION_TOGGLE_PAUSE, "TOGGLE PAUSE"),
        (app_main.OVERLAY_ACTION_SUBTITLES, "ENABLE SUBTITLES"),
        (app_main.OVERLAY_ACTION_RETURN_TO_BROWSER, "RETURN TO BROWSER"),
    ]


def test_overlay_action_exception_is_caught_and_logged(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(app_main, "log_event", lambda event, **kwargs: events.append((event, kwargs)))

    class BadPlayback:
        def step_chapter(self, _delta: int):
            raise RuntimeError("property unavailable")

    app = app_main.App.__new__(app_main.App)
    app.playback = BadPlayback()
    app.playback_source = PlaybackSource(title="Disc", kind=PlaybackKind.DVD_FOLDER, uri="/tmp/VIDEO_TS", authored_dvd=True)
    app.stop_playback = lambda _status: None

    ok = app._execute_overlay_action(app_main.OVERLAY_ACTION_CHAPTER_NEXT)
    assert ok is False
    assert any(event == "overlay_action_failed" and payload.get("action_id") == app_main.OVERLAY_ACTION_CHAPTER_NEXT for event, payload in events)


def test_run_loop_exception_triggers_force_cleanup_and_shutdown(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(app_main, "log_event", lambda event, **kwargs: events.append((event, kwargs)))

    class _FakeClock:
        def tick(self, _fps: int):
            return None

    monkeypatch.setattr(app_main.pygame.time, "Clock", lambda: _FakeClock())

    app = app_main.App.__new__(app_main.App)
    app.running = True
    app._pump_control = lambda: None
    app._pump_pygame = lambda: None
    app._draw = lambda: None
    app._write_runtime_state = lambda: None
    app._flush_screenshots = lambda: None
    app._tick = lambda: (_ for _ in ()).throw(RuntimeError("boom"))

    cleanup = {"called": False}
    shutdown = {"called": False}

    app._force_playback_cleanup = lambda _reason: cleanup.__setitem__("called", True)
    app.shutdown = lambda: shutdown.__setitem__("called", True)

    app.run()

    assert cleanup["called"] is True
    assert shutdown["called"] is True
    assert any(event == "app_runtime_exception" for event, _payload in events)


def test_start_playback_replaces_existing_session(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(app_main, "log_event", lambda event, **kwargs: events.append((event, kwargs)))

    class DummyStore:
        def __init__(self):
            self.prefs = PlaybackPrefs()

        def bookmark(self, _key: str):
            return None

    class NewSession:
        def set_volume(self, _volume: int):
            return None

    old_source = PlaybackSource(
        title="Old Episode",
        kind=PlaybackKind.VIDEO_FILE,
        uri="/tmp/old.mp4",
        authored_dvd=False,
    )
    new_source = PlaybackSource(
        title="New Episode",
        kind=PlaybackKind.VIDEO_FILE,
        uri="/tmp/new.mp4",
        authored_dvd=False,
    )

    app = app_main.App.__new__(app_main.App)
    app.playback_state = DummyStore()
    app.playback = object()
    app.playback_source = old_source
    app.screen = app_main.Screen.HOME
    app.section = "HOME"
    app.list_items = []
    app.list_selected = 0
    app.return_list_items = []
    app.return_list_selected = 0
    app.return_screen_after_playback = app_main.Screen.HOME
    app.return_section_after_playback = "HOME"
    app.app_dir = Path("/tmp")
    app._reset_playback_overlay_state = lambda: None
    app.set_screen = lambda screen, section: (setattr(app, "screen", screen), setattr(app, "section", section))

    cleanup_called = {"called": False}

    def _cleanup(_reason: str):
        cleanup_called["called"] = True
        app.playback = None
        app.playback_source = None

    app._force_playback_cleanup = _cleanup
    monkeypatch.setattr(app_main.PlaybackSession, "start", lambda *_args, **_kwargs: NewSession())

    app.start_playback(new_source, resume_prompt=False)

    assert cleanup_called["called"] is True
    assert app.playback is not None
    assert app.playback_source == new_source
    assert any(event == "playback_replace" for event, _payload in events)
