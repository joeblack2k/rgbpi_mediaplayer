from __future__ import annotations

from pathlib import Path

from dvdplayer_python.core.models import PlaybackKind, PlaybackSource
from dvdplayer_python.core.persistence import PlaybackStateStore


def test_bookmark_roundtrip(tmp_path: Path):
    store = PlaybackStateStore(tmp_path)
    key = "video:/tmp/a.mp4"
    store.save_bookmark(key, "A", "/tmp/a.mp4", 120.0, 360.0, 123456)

    loaded = PlaybackStateStore(tmp_path)
    bookmark = loaded.bookmark(key)
    assert bookmark is not None
    assert bookmark.position_seconds == 120.0
    assert bookmark.duration_seconds == 360.0


def test_prefs_roundtrip(tmp_path: Path):
    store = PlaybackStateStore(tmp_path)
    store.prefs.volume = 55.0
    store.prefs.motion_mode = "authentic"
    store.prefs.force_43 = True
    store.prefs.volume_normalization = "high"
    store.prefs.deinterlace_mode = "bob"
    store.write_prefs()

    loaded = PlaybackStateStore(tmp_path)
    assert loaded.prefs.volume == 55.0
    assert loaded.prefs.motion_mode == "authentic"
    assert loaded.prefs.force_43 is True
    assert loaded.prefs.volume_normalization == "high"
    assert loaded.prefs.deinterlace_mode == "bob"


def test_missing_prefs_defaults_to_smooth_tv(tmp_path: Path):
    loaded = PlaybackStateStore(tmp_path)
    assert loaded.prefs.motion_mode == "smooth_tv"


def test_invalid_motion_mode_falls_back_to_smooth_tv(tmp_path: Path):
    (tmp_path / "playback_prefs.json").write_text('{"motion_mode":"weird"}', encoding="utf-8")

    loaded = PlaybackStateStore(tmp_path)

    assert loaded.prefs.motion_mode == "smooth_tv"


def test_cable_motion_mode_alias_is_normalized(tmp_path: Path):
    (tmp_path / "playback_prefs.json").write_text('{"motion_mode":"cable"}', encoding="utf-8")

    loaded = PlaybackStateStore(tmp_path)

    assert loaded.prefs.motion_mode == "cable_smooth"


def test_missing_prefs_defaults_to_light_volume_normalization(tmp_path: Path):
    loaded = PlaybackStateStore(tmp_path)
    assert loaded.prefs.volume_normalization == "light"


def test_invalid_volume_normalization_falls_back_to_light(tmp_path: Path):
    (tmp_path / "playback_prefs.json").write_text('{"volume_normalization":"invalid"}', encoding="utf-8")

    loaded = PlaybackStateStore(tmp_path)

    assert loaded.prefs.volume_normalization == "light"


def test_invalid_deinterlace_mode_falls_back_to_weave(tmp_path: Path):
    (tmp_path / "playback_prefs.json").write_text('{"deinterlace_mode":"invalid"}', encoding="utf-8")

    loaded = PlaybackStateStore(tmp_path)

    assert loaded.prefs.deinterlace_mode == "weave"


def test_last_played_roundtrip(tmp_path: Path):
    store = PlaybackStateStore(tmp_path)
    source = PlaybackSource(
        title="Turtles",
        kind=PlaybackKind.VIDEO_FILE,
        uri="/media/nas/turtles.mkv",
        subtitle="Turtles",
        authored_dvd=False,
    )
    store.save_last_played(source, 312.0, 1500.0, 999)

    loaded = PlaybackStateStore(tmp_path)

    assert loaded.last_played is not None
    assert loaded.last_played.source.uri == "/media/nas/turtles.mkv"
    assert loaded.last_played.position_seconds == 312.0
