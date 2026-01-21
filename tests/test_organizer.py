"""
modules/organizer.py のテスト
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.organizer import FileOrganizer


class TestFileOrganizer:
    """FileOrganizer のテスト"""

    @pytest.fixture
    def organizer(self, sample_config):
        return FileOrganizer(sample_config)

    @pytest.fixture
    def organize_plan(self, sample_config, temp_dir):
        """テスト用整理計画"""
        source_dir = Path(sample_config["paths"]["source_dir"])
        organized_dir = Path(sample_config["paths"]["organized_dir"])

        # テストファイル作成
        (source_dir / "photo1.jpg").write_bytes(b"photo1 content")
        (source_dir / "photo2.jpg").write_bytes(b"photo2 content")

        return {
            "created_at": datetime.now().isoformat(),
            "source_dir": str(source_dir),
            "organized_dir": str(organized_dir),
            "summary": {
                "move_count": 2,
                "skip_count": 0,
                "total_size": 28,
            },
            "disk_check": {
                "required": 28,
                "available": 1000000000,
                "sufficient": True,
            },
            "move_plan": [
                {
                    "original": str(source_dir / "photo1.jpg"),
                    "new_path": str(organized_dir / "2024" / "20240615143022-01.jpg"),
                    "new_relative_path": "2024/20240615143022-01.jpg",
                    "taken_at": "2024-06-15T14:30:22",
                    "size": 14,
                },
                {
                    "original": str(source_dir / "photo2.jpg"),
                    "new_path": str(organized_dir / "2024" / "20240615143022-02.jpg"),
                    "new_relative_path": "2024/20240615143022-02.jpg",
                    "taken_at": "2024-06-15T14:30:22",
                    "size": 14,
                },
            ],
            "skip_plan": [],
            "warnings": [],
        }

    def test_organize_basic(self, organizer, organize_plan, sample_config):
        """基本的な整理が成功すること"""
        # 計画を保存
        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(organize_plan, f)

        result = organizer.organize(organize_plan)

        assert result["success"] == 2
        assert result["failed"] == 0

        # ファイルがコピーされていること
        organized_dir = Path(sample_config["paths"]["organized_dir"])
        assert (organized_dir / "2024" / "20240615143022-01.jpg").exists()
        assert (organized_dir / "2024" / "20240615143022-02.jpg").exists()

    def test_organize_creates_year_folders(self, organizer, organize_plan, sample_config):
        """年フォルダが作成されること"""
        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(organize_plan, f)

        organizer.organize(organize_plan)

        organized_dir = Path(sample_config["paths"]["organized_dir"])
        assert (organized_dir / "2024").is_dir()

    def test_organize_skips_nonexistent_source(self, organizer, sample_config):
        """存在しないソースファイルをスキップすること"""
        source_dir = Path(sample_config["paths"]["source_dir"])
        organized_dir = Path(sample_config["paths"]["organized_dir"])

        plan = {
            "disk_check": {"sufficient": True},
            "move_plan": [
                {
                    "original": str(source_dir / "nonexistent.jpg"),
                    "new_path": str(organized_dir / "2024" / "20240615143022-01.jpg"),
                },
            ],
        }

        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(plan, f)

        result = organizer.organize(plan)

        assert result["skipped"] == 1
        assert result["success"] == 0

    def test_organize_skips_existing_destination(self, organizer, sample_config):
        """既存のコピー先ファイルをスキップすること"""
        source_dir = Path(sample_config["paths"]["source_dir"])
        organized_dir = Path(sample_config["paths"]["organized_dir"])

        # ソースファイル作成
        (source_dir / "photo.jpg").write_bytes(b"content")

        # コピー先も作成（既存）
        (organized_dir / "2024").mkdir(parents=True)
        (organized_dir / "2024" / "20240615143022-01.jpg").write_bytes(b"existing")

        plan = {
            "disk_check": {"sufficient": True},
            "move_plan": [
                {
                    "original": str(source_dir / "photo.jpg"),
                    "new_path": str(organized_dir / "2024" / "20240615143022-01.jpg"),
                },
            ],
        }

        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(plan, f)

        result = organizer.organize(plan)

        assert result["skipped"] == 1
        assert result["success"] == 0

    def test_organize_verifies_hash(self, organizer, organize_plan, sample_config):
        """コピー後にハッシュ検証が行われること"""
        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(organize_plan, f)

        result = organizer.organize(organize_plan)

        # 成功した操作はハッシュ検証済み
        for op in result["operations"]:
            if op["status"] == "success":
                assert op["hash_verified"] is True

    def test_organize_empty_plan(self, organizer, sample_config):
        """空の計画で正しく動作すること"""
        plan = {
            "disk_check": {"sufficient": True},
            "move_plan": [],
        }

        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(plan, f)

        result = organizer.organize(plan)

        assert result["total"] == 0
        assert result["success"] == 0

    def test_organize_saves_log(self, organizer, organize_plan, sample_config):
        """整理ログが保存されること"""
        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(organize_plan, f)

        organizer.organize(organize_plan)

        log_path = reports_dir / "organize_log.json"
        assert log_path.exists()

        with open(log_path, "r", encoding="utf-8") as f:
            log = json.load(f)

        assert "executed_at" in log
        assert "operations" in log

    def test_organize_saves_result_files(self, organizer, organize_plan, sample_config):
        """success.txt と failed.txt が保存されること"""
        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(organize_plan, f)

        organizer.organize(organize_plan)

        assert (reports_dir / "success.txt").exists()
        assert (reports_dir / "failed.txt").exists()

    def test_organize_disk_insufficient_raises_error(self, organizer, sample_config):
        """ディスク容量不足でエラーが発生すること"""
        source_dir = Path(sample_config["paths"]["source_dir"])
        organized_dir = Path(sample_config["paths"]["organized_dir"])

        # ソースファイル作成
        (source_dir / "photo.jpg").write_bytes(b"content")

        plan = {
            "disk_check": {
                "sufficient": False,
                "required": 1000000000000,
                "required_formatted": "1 TB",
                "available": 100,
                "available_formatted": "100 B",
            },
            "move_plan": [
                {
                    "original": str(source_dir / "photo.jpg"),
                    "new_path": str(organized_dir / "2024" / "20240615143022-01.jpg"),
                },
            ],
        }

        reports_dir = organizer.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(reports_dir / "organize_plan.json", "w") as f:
            json.dump(plan, f)

        with pytest.raises(RuntimeError) as exc_info:
            organizer.organize(plan)

        assert "ディスク容量が不足" in str(exc_info.value)


class TestCopyAndVerify:
    """_copy_and_verify メソッドのテスト"""

    @pytest.fixture
    def organizer(self, sample_config):
        return FileOrganizer(sample_config)

    def test_copy_success(self, organizer, temp_dir):
        """コピーが成功すること"""
        src = temp_dir / "source.txt"
        dst = temp_dir / "dest.txt"
        src.write_text("content")

        result = organizer._copy_and_verify(str(src), str(dst))

        assert result["status"] == "success"
        assert result["hash_verified"] is True
        assert dst.exists()

    def test_copy_source_not_exists(self, organizer, temp_dir):
        """ソースが存在しない場合スキップすること"""
        src = temp_dir / "nonexistent.txt"
        dst = temp_dir / "dest.txt"

        result = organizer._copy_and_verify(str(src), str(dst))

        assert result["status"] == "skipped"
        assert "存在しません" in result["error"]

    def test_copy_dest_exists(self, organizer, temp_dir):
        """コピー先が存在する場合スキップすること"""
        src = temp_dir / "source.txt"
        dst = temp_dir / "dest.txt"
        src.write_text("source")
        dst.write_text("existing")

        result = organizer._copy_and_verify(str(src), str(dst))

        assert result["status"] == "skipped"
        assert "既に存在" in result["error"]
