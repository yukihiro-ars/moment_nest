"""
modules/lock.py のテスト
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.lock import LockManager, LockExistsError


class TestLockManager:
    """LockManager のテスト"""

    @pytest.fixture
    def lock_manager(self, temp_dir):
        config = {"lock": {"auto_delete_hours": 24}}
        return LockManager(temp_dir, config)

    def test_acquire_creates_lock_file(self, lock_manager, temp_dir):
        """acquire がロックファイルを作成すること"""
        result = lock_manager.acquire()

        assert result is True
        assert lock_manager.lock_path.exists()
        assert lock_manager._lock_acquired is True

    def test_acquire_fails_when_lock_exists(self, lock_manager, temp_dir):
        """既存ロックがある場合 acquire が失敗すること"""
        # 先にロックを作成
        lock_manager.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_data = {
            "started_at": datetime.now().isoformat(),
            "pc_name": "other_pc",
            "current_phase": "test",
        }
        with open(lock_manager.lock_path, "w") as f:
            json.dump(lock_data, f)

        with pytest.raises(LockExistsError):
            lock_manager.acquire()

    def test_acquire_force_overwrites_lock(self, lock_manager, temp_dir):
        """force=True で既存ロックを上書きできること"""
        # 先にロックを作成
        lock_manager.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_data = {
            "started_at": datetime.now().isoformat(),
            "pc_name": "other_pc",
            "current_phase": "test",
        }
        with open(lock_manager.lock_path, "w") as f:
            json.dump(lock_data, f)

        result = lock_manager.acquire(force=True)

        assert result is True
        assert lock_manager._lock_acquired is True

    def test_release_removes_lock_file(self, lock_manager, temp_dir):
        """release がロックファイルを削除すること"""
        lock_manager.acquire()
        result = lock_manager.release()

        assert result is True
        assert not lock_manager.lock_path.exists()
        assert lock_manager._lock_acquired is False

    def test_release_without_acquire(self, lock_manager):
        """acquire なしで release すると失敗すること"""
        result = lock_manager.release()

        assert result is False

    def test_release_force_without_acquire(self, lock_manager, temp_dir):
        """force=True なら acquire なしでも release できること"""
        # ロックファイルを手動作成
        lock_manager.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_manager.lock_path.write_text("{}")

        result = lock_manager.release(force=True)

        assert result is True
        assert not lock_manager.lock_path.exists()

    def test_update_phase(self, lock_manager, temp_dir):
        """update_phase がフェーズを更新すること"""
        lock_manager.acquire()
        result = lock_manager.update_phase("phase1a")

        assert result is True

        # ファイル内容を確認
        with open(lock_manager.lock_path, "r") as f:
            data = json.load(f)
        assert data["current_phase"] == "phase1a"

    def test_update_phase_without_acquire(self, lock_manager):
        """acquire なしで update_phase すると失敗すること"""
        result = lock_manager.update_phase("phase1a")

        assert result is False

    def test_check_existing_lock_none(self, lock_manager):
        """ロックがない場合 None を返すこと"""
        result = lock_manager.check_existing_lock()

        assert result is None

    def test_check_existing_lock_exists(self, lock_manager, temp_dir):
        """ロックがある場合その情報を返すこと"""
        lock_manager.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_data = {
            "started_at": "2024-12-15T10:00:00",
            "pc_name": "test_pc",
            "current_phase": "phase1a",
        }
        with open(lock_manager.lock_path, "w") as f:
            json.dump(lock_data, f)

        result = lock_manager.check_existing_lock()

        assert result is not None
        assert result["pc_name"] == "test_pc"
        assert result["current_phase"] == "phase1a"

    def test_is_old_lock_false(self, lock_manager, temp_dir):
        """新しいロックは古くないこと"""
        lock_manager.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_data = {
            "started_at": datetime.now().isoformat(),
            "pc_name": "test_pc",
            "current_phase": "test",
        }
        with open(lock_manager.lock_path, "w") as f:
            json.dump(lock_data, f)

        result = lock_manager.is_old_lock()

        assert result is False

    def test_is_old_lock_true(self, lock_manager, temp_dir):
        """25時間前のロックは古いこと"""
        lock_manager.lock_path.parent.mkdir(parents=True, exist_ok=True)
        old_time = datetime.now() - timedelta(hours=25)
        lock_data = {
            "started_at": old_time.isoformat(),
            "pc_name": "test_pc",
            "current_phase": "test",
        }
        with open(lock_manager.lock_path, "w") as f:
            json.dump(lock_data, f)

        result = lock_manager.is_old_lock()

        assert result is True

    def test_is_old_lock_no_lock(self, lock_manager):
        """ロックがない場合 False を返すこと"""
        result = lock_manager.is_old_lock()

        assert result is False

    def test_context_manager(self, lock_manager, temp_dir):
        """コンテキストマネージャーとして使えること"""
        with lock_manager:
            assert lock_manager._lock_acquired is True
            assert lock_manager.lock_path.exists()

        assert lock_manager._lock_acquired is False
        assert not lock_manager.lock_path.exists()

    def test_get_lock_info_acquired(self, lock_manager):
        """acquire 後に get_lock_info が情報を返すこと"""
        lock_manager.acquire()

        info = lock_manager.get_lock_info()

        assert "started_at" in info
        assert "pc_name" in info
        assert "current_phase" in info

    def test_get_lock_info_not_acquired(self, lock_manager, temp_dir):
        """acquire 前に get_lock_info が既存ロック情報を返すこと"""
        lock_manager.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_data = {"started_at": "2024-12-15T10:00:00", "pc_name": "test"}
        with open(lock_manager.lock_path, "w") as f:
            json.dump(lock_data, f)

        info = lock_manager.get_lock_info()

        assert info["pc_name"] == "test"

    def test_get_lock_age_hours(self, lock_manager, temp_dir):
        """get_lock_age_hours が正しい時間を返すこと"""
        lock_manager.lock_path.parent.mkdir(parents=True, exist_ok=True)
        two_hours_ago = datetime.now() - timedelta(hours=2)
        lock_data = {
            "started_at": two_hours_ago.isoformat(),
            "pc_name": "test",
            "current_phase": "test",
        }
        with open(lock_manager.lock_path, "w") as f:
            json.dump(lock_data, f)

        age = lock_manager.get_lock_age_hours()

        assert age is not None
        assert 1.9 < age < 2.1  # 約2時間


class TestLockExistsError:
    """LockExistsError のテスト"""

    def test_error_message(self):
        """エラーメッセージが正しく生成されること"""
        lock_info = {
            "started_at": "2024-12-15T10:00:00",
            "pc_name": "test_pc",
            "current_phase": "phase1a",
        }

        error = LockExistsError(lock_info)

        assert "test_pc" in str(error)
        assert "phase1a" in str(error)

    def test_lock_info_accessible(self):
        """lock_info にアクセスできること"""
        lock_info = {"test": "value"}
        error = LockExistsError(lock_info)

        assert error.lock_info == lock_info
