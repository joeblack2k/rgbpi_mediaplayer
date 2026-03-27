from dvdplayer_python.media.network_backend import make_saved_root


def test_make_saved_root_normalizes_path():
    root = make_saved_root(
        protocol="SMB",
        display_name="X",
        host="h",
        address="h",
        root_name="share",
        path="media/videos",
        username=None,
        password=None,
    )
    assert root.path == "/media/videos"
    assert root.id.startswith("SMB:h:share:/media/videos:")
