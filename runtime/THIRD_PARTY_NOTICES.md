# Third-Party Runtime Notices

This folder contains bundled Linux ARM runtime binaries and shared libraries used by the app in standalone mode.

Included components:
- `bin/mpv` and runtime-linked shared libraries in `runtime/linux-arm64-rootfs/`
- `libdvdcss` shared library in `runtime/linux-arm64-rootfs/usr/lib/aarch64-linux-gnu/`

Primary upstream projects:
- mpv: https://mpv.io/
- FFmpeg (used by mpv package builds): https://ffmpeg.org/
- libdvdcss: https://www.videolan.org/developers/libdvdcss.html

License notes:
- mpv is distributed under GPL/LGPL terms depending on build and linked components.
- libdvdcss is distributed by VideoLAN under GPL-compatible terms.
- FFmpeg libraries are distributed under LGPL/GPL depending on enabled codecs and build flags.

For full compliance in downstream redistributions, include the exact source and license texts matching the binaries shipped in this folder.
