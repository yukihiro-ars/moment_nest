"""
共通ユーティリティモジュール

ファイルサイズフォーマット、日時処理、パス操作、
ログ設定、設定ファイル読み込みなどの共通機能を提供。
"""

import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Union


# =============================================================================
# ファイルサイズフォーマット
# =============================================================================

def format_file_size(bytes_size: int) -> str:
    """
    バイト数を人間が読みやすい形式にフォーマットする。

    Args:
        bytes_size: バイト数

    Returns:
        フォーマットされた文字列 (例: "1.5 GB", "256 KB")
    """
    if bytes_size < 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(bytes_size)

    for unit in units:
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0

    return f"{size:.1f} PB"


# =============================================================================
# 時間・日時フォーマット
# =============================================================================

def format_duration(seconds: float) -> str:
    """
    秒数を人間が読みやすい形式にフォーマットする。

    Args:
        seconds: 秒数

    Returns:
        フォーマットされた文字列 (例: "1時間23分", "45秒")
    """
    if seconds < 0:
        return "0秒"

    if seconds < 60:
        return f"{int(seconds)}秒"

    minutes = int(seconds // 60)
    secs = int(seconds % 60)

    if minutes < 60:
        if secs == 0:
            return f"{minutes}分"
        return f"{minutes}分{secs}秒"

    hours = minutes // 60
    mins = minutes % 60

    if mins == 0:
        return f"{hours}時間"
    return f"{hours}時間{mins}分"


def format_datetime(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    datetime オブジェクトを指定フォーマットの文字列に変換する。

    Args:
        dt: datetime オブジェクト (None の場合は空文字列を返す)
        fmt: フォーマット文字列

    Returns:
        フォーマットされた日時文字列
    """
    if dt is None:
        return ""
    return dt.strftime(fmt)


def parse_datetime(dt_string: str, formats: Optional[List[str]] = None) -> Optional[datetime]:
    """
    文字列を datetime オブジェクトにパースする。

    Args:
        dt_string: 日時文字列
        formats: 試行するフォーマットのリスト (None の場合はデフォルトを使用)

    Returns:
        datetime オブジェクト (パース失敗時は None)
    """
    if not dt_string:
        return None

    if formats is None:
        formats = [
            "%Y:%m:%d %H:%M:%S",      # EXIF形式
            "%Y-%m-%dT%H:%M:%S",      # ISO形式
            "%Y-%m-%dT%H:%M:%S.%f",   # ISO形式（ミリ秒付き）
            "%Y-%m-%d %H:%M:%S",      # 一般形式
            "%Y/%m/%d %H:%M:%S",      # スラッシュ区切り
        ]

    for fmt in formats:
        try:
            return datetime.strptime(dt_string, fmt)
        except ValueError:
            continue

    return None


def datetime_to_filename(dt: datetime) -> str:
    """
    datetime オブジェクトをファイル名用の文字列に変換する。

    Args:
        dt: datetime オブジェクト

    Returns:
        YYYYMMDDhhmmss 形式の文字列
    """
    return dt.strftime("%Y%m%d%H%M%S")


# =============================================================================
# パス操作ヘルパー
# =============================================================================

def get_file_extension(filepath: Union[str, Path]) -> str:
    """
    ファイルパスから拡張子を取得する（小文字で返す）。

    Args:
        filepath: ファイルパス

    Returns:
        拡張子 (例: ".jpg", ".mp4")
    """
    return Path(filepath).suffix.lower()


def is_supported_format(filepath: Union[str, Path], config: Dict[str, Any]) -> bool:
    """
    ファイルが対応形式かどうかを判定する。

    Args:
        filepath: ファイルパス
        config: 設定辞書 (supported_extensions を含む)

    Returns:
        対応形式なら True
    """
    ext = get_file_extension(filepath)
    supported = config.get("supported_extensions", {})

    image_exts = [e.lower() for e in supported.get("image", [])]
    video_exts = [e.lower() for e in supported.get("video", [])]

    return ext in image_exts or ext in video_exts


def is_image_file(filepath: Union[str, Path], config: Dict[str, Any]) -> bool:
    """
    ファイルが画像形式かどうかを判定する。

    Args:
        filepath: ファイルパス
        config: 設定辞書

    Returns:
        画像形式なら True
    """
    ext = get_file_extension(filepath)
    supported = config.get("supported_extensions", {})
    image_exts = [e.lower() for e in supported.get("image", [])]
    return ext in image_exts


def is_video_file(filepath: Union[str, Path], config: Dict[str, Any]) -> bool:
    """
    ファイルが動画形式かどうかを判定する。

    Args:
        filepath: ファイルパス
        config: 設定辞書

    Returns:
        動画形式なら True
    """
    ext = get_file_extension(filepath)
    supported = config.get("supported_extensions", {})
    video_exts = [e.lower() for e in supported.get("video", [])]
    return ext in video_exts


def get_year_from_datetime(dt: datetime) -> str:
    """
    datetime から年を文字列で取得する。

    Args:
        dt: datetime オブジェクト

    Returns:
        年の文字列 (例: "2024")
    """
    return str(dt.year)


# =============================================================================
# ハッシュ計算
# =============================================================================

def calculate_hash(filepath: Union[str, Path], buffer_size: int = 65536) -> Optional[str]:
    """
    ファイルのSHA-256ハッシュを計算する。

    Args:
        filepath: ファイルパス
        buffer_size: 読み込みバッファサイズ

    Returns:
        ハッシュ値の16進数文字列 (エラー時は None)
    """
    sha256_hash = hashlib.sha256()

    try:
        with open(filepath, "rb") as f:
            while True:
                data = f.read(buffer_size)
                if not data:
                    break
                sha256_hash.update(data)
        return sha256_hash.hexdigest()
    except (OSError, IOError) as e:
        logging.error(f"ハッシュ計算エラー: {filepath} - {e}")
        return None


# =============================================================================
# 設定ファイル読み込み
# =============================================================================

def load_config(config_path: Union[str, Path] = "config.json") -> Dict[str, Any]:
    """
    設定ファイルを読み込む。

    Args:
        config_path: 設定ファイルのパス

    Returns:
        設定辞書

    Raises:
        FileNotFoundError: 設定ファイルが見つからない
        json.JSONDecodeError: JSONパースエラー
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # デフォルト値の設定
    config.setdefault("network", {})
    config["network"].setdefault("retry_count", 3)
    config["network"].setdefault("retry_delay", 5)
    config["network"].setdefault("connection_timeout", 300)
    config["network"].setdefault("batch_size", 50)
    config["network"].setdefault("checkpoint_interval", 100)
    config["network"].setdefault("connection_check_interval", 250)

    config.setdefault("performance", {})
    config["performance"].setdefault("hash_buffer_size", 65536)
    config["performance"].setdefault("parallel_hash", False)
    config["performance"].setdefault("low_priority_mode", True)

    config.setdefault("hash_optimization", {})
    config["hash_optimization"].setdefault("skip_unique_sizes", True)
    config["hash_optimization"].setdefault("min_duplicate_count", 2)

    config.setdefault("supported_extensions", {
        "image": [".jpg", ".jpeg", ".heic", ".png"],
        "video": [".mp4", ".mov", ".3gp", ".m4v"]
    })

    config.setdefault("lock", {})
    config["lock"].setdefault("auto_delete_hours", 24)

    config.setdefault("logging", {})
    config["logging"].setdefault("level", "INFO")
    config["logging"].setdefault("file", "photo-organizer.log")

    return config


def get_default_config() -> Dict[str, Any]:
    """
    デフォルト設定を取得する。

    Returns:
        デフォルト設定辞書
    """
    return {
        "paths": {
            "source_dir": "",
            "organized_dir": "",
            "workspace_dir": "."
        },
        "network": {
            "retry_count": 3,
            "retry_delay": 5,
            "connection_timeout": 300,
            "batch_size": 50,
            "checkpoint_interval": 100,
            "connection_check_interval": 250
        },
        "performance": {
            "hash_buffer_size": 65536,
            "parallel_hash": False,
            "low_priority_mode": True
        },
        "hash_optimization": {
            "skip_unique_sizes": True,
            "min_duplicate_count": 2
        },
        "incremental_mode": {
            "scan_existing": True,
            "skip_duplicates": True,
            "continue_sequence": True,
            "check_cross_folder": True
        },
        "supported_extensions": {
            "image": [".jpg", ".jpeg", ".heic", ".png"],
            "video": [".mp4", ".mov", ".3gp", ".m4v"]
        },
        "filename_pattern": "YYYYMMDDhhmmss-NN",
        "lock": {
            "auto_delete_hours": 24
        },
        "logging": {
            "level": "INFO",
            "file": "photo-organizer.log"
        }
    }


# =============================================================================
# ログ設定
# =============================================================================

def setup_logging(
    config: Optional[Dict[str, Any]] = None,
    log_file: Optional[str] = None,
    level: Optional[str] = None
) -> logging.Logger:
    """
    ロギングを設定する。

    Args:
        config: 設定辞書 (logging セクションを参照)
        log_file: ログファイルパス (config より優先)
        level: ログレベル (config より優先)

    Returns:
        設定済みのルートロガー
    """
    # 設定値の決定
    if config:
        log_config = config.get("logging", {})
        log_file = log_file or log_config.get("file", "photo-organizer.log")
        level = level or log_config.get("level", "INFO")
    else:
        log_file = log_file or "photo-organizer.log"
        level = level or "INFO"

    # ログレベルの変換
    log_level = getattr(logging, level.upper(), logging.INFO)

    # ルートロガーの設定
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # 既存のハンドラをクリア
    logger.handlers.clear()

    # フォーマッタ
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # コンソールハンドラ
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイルハンドラ
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (OSError, IOError) as e:
            logger.warning(f"ログファイルを開けません: {log_file} - {e}")

    return logger


# =============================================================================
# チェックポイント管理
# =============================================================================

class Checkpoint:
    """
    処理の中断・再開を管理するチェックポイントクラス。
    """

    def __init__(self, checkpoint_path: Union[str, Path]):
        """
        Args:
            checkpoint_path: チェックポイントファイルのパス
        """
        self.checkpoint_path = Path(checkpoint_path)
        self.data: Dict[str, Any] = {
            "phase": "",
            "total_files": 0,
            "processed_count": 0,
            "last_updated": "",
            "processed_files": {}
        }
        self._load()

    def _load(self) -> None:
        """チェックポイントファイルを読み込む。"""
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logging.warning(f"チェックポイント読み込みエラー: {e}")

    def save(self) -> None:
        """チェックポイントをファイルに保存する。"""
        self.data["last_updated"] = datetime.now().isoformat()

        # 親ディレクトリを作成
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logging.error(f"チェックポイント保存エラー: {e}")

    def set_phase(self, phase: str) -> None:
        """現在のフェーズを設定する。"""
        self.data["phase"] = phase
        self.save()

    def set_total(self, total: int) -> None:
        """総ファイル数を設定する。"""
        self.data["total_files"] = total

    def mark_processed(self, filepath: str, result: Dict[str, Any]) -> None:
        """ファイルを処理済みとしてマークする。"""
        self.data["processed_files"][filepath] = {
            **result,
            "processed_at": datetime.now().isoformat()
        }
        self.data["processed_count"] = len(self.data["processed_files"])

    def is_processed(self, filepath: str) -> bool:
        """ファイルが処理済みかどうかを判定する。"""
        return filepath in self.data["processed_files"]

    def should_skip(self, filepath: str) -> bool:
        """ファイルをスキップすべきかどうかを判定する。"""
        return self.is_processed(filepath)

    def get_processed_result(self, filepath: str) -> Optional[Dict[str, Any]]:
        """処理済みファイルの結果を取得する。"""
        return self.data["processed_files"].get(filepath)

    def get_progress(self) -> tuple:
        """進捗状況を取得する。"""
        return (self.data["processed_count"], self.data["total_files"])

    def get_last_index(self) -> int:
        """最後に処理したインデックスを取得する。"""
        return self.data["processed_count"]

    def clear(self) -> None:
        """チェックポイントをクリアする。"""
        self.data = {
            "phase": "",
            "total_files": 0,
            "processed_count": 0,
            "last_updated": "",
            "processed_files": {}
        }
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
