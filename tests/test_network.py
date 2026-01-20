"""
modules/network.py のテスト
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.network import NASFileHandler, BatchProcessor, RetryExhaustedError


class TestNASFileHandler:
    """NASFileHandler のテスト"""

    @pytest.fixture
    def handler(self, sample_config):
        return NASFileHandler(sample_config)

    def test_check_connection_existing_dir(self, handler, temp_dir):
        """存在するディレクトリへの接続確認が成功すること"""
        result = handler.check_connection(temp_dir)
        assert result is True

    def test_check_connection_nonexistent_dir(self, handler, temp_dir):
        """存在しないディレクトリへの接続確認が失敗すること"""
        result = handler.check_connection(temp_dir / "nonexistent")
        assert result is False

    def test_check_connection_existing_file(self, handler, temp_dir):
        """存在するファイルへの接続確認が成功すること"""
        filepath = temp_dir / "test.txt"
        filepath.write_text("test")

        result = handler.check_connection(filepath)
        assert result is True

    def test_read_file(self, handler, temp_dir):
        """ファイル読み取りが成功すること"""
        filepath = temp_dir / "test.txt"
        filepath.write_text("hello world")

        result = handler.read_file(filepath)

        assert result == b"hello world"

    def test_read_file_nonexistent(self, handler, temp_dir):
        """存在しないファイルの読み取りでエラーが発生すること"""
        filepath = temp_dir / "nonexistent.txt"

        with pytest.raises(RetryExhaustedError):
            handler.read_file(filepath)

    def test_copy_file(self, handler, temp_dir):
        """ファイルコピーが成功すること"""
        src = temp_dir / "source.txt"
        dst = temp_dir / "dest.txt"
        src.write_text("copy me")

        result = handler.copy_file(src, dst, verify=True)

        assert result["success"] is True
        assert result["hash_verified"] is True
        assert dst.exists()
        assert dst.read_text() == "copy me"

    def test_copy_file_creates_parent_dir(self, handler, temp_dir):
        """コピー先の親ディレクトリを作成すること"""
        src = temp_dir / "source.txt"
        dst = temp_dir / "subdir" / "dest.txt"
        src.write_text("copy me")

        result = handler.copy_file(src, dst)

        assert result["success"] is True
        assert dst.exists()

    def test_copy_file_nonexistent_source(self, handler, temp_dir):
        """存在しないソースのコピーで失敗すること"""
        src = temp_dir / "nonexistent.txt"
        dst = temp_dir / "dest.txt"

        result = handler.copy_file(src, dst)

        assert result["success"] is False
        assert result["error"] is not None

    def test_delete_file(self, handler, temp_dir):
        """ファイル削除が成功すること"""
        filepath = temp_dir / "delete_me.txt"
        filepath.write_text("delete me")

        result = handler.delete_file(filepath)

        assert result["success"] is True
        assert not filepath.exists()

    def test_delete_file_nonexistent(self, handler, temp_dir):
        """存在しないファイルの削除も成功すること"""
        filepath = temp_dir / "nonexistent.txt"

        result = handler.delete_file(filepath)

        # 既に存在しない場合は成功とみなす
        assert result["success"] is True

    def test_calculate_hash(self, handler, temp_dir):
        """ハッシュ計算が正しく行われること"""
        filepath = temp_dir / "test.txt"
        filepath.write_text("hello world")

        result = handler.calculate_hash(filepath)

        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert result == expected

    def test_calculate_hash_nonexistent(self, handler, temp_dir):
        """存在しないファイルのハッシュ計算で None を返すこと"""
        filepath = temp_dir / "nonexistent.txt"

        result = handler.calculate_hash(filepath)

        assert result is None

    def test_get_file_size(self, handler, temp_dir):
        """ファイルサイズ取得が正しく行われること"""
        filepath = temp_dir / "test.txt"
        filepath.write_bytes(b"x" * 1000)

        result = handler.get_file_size(filepath)

        assert result == 1000

    def test_get_file_size_nonexistent(self, handler, temp_dir):
        """存在しないファイルのサイズ取得で None を返すこと"""
        filepath = temp_dir / "nonexistent.txt"

        result = handler.get_file_size(filepath)

        assert result is None

    def test_list_files(self, handler, temp_dir):
        """ファイルリストが正しく取得されること"""
        (temp_dir / "test1.jpg").write_bytes(b"1")
        (temp_dir / "test2.jpg").write_bytes(b"2")
        (temp_dir / "test3.txt").write_bytes(b"3")

        result = handler.list_files(temp_dir, recursive=False)

        assert len(result) == 3

    def test_list_files_with_extension_filter(self, handler, temp_dir):
        """拡張子フィルタが正しく動作すること"""
        (temp_dir / "test1.jpg").write_bytes(b"1")
        (temp_dir / "test2.jpg").write_bytes(b"2")
        (temp_dir / "test3.txt").write_bytes(b"3")

        result = handler.list_files(temp_dir, extensions=[".jpg"])

        assert len(result) == 2
        assert all(f.suffix == ".jpg" for f in result)

    def test_list_files_recursive(self, handler, temp_dir):
        """再帰的なファイルリストが正しく取得されること"""
        (temp_dir / "test1.jpg").write_bytes(b"1")
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "test2.jpg").write_bytes(b"2")

        result = handler.list_files(temp_dir, recursive=True)

        assert len(result) == 2


class TestNASFileHandlerRetry:
    """NASFileHandler のリトライ機構のテスト"""

    @pytest.fixture
    def handler(self):
        config = {
            "network": {
                "retry_count": 2,
                "retry_delay": 0.1,  # テスト用に短く
            }
        }
        return NASFileHandler(config)

    def test_retry_on_oserror(self, handler, temp_dir):
        """OSError でリトライされること"""
        call_count = 0

        def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("Simulated error")
            return "success"

        result = handler._retry_operation(
            failing_operation,
            "test_operation"
        )

        assert result == "success"
        assert call_count == 3  # 2回失敗 + 1回成功

    def test_retry_exhausted(self, handler):
        """リトライ回数を超えるとエラーになること"""
        def always_failing():
            raise OSError("Always fails")

        with pytest.raises(RetryExhaustedError):
            handler._retry_operation(
                always_failing,
                "test_operation"
            )


class TestBatchProcessor:
    """BatchProcessor のテスト"""

    @pytest.fixture
    def handler(self, sample_config):
        return NASFileHandler(sample_config)

    def test_process_files(self, handler, temp_dir):
        """ファイルバッチ処理が正しく動作すること"""
        # テストファイル作成
        files = []
        for i in range(5):
            f = temp_dir / f"test_{i}.txt"
            f.write_text(f"content {i}")
            files.append(f)

        def operation(filepath):
            return {"filepath": str(filepath), "success": True}

        processor = BatchProcessor(
            handler,
            batch_size=2,
            connection_check_interval=10
        )

        results = processor.process_files(files, operation)

        assert len(results) == 5
        assert all(r["success"] for r in results)

    def test_process_files_with_progress_callback(self, handler, temp_dir):
        """進捗コールバックが呼ばれること"""
        files = [temp_dir / f"test_{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")

        progress_calls = []

        def progress_callback(current, total):
            progress_calls.append((current, total))

        def operation(filepath):
            return {"success": True}

        # progress_callback はコンストラクタで渡す
        processor = BatchProcessor(
            handler,
            batch_size=10,
            progress_callback=progress_callback
        )
        processor.process_files(files, operation)

        # 各ファイル処理後にコールバックが呼ばれる
        assert len(progress_calls) == 3
        assert progress_calls[-1] == (3, 3)

    def test_process_files_with_checkpoint_callback(self, handler, temp_dir):
        """チェックポイントコールバックが呼ばれること"""
        files = [temp_dir / f"test_{i}.txt" for i in range(5)]
        for f in files:
            f.write_text("content")

        checkpoint_calls = []

        def checkpoint_callback(count):
            checkpoint_calls.append(count)

        def operation(filepath):
            return {"success": True}

        processor = BatchProcessor(
            handler,
            batch_size=2,  # 2件ごとにチェックポイント
            checkpoint_callback=checkpoint_callback
        )
        processor.process_files(files, operation)

        # バッチごとにコールバックが呼ばれる
        assert 2 in checkpoint_calls or 4 in checkpoint_calls

    def test_reset(self, handler):
        """reset でカウンターがリセットされること"""
        processor = BatchProcessor(handler)
        processor._processed_count = 100
        processor._last_connection_check = 50

        processor.reset()

        assert processor._processed_count == 0
        assert processor._last_connection_check == 0
