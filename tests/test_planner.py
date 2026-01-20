"""
modules/planner.py のテスト
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.planner import FilePlanner


class TestFilePlanner:
    """FilePlanner のテスト"""

    @pytest.fixture
    def planner(self, sample_config):
        return FilePlanner(sample_config)

    @pytest.fixture
    def analysis_report(self, sample_config):
        """テスト用分析レポート"""
        source_dir = sample_config["paths"]["source_dir"]
        return {
            "analysis_date": datetime.now().isoformat(),
            "total_files": 3,
            "files": [
                {
                    "filepath": f"{source_dir}/photo1.jpg",
                    "relative_path": "photo1.jpg",
                    "taken_at": "2024-06-15T14:30:22",
                    "extension": ".jpg",
                    "size": 1000,
                    "is_duplicate_internal": False,
                    "is_duplicate_with_existing": False,
                },
                {
                    "filepath": f"{source_dir}/photo2.jpg",
                    "relative_path": "photo2.jpg",
                    "taken_at": "2024-06-15T14:30:22",  # 同じ秒
                    "extension": ".jpg",
                    "size": 1000,
                    "is_duplicate_internal": False,
                    "is_duplicate_with_existing": False,
                },
                {
                    "filepath": f"{source_dir}/photo3.jpg",
                    "relative_path": "photo3.jpg",
                    "taken_at": "2024-12-25T10:00:00",
                    "extension": ".jpg",
                    "size": 2000,
                    "is_duplicate_internal": False,
                    "is_duplicate_with_existing": False,
                },
            ],
            "duplicates": {
                "source_internal": [],
                "source_vs_organized": [],
            },
        }

    @pytest.fixture
    def existing_files(self, sample_config):
        """テスト用既存ファイル情報"""
        return {
            "scan_date": datetime.now().isoformat(),
            "organized_dir": sample_config["paths"]["organized_dir"],
            "total_files": 0,
            "files": {},
            "size_map": {},
            "sequence_map": {},
        }

    def test_create_plan_basic(self, planner, analysis_report, existing_files):
        """基本的な計画作成ができること"""
        # レポートを保存
        reports_dir = planner.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        with open(reports_dir / "analysis_report.json", "w") as f:
            json.dump(analysis_report, f)
        with open(reports_dir / "existing_files.json", "w") as f:
            json.dump(existing_files, f)

        plan = planner.create_plan(analysis_report, existing_files)

        assert "move_plan" in plan
        assert "skip_plan" in plan
        assert "summary" in plan
        assert plan["summary"]["move_count"] == 3
        assert plan["summary"]["skip_count"] == 0

    def test_create_plan_generates_filenames(self, planner, analysis_report, existing_files):
        """ファイル名が正しく生成されること"""
        reports_dir = planner.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        with open(reports_dir / "analysis_report.json", "w") as f:
            json.dump(analysis_report, f)
        with open(reports_dir / "existing_files.json", "w") as f:
            json.dump(existing_files, f)

        plan = planner.create_plan(analysis_report, existing_files)

        move_plan = plan["move_plan"]
        # 同じ秒のファイルは連番が振られる
        filenames = [Path(m["new_path"]).name for m in move_plan]

        assert "20240615143022-01.jpg" in filenames
        assert "20240615143022-02.jpg" in filenames
        assert "20241225100000-01.jpg" in filenames

    def test_create_plan_organizes_by_year(self, planner, analysis_report, existing_files):
        """年フォルダに整理されること"""
        reports_dir = planner.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        with open(reports_dir / "analysis_report.json", "w") as f:
            json.dump(analysis_report, f)
        with open(reports_dir / "existing_files.json", "w") as f:
            json.dump(existing_files, f)

        plan = planner.create_plan(analysis_report, existing_files)

        paths = [m["new_relative_path"] for m in plan["move_plan"]]

        assert any("2024/" in p for p in paths)

    def test_create_plan_skips_duplicates(self, planner, existing_files, sample_config):
        """既に整理済みのファイルをスキップすること"""
        source_dir = sample_config["paths"]["source_dir"]
        analysis_report = {
            "analysis_date": datetime.now().isoformat(),
            "total_files": 2,
            "files": [
                {
                    "filepath": f"{source_dir}/photo1.jpg",
                    "relative_path": "photo1.jpg",
                    "taken_at": "2024-06-15T14:30:22",
                    "extension": ".jpg",
                    "size": 1000,
                    "is_duplicate_internal": False,
                    "is_duplicate_with_existing": True,  # 既に存在
                },
                {
                    "filepath": f"{source_dir}/photo2.jpg",
                    "relative_path": "photo2.jpg",
                    "taken_at": "2024-06-15T14:30:23",
                    "extension": ".jpg",
                    "size": 1000,
                    "is_duplicate_internal": False,
                    "is_duplicate_with_existing": False,
                },
            ],
            "duplicates": {},
        }

        reports_dir = planner.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        with open(reports_dir / "analysis_report.json", "w") as f:
            json.dump(analysis_report, f)
        with open(reports_dir / "existing_files.json", "w") as f:
            json.dump(existing_files, f)

        plan = planner.create_plan(analysis_report, existing_files)

        assert plan["summary"]["move_count"] == 1
        assert plan["summary"]["skip_count"] == 1
        assert plan["skip_plan"][0]["reason"] == "already_organized"

    def test_create_plan_continues_sequence(self, planner, analysis_report, sample_config):
        """既存ファイルの連番を継続すること"""
        existing_files = {
            "scan_date": datetime.now().isoformat(),
            "organized_dir": sample_config["paths"]["organized_dir"],
            "total_files": 1,
            "files": {
                "20240615143022-01.jpg": {
                    "size": 1000,
                    "path": "2024/20240615143022-01.jpg",
                }
            },
            "size_map": {},
            "sequence_map": {
                "20240615143022": 2,  # 次は -02 から
            },
        }

        reports_dir = planner.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        with open(reports_dir / "analysis_report.json", "w") as f:
            json.dump(analysis_report, f)
        with open(reports_dir / "existing_files.json", "w") as f:
            json.dump(existing_files, f)

        plan = planner.create_plan(analysis_report, existing_files)

        filenames = [Path(m["new_path"]).name for m in plan["move_plan"]]

        # -01 ではなく -02 から始まる
        assert "20240615143022-02.jpg" in filenames
        assert "20240615143022-03.jpg" in filenames

    def test_generate_filename(self, planner):
        """_generate_filename が正しい形式を生成すること"""
        dt = datetime(2024, 12, 15, 14, 30, 22)

        filename1 = planner._generate_filename(dt, ".jpg")
        filename2 = planner._generate_filename(dt, ".jpg")  # 同じ秒
        filename3 = planner._generate_filename(dt, ".png")  # 同じ秒、別拡張子

        assert filename1 == "20241215143022-01.jpg"
        assert filename2 == "20241215143022-02.jpg"
        assert filename3 == "20241215143022-03.png"

    def test_check_disk_space(self, planner):
        """_check_disk_space がチェック結果を返すこと"""
        result = planner._check_disk_space(1000000)  # 1MB

        assert "required" in result
        assert "required_formatted" in result
        assert "available" in result or result["error"] is not None
        assert "sufficient" in result

    def test_create_plan_disk_check(self, planner, analysis_report, existing_files):
        """計画にディスクチェック結果が含まれること"""
        reports_dir = planner.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        with open(reports_dir / "analysis_report.json", "w") as f:
            json.dump(analysis_report, f)
        with open(reports_dir / "existing_files.json", "w") as f:
            json.dump(existing_files, f)

        plan = planner.create_plan(analysis_report, existing_files)

        assert "disk_check" in plan
        assert "required" in plan["disk_check"]
