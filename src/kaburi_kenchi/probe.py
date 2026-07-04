from __future__ import annotations

import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from kaburi_kenchi.scanner import VideoFile

FFPROBE_TIMEOUT_SEC = 30
DEFAULT_WORKERS = 4

# CREATE_NO_WINDOW for Windows so the console doesn't flash with each subprocess.
try:
    from subprocess import CREATE_NO_WINDOW  # type: ignore[attr-defined]
    _SUBPROCESS_FLAGS = CREATE_NO_WINDOW
except ImportError:
    _SUBPROCESS_FLAGS = 0


def find_ffprobe() -> Optional[str]:
    """Locate ffprobe.exe.

    Search order:
      1. PATH (via shutil.which)
      2. winget install location: %LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_*\\...\\bin\\ffprobe.exe
         — winget adds an alias on a fresh install but PATH is only refreshed in
         new shells, so we fall back to direct lookup so the GUI works without
         requiring a shell restart.
    """
    p = shutil.which("ffprobe")
    if p:
        return p

    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    pkg_root = Path(local) / "Microsoft" / "WinGet" / "Packages"
    if not pkg_root.is_dir():
        return None
    for candidate in pkg_root.glob("Gyan.FFmpeg_*/**/bin/ffprobe.exe"):
        if candidate.is_file():
            return str(candidate)
    return None


def probe_one(video: VideoFile, ffprobe_path: str) -> VideoFile:
    """Populate metadata fields on `video` in-place and return it."""
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video.path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_SEC,
            creationflags=_SUBPROCESS_FLAGS,
        )
    except subprocess.TimeoutExpired:
        video.probe_error = "timeout"
        return video
    except OSError as e:
        video.probe_error = f"oserror: {e}"
        return video

    if proc.returncode != 0:
        video.probe_error = (proc.stderr or "ffprobe failed").strip()[:200]
        return video

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        video.probe_error = "invalid ffprobe json"
        return video

    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)

    duration_str = fmt.get("duration")
    if duration_str is not None:
        try:
            video.duration = float(duration_str)
        except ValueError:
            pass

    bitrate_str = fmt.get("bit_rate")
    if bitrate_str is not None:
        try:
            video.bit_rate = int(bitrate_str)
        except ValueError:
            pass

    if video_stream is not None:
        w = video_stream.get("width")
        h = video_stream.get("height")
        if isinstance(w, int):
            video.width = w
        if isinstance(h, int):
            video.height = h
        codec = video_stream.get("codec_name")
        if isinstance(codec, str):
            video.codec = codec

    if not video.has_meta and video.probe_error is None:
        video.probe_error = "missing fields"

    return video


def probe_all(
    videos: list[VideoFile],
    ffprobe_path: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_cb: Optional[Callable[[], bool]] = None,
    workers: int = DEFAULT_WORKERS,
) -> list[VideoFile]:
    """Probe metadata for every video. Reports progress and supports cancellation."""
    total = len(videos)
    if progress_cb:
        progress_cb(0, total)
    if total == 0:
        return videos

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe_one, v, ffprobe_path): v for v in videos}
        for fut in as_completed(futures):
            if cancel_cb and cancel_cb():
                for f in futures:
                    f.cancel()
                break
            try:
                fut.result()
            except Exception as e:  # noqa: BLE001
                v = futures[fut]
                v.probe_error = f"unexpected: {e}"
            completed += 1
            if progress_cb:
                progress_cb(completed, total)
    return videos
