from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from dvdplayer_python.ui.renderer import RenderModel, Renderer


def test_fit_text_adds_ellipsis_for_long_strings():
    renderer = Renderer()

    fitted = renderer._fit_text(renderer.font_s, "SMOOTH TV for video files", 60)

    assert fitted.endswith("...")
    assert renderer.font_s.size(fitted)[0] <= 60


def test_draw_model_handles_long_settings_subtitle_without_overflow():
    renderer = Renderer()
    model = RenderModel(
        title="DVD MEDIAPLAYER",
        section="SETTINGS",
        footer="A/START OPEN   B BACK   START+SELECT EXIT",
        rows=[("CRT MOTION", "SMOOTH TV for video files", True)],
        selected=0,
    )

    renderer.draw_model(model)

    assert renderer.screen.get_width() == 320
    assert renderer.screen.get_height() == 240
