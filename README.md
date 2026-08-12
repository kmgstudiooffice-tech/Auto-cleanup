# 🧹 Auto-Cleanup

さまざまなOS（Windows / macOS / Linux）で、ディスク容量を圧迫している
**不要なファイル・重複・長期間未使用のファイル/アプリ** を安全に整理する
クロスプラットフォーム・クリーンアップアプリです。

**安全性を最優先**に設計されています。削除は必ずユーザーの確認を経て行われ、
実体はいきなり消さずに「隔離（quarantine）」へ移動するため、いつでも復元できます。

---

## 特長

- **5種類のスキャナ**
  - `junk` : OSのキャッシュ／一時／ログ（再生成される安全なゴミ）
  - `large` : 大容量ファイル（既定 100MB以上）
  - `duplicates` : 内容が同一の重複ファイル（1つを残して提案）
  - `stale` : 長期間アクセスのないファイル（既定 180日）
  - `apps` : 長期間未使用のアプリ（**検出と削除方法の提示のみ／自動削除はしない**）
- **確認と安全機構**
  - スキャンは**何も変更しない**。削除は既定で**ドライラン**、`--apply` で初めて実行。
  - 削除は**隔離フォルダへ移動**（`~/.auto-cleanup-quarantine/<日時>/`）。`restore` で復元可能。
  - **リスク判定**: 安全（キャッシュ等）／低（大きな圧縮ファイル等）／
    **高（ドキュメント・画像・アプリ等、影響の可能性あり）**。
    高リスクは一括承認されず**必ず1件ずつ確認**します。
  - **保護パス**: システム領域・`~/.ssh`・`~/.gnupg` などは常に除外。
- **2つのフロントエンド**（同じコアエンジンを共有）
  - コマンドライン（`cleanup`）
  - ローカルWeb UI（`cleanup web`、localhost のみ）

## インストール

```bash
pip install -e ".[web]"     # Web UI も使う場合
pip install -e .            # CLI のみ
```

## 使い方（CLI）

```bash
# 1) 何が対象になるか確認（削除しない）
cleanup scan

# 特定フォルダ・カテゴリだけ
cleanup scan --path ~/Downloads --category large --category duplicates

# 2) 隔離を実行（既定はドライラン。--apply で実行）
cleanup clean                     # ドライラン（提案の確認のみ）
cleanup clean --apply             # 確認しながら実際に隔離
cleanup clean --apply --yes       # 安全〜低リスクは一括承認（高リスクは必ず個別確認）

# 3) 復元・完全削除
cleanup restore                   # 隔離セッション一覧
cleanup restore --session <ID>    # 元の場所へ戻す
cleanup purge --session <ID>      # 完全削除（復元不可）

# 設定の確認
cleanup config
```

### カテゴリ名

`junk` / `large` / `duplicates`(=`dupes`) / `stale` / `apps`

## 使い方（Web UI）

```bash
cleanup web            # http://127.0.0.1:8765 を開く
```

ブラウザ上でカテゴリ別に一覧を確認し、チェックボックスで対象を選択します。
高リスク項目を含む場合は実行前に確認ダイアログが表示されます。
「実際に隔離する」をオフにすればドライランです（安全のため既定はオフ）。

画面下部の「隔離履歴」から、各セッションを **復元**（元の場所へ戻す）または
**完全削除**（復元不可・確認あり）できます。

## デスクトップGUIアプリ（Windows .exe など）

ブラウザのタブではなく、**独立したデスクトップウィンドウ**でアプリを起動できます。

```bash
pip install -e ".[desktop]"
cleanup-gui            # ネイティブウィンドウで起動（pywebview）
```

`pywebview` が無い環境では自動的に既定のブラウザで開きます。

### 単体実行ファイル（.exe）を作る

同梱の PyInstaller 設定で、依存関係ごと**1ファイルの実行ファイル**に固められます。
`.exe` は Windows 上でのみ生成できます（`.app`/ELF も同様に各OS上でビルド）。

**Windows で手動ビルド:**

```powershell
pip install -e ".[web,desktop]" pyinstaller
pyinstaller packaging/Auto-Cleanup.spec
# dist/Auto-Cleanup.exe が生成される（ダブルクリックで起動、コンソール無し）
```

**GitHub Actions で自動ビルド（推奨）:**

`.github/workflows/build-windows.yml` により、対象ブランチへの push、または手動実行
（Actions タブ → *Build Windows EXE* → *Run workflow*）で Windows ランナーが
`Auto-Cleanup.exe` をビルドし、**Artifacts** としてダウンロードできます。
`vX.Y.Z` タグを push すると Release にも自動添付されます。

## 設定

`~/.config/auto-cleanup/config.json` で閾値などを調整できます（無い場合は既定値）。

```json
{
  "large_file_min_bytes": 104857600,
  "stale_after_seconds": 15552000,
  "duplicate_min_bytes": 1048576,
  "extra_roots": ["/path/to/also/scan"],
  "extra_protected": ["/path/to/never/touch"]
}
```

## アーキテクチャ

```
cleanup/
  core/               # UIに依存しないエンジン
    models.py         # Candidate / ScanResult / RiskLevel / Category
    config.py         # 閾値・パス設定
    platform_paths.py # OS別の対象/保護パス
    safety.py         # 保護判定・リスク分類（do-no-harm の要）
    scanner.py        # 各スキャナのオーケストレーション
    scanners/         # large_files / duplicates / stale_files / system_junk / unused_apps
    executor.py       # 隔離・復元・完全削除
  cli.py              # CLI
  web/                # FastAPI + 静的HTML（コアを呼ぶだけ）
tests/                # pytest（一時ディレクトリで各機能を検証）
```

## 開発・テスト

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

## 安全性に関する注意

- アプリ（`apps`）の**アンインストールは自動実行しません**。検出結果と、
  各OSでの削除コマンド／手順を提示するにとどめます。
- 破壊的操作の直前には必ず確認があります。`--apply` を付けない限り実ファイルは移動しません。
- 隔離したファイルは `restore` で元に戻せます。ディスクを完全に空けたい場合のみ `purge` を使ってください。

## ライセンス

MIT
