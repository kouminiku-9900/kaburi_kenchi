from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

VIDEO_EXTS: frozenset[str] = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
    ".webm", ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts",
})

MIN_FILE_SIZE_BYTES = 1024


@dataclass
class VideoFile:
    path: Path
    subfolder: str
    size: int
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bit_rate: Optional[int] = None
    codec: Optional[str] = None
    probe_error: Optional[str] = field(default=None, repr=False)

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def ext(self) -> str:
        return self.path.suffix.lower()

    @property
    def resolution_label(self) -> str:
        if self.height is None:
            return "?"
        return f"{self.height}p"

    @property
    def has_meta(self) -> bool:
        return self.duration is not None and self.width is not None and self.height is not None


def enumerate_videos(parent: Path) -> list[VideoFile]:
    """Walk subfolders under `parent` and collect video files inside each.
    Also collects video files placed directly in `parent` (depth 0),
    assigning them a subfolder value of ".".
    """
    if not parent.is_dir():
        raise NotADirectoryError(parent)

    results: list[VideoFile] = []
    for sub in sorted(parent.iterdir()):
        if sub.is_dir():
            results.extend(_collect_in_subfolder(sub))
        elif sub.is_file():
            if sub.suffix.lower() in VIDEO_EXTS:
                try:
                    size = sub.stat().st_size
                    if size >= MIN_FILE_SIZE_BYTES:
                        results.append(VideoFile(path=sub, subfolder=".", size=size))
                except OSError:
                    pass
    return results


def _collect_in_subfolder(subfolder: Path) -> Iterable[VideoFile]:
    for path in subfolder.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VIDEO_EXTS:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size < MIN_FILE_SIZE_BYTES:
            continue
        yield VideoFile(path=path, subfolder=subfolder.name, size=size)


def is_inside(child: Path, parent: Path) -> bool:
    """True if `child` is the same as or under `parent`."""
    try:
        child_r = child.resolve()
        parent_r = parent.resolve()
    except OSError:
        return False
    if child_r == parent_r:
        return True
    return parent_r in child_r.parents
