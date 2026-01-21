"""
メタデータ抽出モジュール

EXIF・動画メタデータの抽出を担当。
撮影日時、カメラ情報、GPS情報などを取得する。
"""

import logging
import os
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union

# 画像処理
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# HEIC対応
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False

# ffmpeg（動画メタデータ）
try:
    import ffmpeg
    FFMPEG_AVAILABLE = True
except ImportError:
    FFMPEG_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# 画像メタデータ抽出
# =============================================================================

class ImageMetadataExtractor:
    """
    画像ファイルからEXIFメタデータを抽出するクラス。
    JPEG, PNG, HEIC形式に対応。
    """

    # EXIF日時タグの優先順位
    DATETIME_TAGS = [
        "DateTimeOriginal",    # 撮影日時（最優先）
        "DateTimeDigitized",   # デジタル化日時
        "DateTime",            # 更新日時
    ]

    # EXIF日時フォーマット
    EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"

    def __init__(self):
        if not PIL_AVAILABLE:
            logger.warning("Pillowがインストールされていません。画像メタデータ抽出が制限されます。")

    def extract(self, filepath: Union[str, Path]) -> Dict[str, Any]:
        """
        画像ファイルからメタデータを抽出する。

        Args:
            filepath: 画像ファイルのパス

        Returns:
            メタデータ辞書
        """
        filepath = Path(filepath)
        ext = filepath.suffix.lower()

        result = {
            "filepath": str(filepath),
            "taken_at": None,
            "date_source": None,
            "camera_make": None,
            "camera_model": None,
            "width": None,
            "height": None,
            "gps_latitude": None,
            "gps_longitude": None,
            "orientation": None,
            "error": None,
        }

        if not PIL_AVAILABLE:
            result["error"] = "Pillowが利用できません"
            return self._fallback_to_file_time(filepath, result)

        if ext == ".heic" and not HEIF_AVAILABLE:
            result["error"] = "pillow-heifが利用できません"
            return self._fallback_to_file_time(filepath, result)

        try:
            if ext in [".jpg", ".jpeg"]:
                return self._extract_from_jpeg(filepath, result)
            elif ext == ".heic":
                return self._extract_from_heic(filepath, result)
            elif ext == ".png":
                return self._extract_from_png(filepath, result)
            else:
                result["error"] = f"未対応の画像形式: {ext}"
                return self._fallback_to_file_time(filepath, result)

        except Exception as e:
            logger.warning(f"メタデータ抽出エラー: {filepath} - {e}")
            result["error"] = str(e)
            return self._fallback_to_file_time(filepath, result)

    def _extract_from_jpeg(self, filepath: Path, result: Dict[str, Any]) -> Dict[str, Any]:
        """JPEGファイルからEXIFを抽出する。"""
        with Image.open(filepath) as img:
            result["width"] = img.width
            result["height"] = img.height

            exif_data = img._getexif()
            if exif_data:
                result = self._parse_exif(exif_data, result)

        if result["taken_at"] is None:
            return self._fallback_to_file_time(filepath, result)

        return result

    def _extract_from_heic(self, filepath: Path, result: Dict[str, Any]) -> Dict[str, Any]:
        """HEICファイルからEXIFを抽出する。"""
        with Image.open(filepath) as img:
            result["width"] = img.width
            result["height"] = img.height

            # HEICのEXIF取得
            exif_data = img.getexif()
            if exif_data:
                # 標準EXIFタグを処理
                decoded_exif = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    decoded_exif[tag_name] = value

                result = self._parse_exif_dict(decoded_exif, result)

        if result["taken_at"] is None:
            return self._fallback_to_file_time(filepath, result)

        return result

    def _extract_from_png(self, filepath: Path, result: Dict[str, Any]) -> Dict[str, Any]:
        """PNGファイルからメタデータを抽出する。"""
        with Image.open(filepath) as img:
            result["width"] = img.width
            result["height"] = img.height

            # PNGは通常EXIFを持たないが、一部のツールで埋め込まれることがある
            exif_data = img.getexif()
            if exif_data:
                decoded_exif = {}
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    decoded_exif[tag_name] = value
                result = self._parse_exif_dict(decoded_exif, result)

        if result["taken_at"] is None:
            return self._fallback_to_file_time(filepath, result)

        return result

    def _parse_exif(self, exif_data: Dict[int, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """EXIFデータ（タグID形式）をパースする。"""
        decoded = {}
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            decoded[tag_name] = value

        return self._parse_exif_dict(decoded, result)

    def _parse_exif_dict(self, exif_dict: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """デコード済みEXIF辞書をパースする。"""
        # 撮影日時を優先順位に従って取得
        for tag_name in self.DATETIME_TAGS:
            if tag_name in exif_dict:
                dt_str = exif_dict[tag_name]
                if isinstance(dt_str, bytes):
                    dt_str = dt_str.decode("utf-8", errors="ignore")
                dt_str = str(dt_str).strip()

                if dt_str and dt_str != "0000:00:00 00:00:00":
                    try:
                        result["taken_at"] = datetime.strptime(dt_str, self.EXIF_DATETIME_FORMAT)
                        result["date_source"] = "exif"
                        break
                    except ValueError:
                        continue

        # カメラ情報
        if "Make" in exif_dict:
            make = exif_dict["Make"]
            if isinstance(make, bytes):
                make = make.decode("utf-8", errors="ignore")
            result["camera_make"] = str(make).strip()

        if "Model" in exif_dict:
            model = exif_dict["Model"]
            if isinstance(model, bytes):
                model = model.decode("utf-8", errors="ignore")
            result["camera_model"] = str(model).strip()

        # 向き
        if "Orientation" in exif_dict:
            result["orientation"] = exif_dict["Orientation"]

        # GPS情報
        if "GPSInfo" in exif_dict:
            gps_info = exif_dict["GPSInfo"]
            result = self._parse_gps_info(gps_info, result)

        return result

    def _parse_gps_info(self, gps_info: Dict, result: Dict[str, Any]) -> Dict[str, Any]:
        """GPS情報をパースする。"""
        try:
            # GPSタグをデコード
            gps_data = {}
            for tag_id, value in gps_info.items():
                tag_name = GPSTAGS.get(tag_id, str(tag_id))
                gps_data[tag_name] = value

            # 緯度
            if "GPSLatitude" in gps_data and "GPSLatitudeRef" in gps_data:
                lat = self._convert_to_degrees(gps_data["GPSLatitude"])
                if gps_data["GPSLatitudeRef"] == "S":
                    lat = -lat
                result["gps_latitude"] = lat

            # 経度
            if "GPSLongitude" in gps_data and "GPSLongitudeRef" in gps_data:
                lon = self._convert_to_degrees(gps_data["GPSLongitude"])
                if gps_data["GPSLongitudeRef"] == "W":
                    lon = -lon
                result["gps_longitude"] = lon

        except Exception as e:
            logger.debug(f"GPS情報パースエラー: {e}")

        return result

    def _convert_to_degrees(self, value) -> float:
        """GPS座標を度数に変換する。"""
        d, m, s = value
        # 分数オブジェクトの場合の処理
        if hasattr(d, "numerator"):
            d = d.numerator / d.denominator
        if hasattr(m, "numerator"):
            m = m.numerator / m.denominator
        if hasattr(s, "numerator"):
            s = s.numerator / s.denominator

        return float(d) + float(m) / 60 + float(s) / 3600

    def _fallback_to_file_time(self, filepath: Path, result: Dict[str, Any]) -> Dict[str, Any]:
        """ファイル作成日時にフォールバックする。"""
        try:
            stat = filepath.stat()
            # Windowsではst_ctime、Unix系ではst_mtimeを使用
            if os.name == "nt":
                file_time = stat.st_ctime
            else:
                file_time = stat.st_mtime

            result["taken_at"] = datetime.fromtimestamp(file_time)
            result["date_source"] = "file_ctime"
        except OSError as e:
            logger.error(f"ファイル情報取得エラー: {filepath} - {e}")
            result["date_source"] = "unknown"

        return result


# =============================================================================
# 動画メタデータ抽出
# =============================================================================

class VideoMetadataExtractor:
    """
    動画ファイルからメタデータを抽出するクラス。
    MP4, MOV, 3GP, M4V形式に対応。ffmpeg-pythonを使用。
    """

    def __init__(self):
        if not FFMPEG_AVAILABLE:
            logger.warning("ffmpeg-pythonがインストールされていません。動画メタデータ抽出が制限されます。")

    def extract(self, filepath: Union[str, Path]) -> Dict[str, Any]:
        """
        動画ファイルからメタデータを抽出する。

        Args:
            filepath: 動画ファイルのパス

        Returns:
            メタデータ辞書
        """
        filepath = Path(filepath)

        result = {
            "filepath": str(filepath),
            "taken_at": None,
            "date_source": None,
            "width": None,
            "height": None,
            "duration": None,
            "codec": None,
            "error": None,
        }

        if not FFMPEG_AVAILABLE:
            result["error"] = "ffmpeg-pythonが利用できません"
            return self._fallback_to_file_time(filepath, result)

        try:
            return self._extract_with_ffprobe(filepath, result)
        except Exception as e:
            logger.warning(f"動画メタデータ抽出エラー: {filepath} - {e}")
            result["error"] = str(e)
            return self._fallback_to_file_time(filepath, result)

    def _extract_with_ffprobe(self, filepath: Path, result: Dict[str, Any]) -> Dict[str, Any]:
        """ffprobeを使用してメタデータを抽出する。"""
        try:
            probe = ffmpeg.probe(str(filepath))
        except ffmpeg.Error as e:
            raise RuntimeError(f"ffprobe実行エラー: {e.stderr}")

        # フォーマット情報
        format_info = probe.get("format", {})
        tags = format_info.get("tags", {})

        # 撮影日時（creation_time）
        creation_time = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
        if creation_time:
            result["taken_at"] = self._parse_creation_time(creation_time)
            if result["taken_at"]:
                result["date_source"] = "metadata"

        # 動画の長さ
        if "duration" in format_info:
            try:
                result["duration"] = float(format_info["duration"])
            except (ValueError, TypeError):
                pass

        # ストリーム情報（映像）
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                result["width"] = stream.get("width")
                result["height"] = stream.get("height")
                result["codec"] = stream.get("codec_name")
                break

        # フォールバック
        if result["taken_at"] is None:
            return self._fallback_to_file_time(filepath, result)

        return result

    def _parse_creation_time(self, creation_time: str) -> Optional[datetime]:
        """creation_time文字列をdatetimeに変換する。"""
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",      # ISO形式（ミリ秒・UTC）
            "%Y-%m-%dT%H:%M:%SZ",          # ISO形式（UTC）
            "%Y-%m-%dT%H:%M:%S.%f%z",      # ISO形式（ミリ秒・タイムゾーン）
            "%Y-%m-%dT%H:%M:%S%z",         # ISO形式（タイムゾーン）
            "%Y-%m-%d %H:%M:%S",           # 一般形式
            "%Y-%m-%dT%H:%M:%S",           # ISO形式（ローカル）
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(creation_time, fmt)
                # UTCの場合はローカル時間に変換しない（将来の拡張用）
                return dt.replace(tzinfo=None) if dt.tzinfo else dt
            except ValueError:
                continue

        logger.debug(f"creation_timeパース失敗: {creation_time}")
        return None

    def _fallback_to_file_time(self, filepath: Path, result: Dict[str, Any]) -> Dict[str, Any]:
        """ファイル作成日時にフォールバックする。"""
        try:
            stat = filepath.stat()
            if os.name == "nt":
                file_time = stat.st_ctime
            else:
                file_time = stat.st_mtime

            result["taken_at"] = datetime.fromtimestamp(file_time)
            result["date_source"] = "file_ctime"
        except OSError as e:
            logger.error(f"ファイル情報取得エラー: {filepath} - {e}")
            result["date_source"] = "unknown"

        return result


# =============================================================================
# 統合メタデータ抽出インターフェース
# =============================================================================

class MetadataExtractor:
    """
    画像・動画のメタデータ抽出を統合するクラス。
    ファイル形式を自動判定して適切な抽出器を使用する。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Args:
            config: 設定辞書（supported_extensionsを含む）
        """
        self.config = config or {}
        self.image_extractor = ImageMetadataExtractor()
        self.video_extractor = VideoMetadataExtractor()

        # デフォルトの対応拡張子
        supported = self.config.get("supported_extensions", {})
        self.image_extensions = [e.lower() for e in supported.get("image", [".jpg", ".jpeg", ".heic", ".png"])]
        self.video_extensions = [e.lower() for e in supported.get("video", [".mp4", ".mov", ".3gp", ".m4v"])]

    def extract(self, filepath: Union[str, Path]) -> Dict[str, Any]:
        """
        ファイルからメタデータを抽出する。

        Args:
            filepath: ファイルパス

        Returns:
            メタデータ辞書
        """
        filepath = Path(filepath)
        ext = filepath.suffix.lower()

        if ext in self.image_extensions:
            return self.image_extractor.extract(filepath)
        elif ext in self.video_extensions:
            return self.video_extractor.extract(filepath)
        else:
            return {
                "filepath": str(filepath),
                "taken_at": None,
                "date_source": "unsupported",
                "error": f"未対応のファイル形式: {ext}",
            }

    def get_taken_at(self, filepath: Union[str, Path]) -> Optional[datetime]:
        """
        ファイルの撮影日時を取得する。

        Args:
            filepath: ファイルパス

        Returns:
            撮影日時（取得失敗時はNone）
        """
        result = self.extract(filepath)
        return result.get("taken_at")

    def is_supported(self, filepath: Union[str, Path]) -> bool:
        """
        ファイルが対応形式かどうかを判定する。

        Args:
            filepath: ファイルパス

        Returns:
            対応形式ならTrue
        """
        ext = Path(filepath).suffix.lower()
        return ext in self.image_extensions or ext in self.video_extensions

    def is_image(self, filepath: Union[str, Path]) -> bool:
        """ファイルが画像形式かどうかを判定する。"""
        return Path(filepath).suffix.lower() in self.image_extensions

    def is_video(self, filepath: Union[str, Path]) -> bool:
        """ファイルが動画形式かどうかを判定する。"""
        return Path(filepath).suffix.lower() in self.video_extensions


# =============================================================================
# モジュールレベル関数（簡易アクセス用）
# =============================================================================

_default_extractor: Optional[MetadataExtractor] = None


def get_extractor(config: Optional[Dict[str, Any]] = None) -> MetadataExtractor:
    """
    MetadataExtractorのシングルトンインスタンスを取得する。

    Args:
        config: 設定辞書（初回呼び出し時のみ使用）

    Returns:
        MetadataExtractorインスタンス
    """
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = MetadataExtractor(config)
    return _default_extractor


def extract_metadata(filepath: Union[str, Path], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    ファイルからメタデータを抽出する簡易関数。

    Args:
        filepath: ファイルパス
        config: 設定辞書

    Returns:
        メタデータ辞書
    """
    extractor = get_extractor(config)
    return extractor.extract(filepath)
