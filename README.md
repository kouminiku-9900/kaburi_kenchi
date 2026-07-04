# kaburi_kenchi

`video1`, `video2`, ... `videoN` のように分けたサブフォルダ間で **同じ動画が重複している** のを検出して、低画質側を退避フォルダに移すための Windows GUI ツール。

## できること

- 親フォルダを 1 つ指定すると、その直下のサブフォルダ全部を横断スキャン
- ファイル名（拡張子・解像度タグなど除去後）と再生時間（±1秒）が一致するものを **重複グループ** として検出
- 各グループから KEEP（残す）と MOVE（退避）を自動判定
  - 解像度 → ビットレート → ファイルサイズ の順で高画質側を KEEP
  - 同条件のときはサイズ大きい方が KEEP
- 結果はテーブルで一覧表示。チェックボックスで個別に KEEP/MOVE を切り替え可能
- 「退避を実行」で MOVE 対象を **指定の退避フォルダへ移動**（削除はしない）
- 退避フォルダに `_kaburi_kenchi_undo.json` が生成され、元のパスを記録（必要なら手動で戻せる）

## 必要なもの

- Windows 10/11
- Python 3.10+ （3.11+ 推奨）
- **ffprobe**（FFmpeg 同梱）
  - **`run.bat` が未検出時に `winget install Gyan.FFmpeg` で自動インストールする**
  - winget が無い環境では https://www.gyan.dev/ffmpeg/builds/ から手動でDLしてPATHを通す

## 起動

プロジェクトルートで:

```
run.bat
```

初回は `.venv` と PySide6 を自動でセットアップする。

## 使い方

1. **親フォルダ**: 例 `D:\videos`（中に `video1`, `video2`, …が入っている）
2. **退避先**: 例 `D:\_video_dup`（**親フォルダの外側** にすること）
3. **スキャン開始** → 進捗バーに ffprobe の進行状況
4. ツリーに重複グループが並ぶ
   - 緑背景 = KEEP（残す）
   - 橙背景 = MOVE（退避）
   - 黄背景 = MOVE だが KEEP とほぼ同画質（要確認）
5. 必要に応じてチェック切替
6. **退避を実行** → 確認ダイアログ → 移動

## 重複の判定基準

| 項目 | ロジック |
|---|---|
| ファイル名 | 拡張子除去・小文字化・括弧 `[..] (..) {..}` 内除去・解像度/コーデック/ソースタグ除去（例: `1080p`, `x264`, `web-dl`）後の正規化キー |
| 再生時間 | ffprobe で取得した秒数。同じグループ内では ±1秒 の連鎖でクラスタリング |
| 拡張子 | 違っていても同一視（`.mp4` と `.mkv` は同一動画になりがち） |

## 開発

```
python -m pytest tests/
```

## ディレクトリ構成

```
src/kaburi_kenchi/
  scanner.py            # ファイル列挙
  probe.py              # ffprobe ラッパ
  duplicate_finder.py   # 重複グループ化
  quality.py            # KEEP/MOVE 判定
  mover.py              # 退避（衝突回避リネーム + undoログ）
  app.py                # エントリ
  ui/
    main_window.py      # GUI
    scan_worker.py      # バックグラウンドスキャン
tests/
  test_duplicate_finder.py
  test_quality.py
```
