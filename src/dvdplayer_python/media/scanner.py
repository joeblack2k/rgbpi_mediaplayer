from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List

from dvdplayer_python.core.models import DVD_SCAN_ROOTS, DvdCandidate, PlaybackKind, PlaybackSource


VIDEO_EXTS = {"mp4", "mkv", "avi", "mov", "m4v", "mpg", "mpeg", "vob"}


def scan_dvd_candidates() -> List[DvdCandidate]:
    candidates: List[DvdCandidate] = []

    dev = Path("/dev")
    if dev.is_dir():
        for node in sorted(dev.iterdir()):
            if node.name.startswith("sr") and _is_optical_playable(node):
                title = _optical_label(node)
                candidates.append(
                    DvdCandidate(
                        title=title,
                        subtitle=str(node),
                        source=PlaybackSource(
                            title=title,
                            kind=PlaybackKind.OPTICAL_DRIVE,
                            uri=str(node),
                            subtitle=str(node),
                            authored_dvd=True,
                            container="dvd",
                        ),
                    )
                )

    for root in DVD_SCAN_ROOTS:
        root_path = Path(root)
        if root_path.is_dir():
            _collect(root_path, candidates, depth=0)

    return candidates


def _collect(path: Path, out: List[DvdCandidate], depth: int) -> None:
    if depth > 3:
        return
    for entry in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            if entry.name.upper() == "VIDEO_TS" or (entry / "VIDEO_TS").is_dir():
                out.append(
                    DvdCandidate(
                        title=entry.name,
                        subtitle=str(entry),
                        source=PlaybackSource(
                            title=entry.name,
                            kind=PlaybackKind.DVD_FOLDER,
                            uri=str(entry),
                            subtitle=str(entry),
                            authored_dvd=True,
                            file_size=None,
                            container="dvd",
                        ),
                    )
                )
            else:
                _collect(entry, out, depth + 1)
        elif entry.suffix.lower() == ".iso":
            out.append(
                DvdCandidate(
                    title=entry.name,
                    subtitle=str(entry),
                    source=PlaybackSource(
                        title=entry.name,
                        kind=PlaybackKind.DVD_ISO,
                        uri=str(entry),
                        subtitle=str(entry),
                        authored_dvd=True,
                        file_size=entry.stat().st_size if entry.exists() else None,
                        container="iso",
                    ),
                )
            )


def scan_local_items(path: Path):
    items = []
    if path.parent:
        items.append({"title": "..", "subtitle": "Back", "kind": "parent", "path": str(path.parent)})

    for entry in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            if entry.name.upper() == "VIDEO_TS" or (entry / "VIDEO_TS").is_dir():
                items.append({"title": entry.name, "subtitle": "DVD folder", "kind": "dvd_folder", "path": str(entry)})
            else:
                items.append({"title": entry.name, "subtitle": "Folder", "kind": "dir", "path": str(entry)})
        else:
            ext = entry.suffix.lower().lstrip(".")
            if ext in VIDEO_EXTS:
                items.append({"title": entry.name, "subtitle": ext, "kind": "video", "path": str(entry)})
            elif ext == "iso":
                items.append({"title": entry.name, "subtitle": "dvd image", "kind": "iso", "path": str(entry)})

    if len(items) == 1 and items[0]["kind"] == "parent":
        items.append({"title": "(empty)", "subtitle": str(path), "kind": "noop", "path": str(path)})
    return items


def _is_optical_playable(path: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["udevadm", "info", "--query=property", f"--name={path}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return False
    return (
        "ID_CDROM_MEDIA=1" in out
        and ("ID_CDROM_MEDIA_DVD=1" in out or "ID_FS_TYPE=udf" in out or "ID_FS_TYPE=iso9660" in out)
    )


def _optical_label(path: Path) -> str:
    try:
        out = subprocess.check_output(
            ["udevadm", "info", "--query=property", f"--name={path}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for line in out.splitlines():
            if line.startswith("ID_FS_LABEL="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    except Exception:
        pass
    return str(path)
