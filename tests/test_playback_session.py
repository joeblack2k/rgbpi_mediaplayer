from __future__ import annotations

import json

from dvdplayer_python.core.models import PlaybackKind, PlaybackPrefs, PlaybackSource
from dvdplayer_python.playback import session


def test_pal_rate_video_resolves_to_576i(monkeypatch):
    source = PlaybackSource(title="PAL", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/pal.mkv")
    monkeypatch.setattr(
        session,
        "_probe_video_info",
        lambda _uri: session.VideoProbeInfo(width=720, height=576, fps=25.0, field_order="progressive"),
    )

    assert session._target_mode_for_source(source) == "720x576i"


def test_ntsc_rate_video_resolves_to_480i(monkeypatch):
    source = PlaybackSource(title="NTSC", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/ntsc.mkv")
    monkeypatch.setattr(
        session,
        "_probe_video_info",
        lambda _uri: session.VideoProbeInfo(width=720, height=480, fps=29.97, field_order="progressive"),
    )

    assert session._target_mode_for_source(source) == "720x480i"


def test_low_res_video_does_not_force_interlaced_mode(monkeypatch):
    source = PlaybackSource(title="Low", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/low.mp4")
    monkeypatch.setattr(
        session,
        "_probe_video_info",
        lambda _uri: session.VideoProbeInfo(width=320, height=240, fps=60.0, field_order="progressive"),
    )

    assert session._target_mode_for_source(source) is None


def test_authored_dvd_ignores_smooth_motion_preference(monkeypatch):
    monkeypatch.delenv("DVDPLAYER_CRT_MOTION_MODE", raising=False)
    prefs = PlaybackPrefs(motion_mode="smooth_tv")
    source = PlaybackSource(title="DVD", kind=PlaybackKind.DVD_FOLDER, uri="/tmp/VIDEO_TS", authored_dvd=True)

    profile = session.playback_profile_for_source(source, prefs)

    assert profile.motion_mode == "authentic"
    assert profile.video_sync == "audio"
    assert profile.interpolation == "no"


def test_smooth_tv_profile_uses_display_resample(monkeypatch):
    monkeypatch.delenv("DVDPLAYER_CRT_MOTION_MODE", raising=False)
    prefs = PlaybackPrefs(motion_mode="smooth_tv")
    source = PlaybackSource(title="Episode", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/episode.mkv")

    profile = session.playback_profile_for_source(source, prefs)

    assert profile.motion_mode == "smooth_tv"
    assert profile.video_sync == "display-resample"
    assert profile.interpolation == "yes"


def test_cable_smooth_profile_uses_display_resample(monkeypatch):
    monkeypatch.delenv("DVDPLAYER_CRT_MOTION_MODE", raising=False)
    prefs = PlaybackPrefs(motion_mode="cable_smooth")
    source = PlaybackSource(title="Episode", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/episode.mkv")

    profile = session.playback_profile_for_source(source, prefs)

    assert profile.motion_mode == "cable_smooth"
    assert profile.video_sync == "display-resample"
    assert profile.interpolation == "yes"


def test_smooth_fps_filter_enabled_for_smooth_modes():
    source = PlaybackSource(title="Episode", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/episode.mkv")

    smooth = session.smooth_fps_filter_for_source(source, PlaybackPrefs(motion_mode="smooth_tv"))
    cable = session.smooth_fps_filter_for_source(source, PlaybackPrefs(motion_mode="cable_smooth"))
    authentic = session.smooth_fps_filter_for_source(source, PlaybackPrefs(motion_mode="authentic"))

    assert smooth == session.SMOOTH_FPS_FILTER
    assert cable == session.SMOOTH_FPS_FILTER
    assert authentic is None


def test_smooth_fps_filter_disabled_for_authored_dvd():
    source = PlaybackSource(title="Disc", kind=PlaybackKind.DVD_FOLDER, uri="/tmp/VIDEO_TS", authored_dvd=True)
    prefs = PlaybackPrefs(motion_mode="cable_smooth")

    assert session.smooth_fps_filter_for_source(source, prefs) is None


def test_env_override_beats_saved_preference(monkeypatch):
    monkeypatch.setenv("DVDPLAYER_CRT_MOTION_MODE", "authentic")
    prefs = PlaybackPrefs(motion_mode="smooth_tv")

    assert session.resolve_motion_mode(prefs) == "authentic"


def test_motion_mode_alias_cable_is_normalized(monkeypatch):
    monkeypatch.setenv("DVDPLAYER_CRT_MOTION_MODE", "cable")
    prefs = PlaybackPrefs(motion_mode="smooth_tv")

    assert session.resolve_motion_mode(prefs) == "cable_smooth"


def test_output_mode_mismatch_marks_session_degraded(monkeypatch):
    drm_target = session.DrmLaunchTarget(card="card1", connector="VGA-1", mode_name="720x480i")
    monkeypatch.setattr(session, "_read_drm_mode", lambda connector=None: "320x240")

    effective_mode, degraded = session.PlaybackSession._assess_output_mode("720x480i", drm_target)

    assert effective_mode == "320x240"
    assert degraded is True


def test_force_43_applies_to_video_files_only():
    prefs = PlaybackPrefs(force_43=True)
    video = PlaybackSource(title="Episode", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/ep.mkv")
    dvd = PlaybackSource(title="Disc", kind=PlaybackKind.DVD_FOLDER, uri="/tmp/VIDEO_TS", authored_dvd=True)

    assert session.force_43_for_source(video, prefs) is True
    assert session.force_43_for_source(dvd, prefs) is False


def test_audio_normalization_high_falls_back_to_light(monkeypatch):
    prefs = PlaybackPrefs(volume_normalization="high")
    source = PlaybackSource(title="Episode", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/ep.mkv")
    monkeypatch.setattr(session, "_ffmpeg_supports_filter", lambda _name: False)

    mode, audio_filter = session.audio_normalization_profile_for_source(source, prefs)

    assert mode == "light"
    assert audio_filter == session.LIGHT_NORMALIZATION_FILTER


def test_authored_dvd_ignores_volume_normalization_setting():
    prefs = PlaybackPrefs(volume_normalization="high")
    source = PlaybackSource(title="Disc", kind=PlaybackKind.DVD_FOLDER, uri="/tmp/VIDEO_TS", authored_dvd=True)

    mode, audio_filter = session.audio_normalization_profile_for_source(source, prefs)

    assert mode == "off"
    assert audio_filter is None


def test_deinterlace_profile_defaults_to_weave():
    source = PlaybackSource(title="Episode", kind=PlaybackKind.VIDEO_FILE, uri="/tmp/ep.mkv")
    prefs = PlaybackPrefs(deinterlace_mode="weave")

    mode, vf = session.deinterlace_profile_for_source(source, prefs)

    assert mode == "weave"
    assert vf is None


def test_deinterlace_profile_bob_mode_uses_bwdif():
    source = PlaybackSource(title="Episode", kind=PlaybackKind.PLEX_VIDEO, uri="http://plex/ep.mkv")
    prefs = PlaybackPrefs(deinterlace_mode="bob")

    mode, vf = session.deinterlace_profile_for_source(source, prefs)

    assert mode == "bob"
    assert vf == session.BOB_DEINTERLACE_FILTER


def test_send_ignores_unsolicited_mpv_events(monkeypatch, tmp_path):
    responses = [
        json.dumps({"event": "property-change", "name": "pause"}) + "\n",
        json.dumps({"request_id": 1, "error": "success", "data": 12.5}) + "\n",
    ]

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def settimeout(self, _timeout):
            return None

        def connect(self, _path):
            return None

        def sendall(self, _payload):
            return None

        def recv(self, _size):
            if responses:
                return responses.pop(0).encode("utf-8")
            return b""

    monkeypatch.setattr(session.socket, "socket", lambda *_args, **_kwargs: FakeSocket())
    playback = session.PlaybackSession(
        child=None,  # type: ignore[arg-type]
        ipc_path=tmp_path / "ipc.sock",
        target_mode=None,
        drm_target=None,
        backend="mpv",
    )

    response = playback._send({"command": ["get_property", "time-pos"]})

    assert response["data"] == 12.5
