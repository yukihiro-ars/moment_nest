"""
modules/utils.py のテスト
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.utils import (
    format_file_size,
    format_duration,
    format_datetime,
    parse_datetime,
    datetime_to_filename,
    get_file_extension,
    is_supported_format,
    is_image_file,
    is_video_file,
    get_year_from_datetime,
    calculate_hash,
    load_config,
    get_default_config,
    Checkpoint,
)


class TestFormatFileSize:
    """format_file_size のテスト"""

    def test_bytes(self):
        assert format_file_size(0) == "0 B"
        assert format_file_size(100) == "100 B"
        assert format_file_size(1023) == "1023 B"

    def test_kilobytes(self):
        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(10240) == "10.0 KB"

    def test_megabytes(self):
        assert format_file_size(1048576) == "1.0 MB"
        assert format_file_size(1572864) == "1.5 MB"

    def test_gigabytes(self):
        assert format_file_size(1073741824) == "1.0 GB"
        assert format_file_size(1610612736) == "1.5 GB"

    def test_terabytes(self):
        assert format_file_size(1099511627776) == "1.0 TB"

    def test_negative(self):
        assert format_file_size(-100) == "0 B"


class TestFormatDuration:
    """format_duration のテスト"""

    def test_seconds(self):
        assert format_duration(0) == "0秒"
        assert format_duration(30) == "30秒"
        assert format_duration(59) == "59秒"

    def test_minutes(self):
        assert format_duration(60) == "1分"
        assert format_duration(90) == "1分30秒"
        assert format_duration(3599) == "59分59秒"

    def test_hours(self):
        assert format_duration(3600) == "1時間"
        assert format_duration(3660) == "1時間1分"
        assert format_duration(7200) == "2時間"

    def test_negative(self):
        assert format_duration(-10) == "0秒"


class TestFormatDatetime:
    """format_datetime のテスト"""

    def test_default_format(self):
        dt = datetime(2024, 12, 15, 14, 30, 22)
        assert format_datetime(dt) == "2024-12-15 14:30:22"

    def test_custom_format(self):
        dt = datetime(2024, 12, 15, 14, 30, 22)
        assert format_datetime(dt, "%Y/%m/%d") == "2024/12/15"

    def test_none(self):
        assert format_datetime(None) == ""


class TestParseDatetime:
    """parse_datetime のテスト"""

    def test_exif_format(self):
        result = parse_datetime("2024:12:15 14:30:22")
        assert result == datetime(2024, 12, 15, 14, 30, 22)

    def test_iso_format(self):
        result = parse_datetime("2024-12-15T14:30:22")
        assert result == datetime(2024, 12, 15, 14, 30, 22)

    def test_general_format(self):
        result = parse_datetime("2024-12-15 14:30:22")
        assert result == datetime(2024, 12, 15, 14, 30, 22)

    def test_invalid_format(self):
        result = parse_datetime("invalid")
        assert result is None

    def test_empty_string(self):
        result = parse_datetime("")
        assert result is None


class TestDatetimeToFilename:
    """datetime_to_filename のテスト"""

    def test_conversion(self):
        dt = datetime(2024, 12, 15, 14, 30, 22)
        assert datetime_to_filename(dt) == "20241215143022"

    def test_zero_padding(self):
        dt = datetime(2024, 1, 5, 9, 5, 2)
        assert datetime_to_filename(dt) == "20240105090502"


class TestGetFileExtension:
    """get_file_extension のテスト"""

    def test_jpg(self):
        assert get_file_extension("photo.jpg") == ".jpg"
        assert get_file_extension("photo.JPG") == ".jpg"

    def test_heic(self):
        assert get_file_extension("photo.heic") == ".heic"
        assert get_file_extension("photo.HEIC") == ".heic"

    def test_mp4(self):
        assert get_file_extension("video.mp4") == ".mp4"

    def test_path_object(self):
        assert get_file_extension(Path("photo.jpg")) == ".jpg"

    def test_full_path(self):
        assert get_file_extension("/path/to/photo.jpg") == ".jpg"


class TestIsSupportedFormat:
    """is_supported_format のテスト"""

    @pytest.fixture
    def config(self):
        return {
            "supported_extensions": {
                "image": [".jpg", ".jpeg", ".heic", ".png"],
                "video": [".mp4", ".mov"],
            }
        }

    def test_supported_image(self, config):
        assert is_supported_format("photo.jpg", config) is True
        assert is_supported_format("photo.JPEG", config) is True
        assert is_supported_format("photo.heic", config) is True

    def test_supported_video(self, config):
        assert is_supported_format("video.mp4", config) is True
        assert is_supported_format("video.MOV", config) is True

    def test_unsupported(self, config):
        assert is_supported_format("document.pdf", config) is False
        assert is_supported_format("image.gif", config) is False


class TestIsImageFile:
    """is_image_file のテスト"""

    @pytest.fixture
    def config(self):
        return {
            "supported_extensions": {
                "image": [".jpg", ".jpeg", ".heic", ".png"],
                "video": [".mp4", ".mov"],
            }
        }

    def test_image(self, config):
        assert is_image_file("photo.jpg", config) is True
        assert is_image_file("photo.png", config) is True

    def test_not_image(self, config):
        assert is_image_file("video.mp4", config) is False


class TestIsVideoFile:
    """is_video_file のテスト"""

    @pytest.fixture
    def config(self):
        return {
            "supported_extensions": {
                "image": [".jpg", ".jpeg", ".heic", ".png"],
                "video": [".mp4", ".mov"],
            }
        }

    def test_video(self, config):
        assert is_video_file("video.mp4", config) is True
        assert is_video_file("video.mov", config) is True

    def test_not_video(self, config):
        assert is_video_file("photo.jpg", config) is False


class TestGetYearFromDatetime:
    """get_year_from_datetime のテスト"""

    def test_year(self):
        dt = datetime(2024, 12, 15)
        assert get_year_from_datetime(dt) == "2024"

    def test_different_year(self):
        dt = datetime(2020, 1, 1)
        assert get_year_from_datetime(dt) == "2020"


class TestCalculateHash:
    """calculate_hash のテスト"""

    def test_hash_calculation(self, temp_dir):
        # テストファイル作成
        filepath = temp_dir / "test.txt"
        filepath.write_text("hello world")

        result = calculate_hash(filepath)

        # SHA-256 of "hello world"
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert result == expected

    def test_nonexistent_file(self, temp_dir):
        filepath = temp_dir / "nonexistent.txt"
        result = calculate_hash(filepath)
        assert result is None


class TestLoadConfig:
    """load_config のテスト"""

    def test_load_valid_config(self, temp_dir):
        config_path = temp_dir / "config.json"
        config_data = {
            "paths": {
                "source_dir": "/source",
                "organized_dir": "/organized",
            }
        }
        config_path.write_text(json.dumps(config_data))

        result = load_config(config_path)

        assert result["paths"]["source_dir"] == "/source"
        # デフォルト値が設定されていることを確認
        assert "network" in result
        assert result["network"]["retry_count"] == 3

    def test_nonexistent_config(self, temp_dir):
        config_path = temp_dir / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            load_config(config_path)


class TestGetDefaultConfig:
    """get_default_config のテスト"""

    def test_default_config(self):
        config = get_default_config()

        assert "paths" in config
        assert "network" in config
        assert "supported_extensions" in config
        assert config["network"]["retry_count"] == 3


class TestCheckpoint:
    """Checkpoint クラスのテスト"""

    def test_create_and_save(self, temp_dir):
        checkpoint_path = temp_dir / "checkpoint.json"
        checkpoint = Checkpoint(checkpoint_path)

        checkpoint.set_phase("test_phase")
        checkpoint.set_total(100)
        checkpoint.mark_processed("file1.jpg", {"status": "success"})
        checkpoint.save()

        assert checkpoint_path.exists()

    def test_load_existing(self, temp_dir):
        checkpoint_path = temp_dir / "checkpoint.json"

        # 最初のチェックポイント
        cp1 = Checkpoint(checkpoint_path)
        cp1.set_phase("test_phase")
        cp1.mark_processed("file1.jpg", {"status": "success"})
        cp1.save()

        # 再読み込み
        cp2 = Checkpoint(checkpoint_path)

        assert cp2.data["phase"] == "test_phase"
        assert cp2.is_processed("file1.jpg") is True
        assert cp2.is_processed("file2.jpg") is False

    def test_should_skip(self, temp_dir):
        checkpoint_path = temp_dir / "checkpoint.json"
        checkpoint = Checkpoint(checkpoint_path)

        checkpoint.mark_processed("file1.jpg", {"status": "success"})

        assert checkpoint.should_skip("file1.jpg") is True
        assert checkpoint.should_skip("file2.jpg") is False

    def test_get_progress(self, temp_dir):
        checkpoint_path = temp_dir / "checkpoint.json"
        checkpoint = Checkpoint(checkpoint_path)

        checkpoint.set_total(100)
        checkpoint.mark_processed("file1.jpg", {})
        checkpoint.mark_processed("file2.jpg", {})

        processed, total = checkpoint.get_progress()
        assert processed == 2
        assert total == 100

    def test_clear(self, temp_dir):
        checkpoint_path = temp_dir / "checkpoint.json"
        checkpoint = Checkpoint(checkpoint_path)

        checkpoint.mark_processed("file1.jpg", {})
        checkpoint.save()
        checkpoint.clear()

        assert not checkpoint_path.exists()
        assert checkpoint.data["processed_count"] == 0
