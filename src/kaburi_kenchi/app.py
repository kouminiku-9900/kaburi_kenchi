from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from kaburi_kenchi.probe import find_ffprobe
from kaburi_kenchi.ui.main_window import MainWindow


FFPROBE_INSTALL_HINT = (
    "ffprobe (FFmpeg) が見つかりませんでした。\n\n"
    "このアプリは動画の再生時間や解像度を取得するために ffprobe を使います。\n\n"
    "インストール方法:\n"
    "1. https://www.gyan.dev/ffmpeg/builds/ から 'release essentials' を取得\n"
    "2. 解凍した bin フォルダのパスを Windows の環境変数 PATH に追加\n"
    "3. PowerShell / コマンドプロンプトを開き直して `ffprobe -version` が動くことを確認\n"
    "4. このアプリを再起動\n\n"
    "winget が使える環境なら以下でも入ります:\n"
    "    winget install Gyan.FFmpeg"
)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("kaburi_kenchi")
    app.setOrganizationName("kaburi_kenchi")

    ffprobe = find_ffprobe()
    if ffprobe is None:
        QMessageBox.critical(None, "ffprobe が必要です", FFPROBE_INSTALL_HINT)
        return 1

    window = MainWindow(ffprobe)
    window.show()
    return app.exec()
