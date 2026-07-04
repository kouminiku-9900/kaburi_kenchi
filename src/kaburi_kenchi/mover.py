from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

UNDO_LOG_NAME = "_kaburi_kenchi_undo.json"


@dataclass
class MoveResult:
    src: Path
    dst: Path
    bytes_moved: int


@dataclass
class MoveError:
    src: Path
    error: str


def _safe_destination(dest_dir: Path, src: Path, src_subfolder: str) -> Path:
    """Pick a unique destination path inside `dest_dir`.

    First tries `<src.name>`. On collision, prefixes with `<src_subfolder>__`.
    Further collisions append `(2)`, `(3)`, ... before the extension.
    """
    candidate = dest_dir / src.name
    if not candidate.exists():
        return candidate

    candidate = dest_dir / f"{src_subfolder}__{src.name}"
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    i = 2
    while True:
        candidate = dest_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def move_files(
    plan: list[tuple[Path, str]],
    dest_dir: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[MoveResult], list[MoveError]]:
    """Execute a list of (source_path, source_subfolder) moves into dest_dir.

    Returns (successes, failures). On any per-file failure, the rest still proceed.
    Successes are appended to an undo log JSON inside dest_dir.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    successes: list[MoveResult] = []
    failures: list[MoveError] = []

    total = len(plan)
    if progress_cb:
        progress_cb(0, total)

    for i, (src, sub) in enumerate(plan, start=1):
        try:
            if not src.exists():
                failures.append(MoveError(src=src, error="source no longer exists"))
                continue
            size = src.stat().st_size
            dst = _safe_destination(dest_dir, src, sub)
            shutil.move(str(src), str(dst))
            successes.append(MoveResult(src=src, dst=dst, bytes_moved=size))
        except Exception as e:  # noqa: BLE001
            failures.append(MoveError(src=src, error=str(e)))
        finally:
            if progress_cb:
                progress_cb(i, total)

    if successes:
        _append_undo_log(dest_dir, successes)
    return successes, failures


def _append_undo_log(dest_dir: Path, successes: list[MoveResult]) -> None:
    log_path = dest_dir / UNDO_LOG_NAME
    existing: list[dict] = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError):
            existing = []

    now = datetime.now().isoformat(timespec="seconds")
    for r in successes:
        existing.append({
            "moved_at": now,
            "original_path": str(r.src),
            "moved_to": str(r.dst),
            "bytes": r.bytes_moved,
        })

    try:
        log_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
