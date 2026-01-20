"""
NAS写真・動画整理ツール モジュールパッケージ

各モジュールの責務:
- metadata.py: EXIF・動画メタデータの抽出
- scanner.py: ファイルスキャン、ハッシュ計算、分析
- planner.py: 整理計画の作成
- organizer.py: ファイルの整理（コピー・検証）
- cleaner.py: クリーンアップ（ファイル削除）
- network.py: NASファイル操作（リトライ、タイムアウト）
- lock.py: 二重起動防止、ロックファイル管理
- utils.py: 共通ユーティリティ
"""

from .utils import (
    format_file_size,
    format_duration,
    format_datetime,
    get_file_extension,
    is_supported_format,
    load_config,
    setup_logging,
)

__version__ = "1.0.0"
__all__ = [
    "format_file_size",
    "format_duration",
    "format_datetime",
    "get_file_extension",
    "is_supported_format",
    "load_config",
    "setup_logging",
]
