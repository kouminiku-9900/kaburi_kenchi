from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSettings, QThread
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kaburi_kenchi.duplicate_finder import DuplicateGroup
from kaburi_kenchi.mover import move_files
from kaburi_kenchi.quality import Action, FileDecision, decide_all, estimated_savings_bytes
from kaburi_kenchi.scanner import VideoFile, is_inside
from kaburi_kenchi.ui.scan_worker import ScanWorker


COL_NAME = 0
COL_SUBFOLDER = 1
COL_RESOLUTION = 2
COL_DURATION = 3
COL_BITRATE = 4
COL_SIZE = 5
COL_ACTION = 6
COL_COUNT = 7

ROLE_FILE = Qt.UserRole + 1
ROLE_GROUP_INDEX = Qt.UserRole + 2

KEEP_LABEL = "KEEP"
MOVE_LABEL = "MOVE"

KEEP_BG = QColor(220, 245, 220)
MOVE_BG = QColor(255, 235, 210)
AMBIGUOUS_BG = QColor(255, 245, 200)


def fmt_size(n: int) -> str:
    if n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    i = 0
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.2f} {units[i]}" if i > 0 else f"{int(f)} {units[i]}"


def fmt_duration(secs: Optional[float]) -> str:
    if secs is None:
        return "?"
    s = int(round(secs))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_bitrate(br: Optional[int]) -> str:
    if not br:
        return "?"
    return f"{br // 1000} kbps"


class MainWindow(QMainWindow):
    def __init__(self, ffprobe_path: str) -> None:
        super().__init__()
        self._ffprobe_path = ffprobe_path
        self._settings = QSettings("kaburi_kenchi", "kaburi_kenchi")
        self._thread: Optional[QThread] = None
        self._worker: Optional[ScanWorker] = None
        self._groups: list[DuplicateGroup] = []
        self._decisions: dict[int, list[FileDecision]] = {}

        self.setWindowTitle("kaburi_kenchi - 動画かぶり検知")
        self.resize(1100, 700)
        self._build_ui()
        self._restore_paths()

    # ---- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Folder selectors
        form = QVBoxLayout()
        form.addLayout(self._build_path_row("親フォルダ:", "parent"))
        form.addLayout(self._build_path_row("退避先:", "dest"))
        root.addLayout(form)

        # Scan button + progress
        ctl = QHBoxLayout()
        self.scan_btn = QPushButton("スキャン開始")
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        ctl.addWidget(self.scan_btn)

        self.cancel_btn = QPushButton("中止")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        ctl.addWidget(self.cancel_btn)

        self.progress_label = QLabel("")
        self.progress_label.setMinimumWidth(220)
        ctl.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumWidth(280)
        ctl.addWidget(self.progress_bar, stretch=1)
        root.addLayout(ctl)

        # Summary
        self.summary_label = QLabel("スキャン未実行")
        f = QFont()
        f.setBold(True)
        self.summary_label.setFont(f)
        root.addWidget(self.summary_label)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setColumnCount(COL_COUNT)
        self.tree.setHeaderLabels([
            "ファイル / グループ", "サブフォルダ", "解像度",
            "再生時間", "ビットレート", "サイズ", "アクション",
        ])
        header = self.tree.header()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for c in (COL_SUBFOLDER, COL_RESOLUTION, COL_DURATION, COL_BITRATE, COL_SIZE, COL_ACTION):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.tree, stretch=1)

        # Bottom buttons
        bottom = QHBoxLayout()
        self.expand_btn = QPushButton("全展開")
        self.expand_btn.clicked.connect(lambda: self.tree.expandAll())
        bottom.addWidget(self.expand_btn)

        self.collapse_btn = QPushButton("全折りたたみ")
        self.collapse_btn.clicked.connect(lambda: self.tree.collapseAll())
        bottom.addWidget(self.collapse_btn)

        bottom.addStretch(1)

        self.execute_btn = QPushButton("退避を実行")
        self.execute_btn.setEnabled(False)
        self.execute_btn.clicked.connect(self._on_execute_clicked)
        bottom.addWidget(self.execute_btn)
        root.addLayout(bottom)

        self.setStatusBar(QStatusBar())

    def _build_path_row(self, label: str, key: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        edit = QLineEdit()
        setattr(self, f"{key}_edit", edit)
        row.addWidget(edit, stretch=1)
        btn = QPushButton("参照")
        btn.clicked.connect(lambda: self._browse_folder(edit, label))
        row.addWidget(btn)
        return row

    def _browse_folder(self, edit: QLineEdit, label: str) -> None:
        start = edit.text().strip() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, f"{label} を選択", start)
        if path:
            edit.setText(path)

    # ---- Settings persistence ----------------------------------------------

    def _restore_paths(self) -> None:
        p = self._settings.value("parent_folder", "", type=str)
        d = self._settings.value("dest_folder", "", type=str)
        if p:
            self.parent_edit.setText(p)
        if d:
            self.dest_edit.setText(d)

    def _save_paths(self) -> None:
        self._settings.setValue("parent_folder", self.parent_edit.text())
        self._settings.setValue("dest_folder", self.dest_edit.text())

    # ---- Scan ---------------------------------------------------------------

    def _on_scan_clicked(self) -> None:
        parent = self.parent_edit.text().strip()
        dest = self.dest_edit.text().strip()
        if not parent:
            QMessageBox.warning(self, "入力エラー", "親フォルダを指定してください。")
            return
        parent_path = Path(parent)
        if not parent_path.is_dir():
            QMessageBox.warning(self, "入力エラー", "親フォルダが存在しません。")
            return
        if dest:
            dest_path = Path(dest)
            if is_inside(dest_path, parent_path):
                QMessageBox.warning(
                    self,
                    "退避先の指定エラー",
                    "退避先フォルダが親フォルダの内側にあります。\n"
                    "再スキャン時に退避済みファイルを再検出して事故になるため、外側のフォルダを指定してください。",
                )
                return

        self._save_paths()
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.execute_btn.setEnabled(False)
        self.tree.clear()
        self.summary_label.setText("スキャン中...")
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText("開始しています...")

        self._thread = QThread()
        self._worker = ScanWorker(parent_path, self._ffprobe_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_cancel_clicked(self) -> None:
        if self._worker:
            self._worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.progress_label.setText("中止しています...")

    def _cleanup_thread(self) -> None:
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _on_progress(self, phase: str, done: int, total: int) -> None:
        self.progress_label.setText(phase)
        if total <= 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)

    def _on_scan_failed(self, msg: str) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_label.setText("")
        self.summary_label.setText(f"スキャン失敗: {msg}")

    def _on_scan_finished(
        self,
        groups: list[DuplicateGroup],
        all_videos: list[VideoFile],
        unprobed: list[VideoFile],
    ) -> None:
        self._groups = groups
        self._decisions = decide_all(groups)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.progress_label.setText("")
        self._populate_tree(unprobed)

        n_files_to_move = sum(
            1 for decs in self._decisions.values() for d in decs if d.action is Action.MOVE
        )
        savings = estimated_savings_bytes(self._decisions)
        self.summary_label.setText(
            f"スキャン完了: 総ファイル {len(all_videos)} / 重複グループ {len(groups)} / "
            f"退避候補 {n_files_to_move} / 推定 {fmt_size(savings)} 節約"
        )
        self.execute_btn.setEnabled(n_files_to_move > 0)

    # ---- Tree population ---------------------------------------------------

    def _populate_tree(self, unprobed: list[VideoFile]) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()

        for gi, group in enumerate(self._groups):
            decisions = self._decisions[id(group)]
            move_size = sum(d.file.size for d in decisions if d.action is Action.MOVE)
            top = QTreeWidgetItem([
                f"{group.key_name or '(空)'}  ({len(decisions)}件)",
                "",
                "",
                fmt_duration(group.representative_duration),
                "",
                fmt_size(move_size) + " 節約",
                "",
            ])
            top.setData(0, ROLE_GROUP_INDEX, gi)
            top.setFirstColumnSpanned(False)
            self.tree.addTopLevelItem(top)

            for dec in decisions:
                v = dec.file
                child = QTreeWidgetItem([
                    v.path.name,
                    v.subfolder,
                    f"{v.width}x{v.height}" if v.width and v.height else "?",
                    fmt_duration(v.duration),
                    fmt_bitrate(v.bit_rate),
                    fmt_size(v.size),
                    KEEP_LABEL if dec.action is Action.KEEP else MOVE_LABEL,
                ])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(
                    COL_ACTION,
                    Qt.Unchecked if dec.action is Action.KEEP else Qt.Checked,
                )
                child.setData(COL_NAME, ROLE_FILE, v)
                child.setToolTip(COL_NAME, str(v.path))
                self._paint_row(child, dec)
                top.addChild(child)
            top.setExpanded(True)

        if unprobed:
            unprobed_top = QTreeWidgetItem([
                f"⚠ メタ取得不可 ({len(unprobed)}件)", "", "", "", "", "", "",
            ])
            for v in unprobed:
                child = QTreeWidgetItem([
                    v.path.name, v.subfolder, "?",
                    "?", "?", fmt_size(v.size), v.probe_error or "?",
                ])
                child.setToolTip(COL_NAME, str(v.path))
                unprobed_top.addChild(child)
            self.tree.addTopLevelItem(unprobed_top)

        self.tree.blockSignals(False)

    def _paint_row(self, item: QTreeWidgetItem, dec: FileDecision) -> None:
        if dec.action is Action.KEEP:
            color = KEEP_BG
        elif dec.is_ambiguous:
            color = AMBIGUOUS_BG
        else:
            color = MOVE_BG
        brush = QBrush(color)
        for c in range(COL_COUNT):
            item.setBackground(c, brush)

    # ---- Item interaction --------------------------------------------------

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        v: Optional[VideoFile] = item.data(COL_NAME, ROLE_FILE)
        if v is None:
            return
        try:
            os.startfile(str(v.path.parent))  # type: ignore[attr-defined]
        except OSError:
            QMessageBox.warning(self, "エラー", "フォルダを開けませんでした。")

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != COL_ACTION:
            return
        v: Optional[VideoFile] = item.data(COL_NAME, ROLE_FILE)
        if v is None:
            return
        new_state = item.checkState(COL_ACTION)
        new_action = Action.MOVE if new_state == Qt.Checked else Action.KEEP

        # Update the underlying decision and re-paint.
        for decs in self._decisions.values():
            for d in decs:
                if d.file is v:
                    d.action = new_action
                    self.tree.blockSignals(True)
                    item.setText(COL_ACTION, MOVE_LABEL if new_action is Action.MOVE else KEEP_LABEL)
                    self._paint_row(item, d)
                    self.tree.blockSignals(False)
                    break

        self._refresh_summary()

    def _refresh_summary(self) -> None:
        n_move = sum(
            1 for decs in self._decisions.values() for d in decs if d.action is Action.MOVE
        )
        savings = estimated_savings_bytes(self._decisions)
        text = self.summary_label.text()
        # Replace the trailing "退避候補 ..." portion if present, else append.
        if "退避候補" in text:
            head = text.split("退避候補")[0]
            self.summary_label.setText(f"{head}退避候補 {n_move} / 推定 {fmt_size(savings)} 節約")
        else:
            self.summary_label.setText(f"退避候補 {n_move} / 推定 {fmt_size(savings)} 節約")
        self.execute_btn.setEnabled(n_move > 0)

    # ---- Execute -----------------------------------------------------------

    def _on_execute_clicked(self) -> None:
        dest = self.dest_edit.text().strip()
        if not dest:
            QMessageBox.warning(self, "入力エラー", "退避先を指定してください。")
            return
        dest_path = Path(dest)
        parent_path = Path(self.parent_edit.text().strip())
        if is_inside(dest_path, parent_path):
            QMessageBox.warning(
                self, "退避先エラー",
                "退避先が親フォルダの内側です。外側のフォルダを指定してください。",
            )
            return

        plan: list[tuple[Path, str]] = []
        for decs in self._decisions.values():
            for d in decs:
                if d.action is Action.MOVE:
                    plan.append((d.file.path, d.file.subfolder))

        if not plan:
            QMessageBox.information(self, "退避なし", "退避対象のファイルがありません。")
            return

        total_bytes = sum(d.file.size for decs in self._decisions.values() for d in decs if d.action is Action.MOVE)
        confirm = QMessageBox.question(
            self,
            "退避の確認",
            f"{len(plan)} ファイル ({fmt_size(total_bytes)}) を\n"
            f"  {dest_path}\n"
            f"へ移動します。よろしいですか?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.progress_bar.setRange(0, len(plan))
        self.progress_bar.setValue(0)
        self.progress_label.setText("退避中...")
        QApplication.processEvents()

        def on_progress(done: int, total: int) -> None:
            self.progress_bar.setValue(done)
            QApplication.processEvents()

        successes, failures = move_files(plan, dest_path, progress_cb=on_progress)
        self.progress_label.setText("")

        moved_bytes = sum(r.bytes_moved for r in successes)
        msg = f"{len(successes)} ファイルを移動しました ({fmt_size(moved_bytes)} 節約)。"
        if failures:
            msg += f"\n{len(failures)} 件失敗:\n"
            msg += "\n".join(f"- {e.src.name}: {e.error}" for e in failures[:10])
            if len(failures) > 10:
                msg += f"\n...他 {len(failures) - 10} 件"
            QMessageBox.warning(self, "退避完了 (一部失敗)", msg)
        else:
            QMessageBox.information(self, "退避完了", msg)

        # Re-scan to reflect the new state.
        self._on_scan_clicked()
