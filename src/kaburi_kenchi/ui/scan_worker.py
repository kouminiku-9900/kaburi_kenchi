from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from kaburi_kenchi.duplicate_finder import DuplicateGroup, find_duplicates
from kaburi_kenchi.probe import probe_all
from kaburi_kenchi.scanner import VideoFile, enumerate_videos


class ScanWorker(QObject):
    progress = Signal(str, int, int)         # phase label, done, total
    finished = Signal(list, list, list)       # groups, all_videos, unprobed
    failed = Signal(str)

    def __init__(self, parent_folder: Path, ffprobe_path: str) -> None:
        super().__init__()
        self._parent = parent_folder
        self._ffprobe = ffprobe_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            self.progress.emit("Enumerating files...", 0, 0)
            videos: list[VideoFile] = enumerate_videos(self._parent)
            if self._cancelled:
                self.failed.emit("Cancelled")
                return

            def on_probe_progress(done: int, total: int) -> None:
                self.progress.emit("Probing video metadata...", done, total)

            probe_all(
                videos,
                self._ffprobe,
                progress_cb=on_probe_progress,
                cancel_cb=self._is_cancelled,
            )
            if self._cancelled:
                self.failed.emit("Cancelled")
                return

            self.progress.emit("Finding duplicates...", 0, 0)
            groups: list[DuplicateGroup] = find_duplicates(videos)
            unprobed = [v for v in videos if not v.has_meta]
            self.finished.emit(groups, videos, unprobed)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")


def run_scan_in_thread(
    parent_folder: Path,
    ffprobe_path: str,
) -> tuple[QThread, ScanWorker]:
    """Helper to start a ScanWorker on its own QThread. Caller wires signals."""
    thread = QThread()
    worker = ScanWorker(parent_folder, ffprobe_path)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    return thread, worker
