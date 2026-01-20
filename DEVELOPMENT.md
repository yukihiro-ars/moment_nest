# 開発者ガイド

このドキュメントは、NAS写真・動画整理ツールの開発者向けガイドです。

---

## 目次

1. [開発環境セットアップ](#開発環境セットアップ)
2. [アーキテクチャ](#アーキテクチャ)
3. [モジュール構成](#モジュール構成)
4. [データフォーマット](#データフォーマット)
5. [コーディング規約](#コーディング規約)
6. [テスト方針](#テスト方針)
7. [デバッグ方法](#デバッグ方法)

---

## 開発環境セットアップ

### 必須要件
- Python 3.8以上
- pip
- 開発用NASまたはテスト用ディレクトリ

### セットアップ手順

```bash
# 1. リポジトリクローン
git clone <repository-url>
cd photo-organizer

# 2. 仮想環境作成
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. 依存ライブラリインストール
pip install -r requirements.txt

# 4. 開発用ライブラリインストール（オプション）
pip install pytest pytest-cov black flake8 mypy

# 5. 設定ファイル作成
cp config.json.sample config.json
# config.json を編集してテスト環境に合わせる
```

### 推奨開発ツール
- **IDE**: VSCode, PyCharm
- **Linter**: flake8
- **Formatter**: black
- **Type Checker**: mypy

---

## アーキテクチャ

### 全体構造

```
┌─────────────────────────────────────┐
│        organize.py (メイン)         │
│      対話モード・フロー制御          │
└─────────────────────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼───┐   ┌───▼───┐   ┌───▼───┐
│Scanner│   │Planner│   │Organiz│
│       │   │       │   │  er   │
└───┬───┘   └───┬───┘   └───┬───┘
    │            │            │
    └────────────┼────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼────┐  ┌───▼────┐  ┌───▼────┐
│Metadata│  │Network │  │  Lock  │
│        │  │        │  │        │
└────────┘  └────────┘  └────────┘
```

### 設計原則

1. **関心の分離**: 各モジュールは単一責任を持つ
2. **疎結合**: モジュール間の依存を最小化
3. **再利用性**: 共通処理はutilsに集約
4. **エラーハンドリング**: 各層で適切にエラーを処理
5. **段階的処理**: Phaseごとに独立して動作可能

### データフロー

```
source/ (NAS)
    ↓ スキャン
metadata_report.json (PC)
    ↓ ハッシュ計算
hash_report.json (PC)
    ↓ 分析
analysis_report.json (PC)
    ↓ 計画
organize_plan.txt (PC)
    ↓ 実行
organized/ (NAS)
    ↓ クリーンアップ
source/ 削除
```

---

## モジュール構成

### organize.py（メインスクリプト）

**責務**: 対話モードの実装、Phaseフロー制御

```python
主要な関数:
- main(): エントリーポイント
- phase_1a(): Phase 1a実行・確認
- phase_1b(): Phase 1b実行・確認
- phase_1c(): Phase 1c実行・確認
- phase_2(): Phase 2実行・確認
- phase_3(): Phase 3実行・確認
- phase_5a(): Phase 5a実行・確認
- phase_5b(): Phase 5b実行・確認
- display_summary(): レポートサマリー表示
- confirm_continue(): 継続確認プロンプト
```

### modules/metadata.py

**責務**: EXIF・動画メタデータの抽出

```python
クラス:
- ImageMetadataExtractor: 画像用
  * extract_from_jpeg()
  * extract_from_heic()
  * extract_from_png()
  
- VideoMetadataExtractor: 動画用
  * extract_from_mp4()
  * extract_from_mov()
  
- MetadataExtractor: 統合インターフェース
  * extract(filepath): ファイル形式を判定して適切な抽出
  * get_taken_at(): 撮影日時取得（優先順位適用）
  * get_camera_info(): カメラ情報（将来用）
  * get_gps_info(): GPS情報（将来用）

戻り値の形式:
{
  "filepath": "source/IMG_1234.jpg",
  "taken_at": "2024-12-15T14:30:22",
  "date_source": "exif",  # exif, metadata, file_ctime
  "camera_make": "Apple",
  "camera_model": "iPhone 13",
  "width": 4032,
  "height": 3024,
  "gps_latitude": 35.6812,
  "gps_longitude": 139.7671
}
```

### modules/network.py

**責務**: NASファイル操作（リトライ、タイムアウト）

```python
クラス:
- NASFileHandler:
  * read_with_retry(filepath): ファイル読み取り
  * copy_with_retry(src, dst): ファイルコピー
  * delete_with_retry(filepath): ファイル削除
  * check_connection(nas_path): 接続確認
  * calculate_hash(filepath): ハッシュ計算（リトライ付き）
  
設定:
- retry_count: リトライ回数（デフォルト3）
- retry_delay: リトライ間隔（デフォルト5秒）
- timeout: タイムアウト（デフォルト300秒）
```

### modules/lock.py

**責務**: 二重起動防止、ロックファイル管理

```python
クラス:
- LockManager:
  * acquire(): ロック取得
  * release(): ロック解放
  * update_phase(phase): 現在フェーズ更新
  * check_existing_lock(): 既存ロックチェック
  * is_old_lock(hours): 古いロック判定
  
ロックファイル構造:
{
  "started_at": "2025-01-16T10:30:00",
  "pc_name": "DESKTOP-ABC123",
  "current_phase": "phase1b_hash"
}
```

### modules/scanner.py

**責務**: ファイルスキャン、ハッシュ計算、分析

```python
クラス:
- PhotoScanner:
  * scan_metadata(source_dir, organized_dir): Phase 1a
  * scan_hash(metadata_report): Phase 1b
  * analyze(metadata_report, hash_report): Phase 1c
  
メソッド詳細:
- scan_metadata():
  1. source/ をスキャン
  2. organized/ を軽量スキャン
  3. メタデータ抽出
  4. レポート出力
  
- scan_hash():
  1. サイズグループ化
  2. サイズフィルタリング
  3. ハッシュ計算（対象のみ）
  4. チェックポイント保存
  
- analyze():
  1. メタデータ + ハッシュ統合
  2. 重複検出
  3. 統計情報生成
```

### modules/planner.py

**責務**: 整理計画の作成

```python
クラス:
- FilePlanner:
  * create_plan(analysis_report, existing_files): 計画作成
  * generate_filename(taken_at, ext, existing): ファイル名生成
  * check_disk_space(plan): ディスク容量チェック
  
ファイル名生成ロジック:
1. 撮影日時から基本名: YYYYMMDDhhmmss
2. organized/ の既存ファイルチェック
3. 連番決定: -01, -02, ...
4. 衝突回避
```

### modules/organizer.py

**責務**: ファイルの実際の整理（コピー・検証）

```python
クラス:
- FileOrganizer:
  * organize(plan, checkpoint_manager): 整理実行
  * copy_file(src, dst): ファイルコピー
  * verify_copy(src, dst): コピー検証（ハッシュ）
  * create_year_folders(organized_dir): 年フォルダ作成
  
バッチ処理:
- batch_size件ごとに処理
- 5バッチごとにNAS接続確認
- チェックポイント保存
```

### modules/cleaner.py

**責務**: クリーンアップ（ファイル削除）

```python
クラス:
- FileCleaner:
  * cleanup_originals(organize_log): Phase 5a
  * cleanup_duplicates(duplicates_report): Phase 5b
  * confirm_delete(file_list): 削除確認
  
削除条件:
- Phase 5a: status="success" かつ hash_verified=true
- Phase 5b: ユーザー選択
```

### modules/utils.py

**責務**: 共通ユーティリティ

```python
関数:
- format_file_size(bytes): ファイルサイズフォーマット
- format_duration(seconds): 処理時間フォーマット
- format_datetime(dt): 日時フォーマット
- calculate_hash(filepath, buffer_size): ハッシュ計算
- get_file_extension(filepath): 拡張子取得
- is_supported_format(filepath, config): 対応形式判定

クラス:
- Checkpoint: チェックポイント管理
  * save(index, data): 保存
  * load(): 読み込み
  * should_skip(filepath): スキップ判定
  * get_last_index(): 最終インデックス取得
```

---

## データフォーマット

### metadata_report.json

```json
{
  "scan_date": "2025-01-16T10:30:00",
  "source_dir": "Z:/Photos/source",
  "total_files": 1234,
  "by_type": {
    "image": 1000,
    "video": 234
  },
  "date_range": {
    "earliest": "2020-01-01T00:00:00",
    "latest": "2025-01-15T23:59:59"
  },
  "files": [
    {
      "original_path": "source/IMG_1234.jpg",
      "size": 2048576,
      "extension": ".jpg",
      "taken_at": "2024-12-15T14:30:22",
      "date_source": "exif",
      "camera_make": "Apple",
      "camera_model": "iPhone 13"
    }
  ],
  "warnings": [
    {
      "file": "source/corrupted.jpg",
      "message": "EXIF読み取り失敗、ファイル作成日時を使用"
    }
  ]
}
```

### existing_files.json

```json
{
  "scan_date": "2025-01-16T10:30:00",
  "organized_dir": "Z:/Photos/organized",
  "total_files": 25000,
  "files": {
    "20241215143022-01.jpg": {
      "size": 2048576,
      "path": "organized/2024/20241215143022-01.jpg"
    }
  },
  "size_map": {
    "2048576": [
      "organized/2024/20241215143022-01.jpg"
    ]
  },
  "sequence_map": {
    "20241215143022": 2  // 次は -03 から
  }
}
```

### hash_report.json

```json
{
  "scan_date": "2025-01-16T12:00:00",
  "total_files": 30000,
  "hash_calculated": 6000,
  "hash_skipped": 24000,
  "optimization_stats": {
    "unique_sizes": 24000,
    "duplicate_sizes": 6000,
    "time_saved_estimate": "6.4 hours"
  },
  "files": [
    {
      "path": "source/IMG_1234.jpg",
      "size": 2048576,
      "hash": "abc123...",
      "hash_status": "calculated"
    },
    {
      "path": "source/IMG_5678.jpg",
      "size": 2048577,
      "hash": null,
      "hash_status": "skipped_unique_size"
    }
  ]
}
```

### analysis_report.json

```json
{
  "analysis_date": "2025-01-16T12:30:00",
  "total_files": 30000,
  "duplicates": {
    "source_internal": [
      {
        "hash": "abc123...",
        "files": [
          "source/IMG_1234.jpg",
          "source/backup/IMG_1234.jpg"
        ]
      }
    ],
    "source_vs_organized": [
      {
        "hash": "def456...",
        "files": [
          "source/IMG_9999.jpg",
          "organized/2024/20241215143022-01.jpg"
        ]
      }
    ]
  },
  "statistics": {
    "date_range": {...},
    "by_type": {...},
    "by_camera": {...}
  }
}
```

### organize_plan.txt（人間可読）

```
整理計画
=====================================
作成日時: 2025-01-16 13:00:00

処理予定: 1200ファイル
スキップ: 34ファイル（重複等）

移動計画:
----------------------------------------
source/IMG_1234.jpg (2.0 MB)
  → organized/2024/20241215143022-01.jpg
  撮影日時: 2024-12-15 14:30:22

source/VID_5678.mp4 (100.5 MB)
  → organized/2024/20241215143022-02.mp4
  撮影日時: 2024-12-15 14:30:22

...

スキップファイル:
----------------------------------------
source/IMG_9999.jpg
  理由: 既に整理済み (organized/2024/20241215143022-01.jpg)

必要なディスク容量: 15.2 GB
現在の空き容量: 50.3 GB
```

### organize_log.json

```json
{
  "executed_at": "2025-01-16T14:00:00",
  "total": 1200,
  "success": 1195,
  "failed": 5,
  "operations": [
    {
      "status": "success",
      "original": "source/IMG_1234.jpg",
      "new": "organized/2024/20241215143022-01.jpg",
      "hash_verified": true,
      "copied_at": "2025-01-16T14:05:23"
    },
    {
      "status": "failed",
      "original": "source/corrupted.jpg",
      "error": "ファイル読み取りエラー",
      "retry_count": 3
    }
  ]
}
```

---

## コーディング規約

### Pythonスタイル

- **PEP 8** に準拠
- **black** でフォーマット
- **flake8** でリント
- 行の長さ: 最大88文字（black デフォルト）

### 命名規則

```python
# クラス: PascalCase
class PhotoScanner:
    pass

# 関数・変数: snake_case
def scan_metadata():
    file_count = 0

# 定数: UPPER_CASE
MAX_RETRY_COUNT = 3

# プライベート: _prefix
def _internal_method():
    pass
```

### docstring

```python
def scan_metadata(source_dir: str, organized_dir: str) -> dict:
    """
    source/ と organized/ をスキャンしてメタデータを抽出する。
    
    Args:
        source_dir (str): 整理前のファイル格納ディレクトリ
        organized_dir (str): 整理後のディレクトリ
        
    Returns:
        dict: メタデータレポート
            {
                "total_files": int,
                "files": [...],
                ...
            }
            
    Raises:
        OSError: ディレクトリアクセスエラー
        ValueError: 設定エラー
    """
    pass
```

### 型ヒント

```python
from typing import List, Dict, Optional
from pathlib import Path

def process_files(
    files: List[Path],
    config: Dict[str, any],
    checkpoint: Optional[Checkpoint] = None
) -> Dict[str, any]:
    pass
```

### エラーハンドリング

```python
# 具体的な例外を捕捉
try:
    data = read_file(path)
except FileNotFoundError:
    logger.error(f"ファイルが見つかりません: {path}")
    return None
except PermissionError:
    logger.error(f"アクセス権限がありません: {path}")
    return None
except Exception as e:
    logger.exception(f"予期しないエラー: {e}")
    raise

# リソースは確実に解放
with open(file, 'r') as f:
    data = f.read()
```

### ログ出力

```python
import logging

logger = logging.getLogger(__name__)

# レベル別に使い分け
logger.debug("デバッグ情報")
logger.info("正常な処理")
logger.warning("警告")
logger.error("エラー")
logger.exception("例外（スタックトレース付き）")
```

---

## テスト方針

### ディレクトリ構成

```
tests/
├── __init__.py
├── test_metadata.py
├── test_network.py
├── test_scanner.py
├── test_planner.py
├── test_organizer.py
├── test_cleaner.py
├── test_lock.py
├── test_utils.py
└── fixtures/
    ├── sample_images/
    │   ├── test.jpg
    │   └── test.heic
    └── sample_videos/
        └── test.mp4
```

### 単体テスト例

```python
# tests/test_metadata.py
import pytest
from pathlib import Path
from modules.metadata import ImageMetadataExtractor

class TestImageMetadataExtractor:
    def test_extract_jpeg_exif(self):
        """JPEG EXIFの正常抽出をテスト"""
        extractor = ImageMetadataExtractor()
        result = extractor.extract_from_jpeg(
            Path("tests/fixtures/sample_images/test.jpg")
        )
        
        assert result is not None
        assert "taken_at" in result
        assert result["date_source"] == "exif"
    
    def test_extract_no_exif_fallback(self):
        """EXIF無しの場合のフォールバックをテスト"""
        extractor = ImageMetadataExtractor()
        result = extractor.extract_from_jpeg(
            Path("tests/fixtures/sample_images/no_exif.jpg")
        )
        
        assert result is not None
        assert result["date_source"] == "file_ctime"
```

### 統合テスト例

```python
# tests/test_integration.py
import pytest
from pathlib import Path
from organize import main

class TestFullWorkflow:
    def test_initial_run(self, tmp_path):
        """初回実行の統合テスト"""
        # テスト環境セットアップ
        source = tmp_path / "source"
        organized = tmp_path / "organized"
        source.mkdir()
        organized.mkdir()
        
        # テストファイル配置
        # ...
        
        # プログラム実行（対話モックあり）
        # ...
        
        # 結果検証
        assert (organized / "2024").exists()
        # ...
```

### テスト実行

```bash
# 全テスト実行
pytest

# カバレッジ付き
pytest --cov=modules --cov-report=html

# 特定のテストのみ
pytest tests/test_metadata.py

# マーカーでフィルタ
pytest -m "slow"  # @pytest.mark.slow のテストのみ
```

---

## デバッグ方法

### ログレベル設定

```python
# config.json
{
  "logging": {
    "level": "DEBUG",  # DEBUG, INFO, WARNING, ERROR
    "file": "photo-organizer.log"
  }
}
```

### デバッグモード実行

```bash
# 環境変数でデバッグモード
DEBUG=1 python organize.py

# またはコード内で
import os
DEBUG = os.getenv('DEBUG', False)

if DEBUG:
    print(f"Debug: {variable}")
```

### プロファイリング

```python
# 処理時間計測
import time

start = time.time()
# ... 処理 ...
elapsed = time.time() - start
logger.info(f"処理時間: {elapsed:.2f}秒")
```

```bash
# cProfileでプロファイリング
python -m cProfile -o profile.stats organize.py

# 結果確認
python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumtime').print_stats(20)"
```

### メモリ使用量確認

```python
import psutil
import os

process = psutil.Process(os.getpid())
memory_info = process.memory_info()
print(f"メモリ使用量: {memory_info.rss / 1024 / 1024:.2f} MB")
```

---

## よくある開発課題と解決方法

### 問題: HEICファイルが読めない
```bash
# pillow-heif のインストール確認
pip install pillow-heif

# macOS の場合、追加で libheif が必要
brew install libheif
```

### 問題: ffmpeg-python でエラー
```bash
# ffmpeg 本体のインストールが必要
# Windows: https://ffmpeg.org/download.html からダウンロード
# macOS
brew install ffmpeg
# Linux
sudo apt-get install ffmpeg
```

### 問題: NASへの接続が不安定
```python
# リトライ設定を調整
{
  "network": {
    "retry_count": 5,      # 増やす
    "retry_delay": 10,     # 延ばす
    "batch_size": 25       # 小さくする
  }
}
```

---

## コミット規約

### コミットメッセージ形式

```
<type>: <subject>

<body>

<footer>
```

### type の種類
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: フォーマット
- `refactor`: リファクタリング
- `test`: テスト追加
- `chore`: ビルド・補助ツール

### 例
```
feat: Phase 1a メタデータスキャン機能を実装

- source/ の再帰的スキャン
- EXIF抽出（JPEG, HEIC, PNG）
- 動画メタデータ抽出
- プログレスバー表示

Closes #12
```

---

## リリース手順

1. バージョン番号更新（`__version__` in `organize.py`）
2. CHANGELOG.md 更新
3. テスト実行・合格確認
4. ドキュメント最終確認
5. Git タグ作成: `git tag v1.0.0`
6. プッシュ: `git push --tags`

---

## 参考資料

- [Python公式ドキュメント](https://docs.python.org/3/)
- [PEP 8 スタイルガイド](https://peps.python.org/pep-0008/)
- [Pillow ドキュメント](https://pillow.readthedocs.io/)
- [pytest ドキュメント](https://docs.pytest.org/)
