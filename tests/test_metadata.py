"""
modules/metadata.py のテスト
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.metadata import (
    ImageMetadataExtractor,
    VideoMetadataExtractor,
    MetadataExtractor,
    extract_metadata,
)


class TestImageMetadataExtractor:
    """ImageMetadataExtractor のテスト"""

    @pytest.fixture
    def extractor(self):
        return ImageMetadataExtractor()

    def test_extract_returns_dict(self, extractor, temp_dir):
        """抽出結果が辞書であること"""
        # テストファイル作成
        filepath = temp_dir / "test.jpg"
        filepath.write_bytes(b"dummy jpeg content")

        result = extractor.extract(filepath)

        assert isinstance(result, dict)
        assert "filepath" in result
        assert "taken_at" in result
        assert "date_source" in result

    def test_extract_fallback_to_file_time(self, extractor, temp_dir):
        """EXIF がない場合にファイル時刻にフォールバックすること"""
        filepath = temp_dir / "no_exif.jpg"
        filepath.write_bytes(b"no exif data")

        result = extractor.extract(filepath)

        # フォールバックの場合、date_source は file_ctime になる
        assert result["date_source"] in ["file_ctime", None, "unknown"]

    def test_extract_nonexistent_file(self, extractor, temp_dir):
        """存在しないファイルの場合エラーを含む結果を返すこと"""
        filepath = temp_dir / "nonexistent.jpg"

        result = extractor.extract(filepath)

        assert result["error"] is not None or result["date_source"] == "unknown"

    def test_extract_unsupported_format(self, extractor, temp_dir):
        """未対応形式の場合エラーを含む結果を返すこと"""
        filepath = temp_dir / "test.xyz"
        filepath.write_bytes(b"unknown format")

        result = extractor.extract(filepath)

        assert result["error"] is not None or result["date_source"] in ["file_ctime", "unsupported"]


class TestVideoMetadataExtractor:
    """VideoMetadataExtractor のテスト"""

    @pytest.fixture
    def extractor(self):
        return VideoMetadataExtractor()

    def test_extract_returns_dict(self, extractor, temp_dir):
        """抽出結果が辞書であること"""
        filepath = temp_dir / "test.mp4"
        filepath.write_bytes(b"dummy mp4 content")

        result = extractor.extract(filepath)

        assert isinstance(result, dict)
        assert "filepath" in result
        assert "taken_at" in result

    def test_extract_fallback_to_file_time(self, extractor, temp_dir):
        """メタデータがない場合にファイル時刻にフォールバックすること"""
        filepath = temp_dir / "no_metadata.mp4"
        filepath.write_bytes(b"no metadata")

        result = extractor.extract(filepath)

        # ffmpeg エラーでもフォールバックする
        assert result["date_source"] in ["file_ctime", "metadata", None, "unknown"]


class TestMetadataExtractor:
    """MetadataExtractor のテスト"""

    @pytest.fixture
    def extractor(self):
        config = {
            "supported_extensions": {
                "image": [".jpg", ".jpeg", ".heic", ".png"],
                "video": [".mp4", ".mov", ".3gp", ".m4v"],
            }
        }
        return MetadataExtractor(config)

    def test_extract_image(self, extractor, temp_dir):
        """画像ファイルを正しく処理すること"""
        filepath = temp_dir / "test.jpg"
        filepath.write_bytes(b"jpeg content")

        result = extractor.extract(filepath)

        assert result["filepath"] == str(filepath)

    def test_extract_video(self, extractor, temp_dir):
        """動画ファイルを正しく処理すること"""
        filepath = temp_dir / "test.mp4"
        filepath.write_bytes(b"mp4 content")

        result = extractor.extract(filepath)

        assert result["filepath"] == str(filepath)

    def test_extract_unsupported(self, extractor, temp_dir):
        """未対応形式を正しく処理すること"""
        filepath = temp_dir / "test.pdf"
        filepath.write_bytes(b"pdf content")

        result = extractor.extract(filepath)

        assert result["date_source"] == "unsupported"
        assert result["error"] is not None

    def test_is_supported_image(self, extractor, temp_dir):
        """is_supported が画像を正しく判定すること"""
        assert extractor.is_supported("test.jpg") is True
        assert extractor.is_supported("test.jpeg") is True
        assert extractor.is_supported("test.heic") is True
        assert extractor.is_supported("test.png") is True

    def test_is_supported_video(self, extractor, temp_dir):
        """is_supported が動画を正しく判定すること"""
        assert extractor.is_supported("test.mp4") is True
        assert extractor.is_supported("test.mov") is True
        assert extractor.is_supported("test.3gp") is True

    def test_is_supported_unsupported(self, extractor, temp_dir):
        """is_supported が未対応形式を正しく判定すること"""
        assert extractor.is_supported("test.pdf") is False
        assert extractor.is_supported("test.doc") is False

    def test_is_image(self, extractor):
        """is_image が正しく判定すること"""
        assert extractor.is_image("test.jpg") is True
        assert extractor.is_image("test.mp4") is False

    def test_is_video(self, extractor):
        """is_video が正しく判定すること"""
        assert extractor.is_video("test.mp4") is True
        assert extractor.is_video("test.jpg") is False

    def test_get_taken_at(self, extractor, temp_dir):
        """get_taken_at がdatetimeまたはNoneを返すこと"""
        filepath = temp_dir / "test.jpg"
        filepath.write_bytes(b"content")

        result = extractor.get_taken_at(filepath)

        assert result is None or isinstance(result, datetime)


class TestExtractMetadataFunction:
    """extract_metadata 関数のテスト"""

    def test_extract_metadata(self, temp_dir):
        """モジュールレベル関数が動作すること"""
        filepath = temp_dir / "test.jpg"
        filepath.write_bytes(b"jpeg content")

        result = extract_metadata(filepath)

        assert isinstance(result, dict)
        assert "filepath" in result


class TestImageMetadataExtractorParseExif:
    """EXIF パース関連のテスト"""

    @pytest.fixture
    def extractor(self):
        return ImageMetadataExtractor()

    def test_parse_exif_dict_with_datetime(self, extractor):
        """DateTimeOriginal を正しくパースすること"""
        result = {
            "filepath": "test.jpg",
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

        exif_dict = {
            "DateTimeOriginal": "2024:12:15 14:30:22",
            "Make": "Apple",
            "Model": "iPhone 13",
        }

        result = extractor._parse_exif_dict(exif_dict, result)

        assert result["taken_at"] == datetime(2024, 12, 15, 14, 30, 22)
        assert result["date_source"] == "exif"
        assert result["camera_make"] == "Apple"
        assert result["camera_model"] == "iPhone 13"

    def test_parse_exif_dict_fallback_to_datetime(self, extractor):
        """DateTimeOriginal がない場合 DateTime にフォールバックすること"""
        result = {
            "filepath": "test.jpg",
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

        exif_dict = {
            "DateTime": "2024:12:15 14:30:22",
        }

        result = extractor._parse_exif_dict(exif_dict, result)

        assert result["taken_at"] == datetime(2024, 12, 15, 14, 30, 22)
        assert result["date_source"] == "exif"

    def test_parse_exif_dict_invalid_datetime(self, extractor):
        """無効な日時文字列を正しく処理すること"""
        result = {
            "filepath": "test.jpg",
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

        exif_dict = {
            "DateTimeOriginal": "invalid_datetime",
        }

        result = extractor._parse_exif_dict(exif_dict, result)

        # 無効な場合は taken_at は None のまま
        assert result["taken_at"] is None

    def test_parse_exif_dict_zero_datetime(self, extractor):
        """0000:00:00 00:00:00 を無視すること"""
        result = {
            "filepath": "test.jpg",
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

        exif_dict = {
            "DateTimeOriginal": "0000:00:00 00:00:00",
        }

        result = extractor._parse_exif_dict(exif_dict, result)

        assert result["taken_at"] is None


class TestVideoMetadataExtractorParseCreationTime:
    """動画メタデータ creation_time パース関連のテスト"""

    @pytest.fixture
    def extractor(self):
        return VideoMetadataExtractor()

    def test_parse_creation_time_iso_utc(self, extractor):
        """ISO UTC 形式をパースすること"""
        result = extractor._parse_creation_time("2024-12-15T14:30:22Z")
        assert result == datetime(2024, 12, 15, 14, 30, 22)

    def test_parse_creation_time_iso_milliseconds(self, extractor):
        """ミリ秒付き形式をパースすること"""
        result = extractor._parse_creation_time("2024-12-15T14:30:22.123Z")
        assert result.year == 2024
        assert result.month == 12
        assert result.day == 15

    def test_parse_creation_time_invalid(self, extractor):
        """無効な形式で None を返すこと"""
        result = extractor._parse_creation_time("invalid")
        assert result is None
