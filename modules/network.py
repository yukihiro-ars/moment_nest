"""
ネットワークハンドラーモジュール

NASファイル操作（リトライ、タイムアウト）を担当。
SMB/CIFS接続での不安定性に対応するためのラッパー。
"""

import logging
import shutil
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Union, Callable, List

logger = logging.getLogger(__name__)


# =============================================================================
# 例外クラス
# =============================================================================

class NetworkError(Exception):
    """ネットワーク関連のエラー"""
    pass


class ConnectionError(NetworkError):
    """NAS接続エラー"""
    pass


class RetryExhaustedError(NetworkError):
    """リトライ回数超過エラー"""
    pass


# =============================================================================
# NASファイルハンドラー
# =============================================================================

class NASFileHandler:
    """
    NASファイル操作を行うクラス。
    リトライ機構、タイムアウト、バッチ処理をサポート。
    """

    # リトライ対象の例外
    RETRYABLE_EXCEPTIONS = (
        OSError,
        IOError,
        TimeoutError,
        PermissionError,
        ConnectionResetError,
        BrokenPipeError,
    )

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Args:
            config: 設定辞書（networkセクションを参照）
        """
        self.config = config or {}
        network_config = self.config.get("network", {})

        self.retry_count = network_config.get("retry_count", 3)
        self.retry_delay = network_config.get("retry_delay", 5)
        self.connection_timeout = network_config.get("connection_timeout", 300)
        self.batch_size = network_config.get("batch_size", 50)
        self.checkpoint_interval = network_config.get("checkpoint_interval", 100)
        self.connection_check_interval = network_config.get("connection_check_interval", 250)

        # ハッシュ計算用バッファサイズ
        performance_config = self.config.get("performance", {})
        self.hash_buffer_size = performance_config.get("hash_buffer_size", 65536)

    def _retry_operation(
        self,
        operation: Callable,
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        リトライ機構付きで操作を実行する。

        Args:
            operation: 実行する関数
            operation_name: 操作名（ログ用）
            *args, **kwargs: operationに渡す引数

        Returns:
            操作の戻り値

        Raises:
            RetryExhaustedError: リトライ回数超過
        """
        last_exception = None

        for attempt in range(self.retry_count + 1):
            try:
                return operation(*args, **kwargs)
            except self.RETRYABLE_EXCEPTIONS as e:
                last_exception = e
                if attempt < self.retry_count:
                    # Exponential backoff
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"{operation_name} 失敗 (試行 {attempt + 1}/{self.retry_count + 1}): {e}. "
                        f"{delay}秒後にリトライ..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"{operation_name} 失敗: リトライ回数超過")

        raise RetryExhaustedError(
            f"{operation_name} が {self.retry_count + 1} 回の試行後も失敗: {last_exception}"
        )

    def check_connection(self, path: Union[str, Path]) -> bool:
        """
        NASパスへの接続を確認する。

        Args:
            path: 確認するパス（ディレクトリまたはファイル）

        Returns:
            接続可能ならTrue
        """
        path = Path(path)

        try:
            if path.is_dir():
                # ディレクトリの場合はリスト取得を試みる
                list(path.iterdir())
                return True
            elif path.is_file():
                # ファイルの場合は存在確認
                return True
            else:
                # 存在しない場合はFalse
                return False
        except self.RETRYABLE_EXCEPTIONS as e:
            logger.warning(f"接続確認失敗: {path} - {e}")
            return False

    def check_connection_with_retry(self, path: Union[str, Path]) -> bool:
        """
        リトライ付きでNAS接続を確認する。

        Args:
            path: 確認するパス

        Returns:
            接続可能ならTrue
        """
        try:
            self._retry_operation(
                self._check_connection_internal,
                "接続確認",
                path
            )
            return True
        except RetryExhaustedError:
            return False

    def _check_connection_internal(self, path: Union[str, Path]) -> None:
        """内部用: 接続確認（例外を投げる）"""
        path = Path(path)
        if path.is_dir():
            list(path.iterdir())
        else:
            if not path.parent.exists():
                raise OSError(f"パスが存在しません: {path.parent}")

    def read_file(self, filepath: Union[str, Path]) -> bytes:
        """
        ファイルを読み取る（リトライ付き）。

        Args:
            filepath: ファイルパス

        Returns:
            ファイル内容（バイト列）

        Raises:
            RetryExhaustedError: リトライ回数超過
        """
        return self._retry_operation(
            self._read_file_internal,
            f"ファイル読み取り ({filepath})",
            filepath
        )

    def _read_file_internal(self, filepath: Union[str, Path]) -> bytes:
        """内部用: ファイル読み取り"""
        with open(filepath, "rb") as f:
            return f.read()

    def copy_file(
        self,
        src: Union[str, Path],
        dst: Union[str, Path],
        verify: bool = True
    ) -> Dict[str, Any]:
        """
        ファイルをコピーする（リトライ付き）。

        Args:
            src: コピー元パス
            dst: コピー先パス
            verify: コピー後にハッシュ検証するか

        Returns:
            結果辞書 {
                "success": bool,
                "src": str,
                "dst": str,
                "hash_verified": bool or None,
                "error": str or None
            }
        """
        src = Path(src)
        dst = Path(dst)

        result = {
            "success": False,
            "src": str(src),
            "dst": str(dst),
            "hash_verified": None,
            "error": None,
        }

        try:
            # コピー先ディレクトリを作成
            dst.parent.mkdir(parents=True, exist_ok=True)

            # コピー実行
            self._retry_operation(
                shutil.copy2,
                f"ファイルコピー ({src} -> {dst})",
                src,
                dst
            )

            result["success"] = True

            # ハッシュ検証
            if verify:
                src_hash = self.calculate_hash(src)
                dst_hash = self.calculate_hash(dst)

                if src_hash and dst_hash:
                    result["hash_verified"] = (src_hash == dst_hash)
                    if not result["hash_verified"]:
                        result["success"] = False
                        result["error"] = "ハッシュ検証失敗"
                        # 失敗したコピー先を削除
                        try:
                            dst.unlink()
                        except OSError:
                            pass
                else:
                    result["hash_verified"] = None
                    logger.warning(f"ハッシュ計算失敗: {src} or {dst}")

        except RetryExhaustedError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"コピーエラー: {src} -> {dst}: {e}")

        return result

    def delete_file(self, filepath: Union[str, Path]) -> Dict[str, Any]:
        """
        ファイルを削除する（リトライ付き）。

        Args:
            filepath: 削除するファイルパス

        Returns:
            結果辞書 {"success": bool, "filepath": str, "error": str or None}
        """
        filepath = Path(filepath)

        result = {
            "success": False,
            "filepath": str(filepath),
            "error": None,
        }

        # 既に存在しない場合は成功とみなす
        if not filepath.exists():
            result["success"] = True
            return result

        try:
            self._retry_operation(
                filepath.unlink,
                f"ファイル削除 ({filepath})"
            )
            result["success"] = True
        except RetryExhaustedError as e:
            result["error"] = str(e)
        except FileNotFoundError:
            # 削除中に消えた場合も成功とみなす
            result["success"] = True
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"削除エラー: {filepath}: {e}")

        return result

    def calculate_hash(self, filepath: Union[str, Path]) -> Optional[str]:
        """
        ファイルのSHA-256ハッシュを計算する（リトライ付き）。

        Args:
            filepath: ファイルパス

        Returns:
            ハッシュ値の16進数文字列（失敗時はNone）
        """
        try:
            return self._retry_operation(
                self._calculate_hash_internal,
                f"ハッシュ計算 ({filepath})",
                filepath
            )
        except RetryExhaustedError:
            return None

    def _calculate_hash_internal(self, filepath: Union[str, Path]) -> str:
        """内部用: ハッシュ計算"""
        sha256_hash = hashlib.sha256()

        with open(filepath, "rb") as f:
            while True:
                data = f.read(self.hash_buffer_size)
                if not data:
                    break
                sha256_hash.update(data)

        return sha256_hash.hexdigest()

    def get_file_size(self, filepath: Union[str, Path]) -> Optional[int]:
        """
        ファイルサイズを取得する。

        Args:
            filepath: ファイルパス

        Returns:
            ファイルサイズ（バイト）、失敗時はNone
        """
        try:
            return Path(filepath).stat().st_size
        except OSError as e:
            logger.warning(f"ファイルサイズ取得失敗: {filepath} - {e}")
            return None

    def list_files(
        self,
        directory: Union[str, Path],
        recursive: bool = True,
        extensions: Optional[List[str]] = None
    ) -> List[Path]:
        """
        ディレクトリ内のファイルをリストする。

        Args:
            directory: 対象ディレクトリ
            recursive: 再帰的に検索するか
            extensions: フィルタする拡張子リスト（小文字、ドット付き）

        Returns:
            ファイルパスのリスト
        """
        directory = Path(directory)
        files = []

        try:
            if recursive:
                iterator = directory.rglob("*")
            else:
                iterator = directory.glob("*")

            for path in iterator:
                if path.is_file():
                    if extensions is None:
                        files.append(path)
                    elif path.suffix.lower() in extensions:
                        files.append(path)

        except OSError as e:
            logger.error(f"ディレクトリ読み取りエラー: {directory} - {e}")

        return files


# =============================================================================
# バッチ処理ヘルパー
# =============================================================================

class BatchProcessor:
    """
    バッチ処理を管理するクラス。
    定期的な接続確認とチェックポイント保存をサポート。
    """

    def __init__(
        self,
        handler: NASFileHandler,
        batch_size: int = 50,
        connection_check_interval: int = 250,
        checkpoint_callback: Optional[Callable[[int], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        """
        Args:
            handler: NASFileHandlerインスタンス
            batch_size: バッチサイズ
            connection_check_interval: 接続確認間隔（ファイル数）
            checkpoint_callback: チェックポイント保存コールバック（引数: 処理済み数）
            progress_callback: 進捗コールバック（引数: 処理済み数, 総数）
        """
        self.handler = handler
        self.batch_size = batch_size
        self.connection_check_interval = connection_check_interval
        self.checkpoint_callback = checkpoint_callback
        self.progress_callback = progress_callback

        self._processed_count = 0
        self._last_connection_check = 0

    def process_files(
        self,
        files: List[Path],
        operation: Callable[[Path], Dict[str, Any]],
        connection_check_path: Optional[Union[str, Path]] = None
    ) -> List[Dict[str, Any]]:
        """
        ファイルリストをバッチ処理する。

        Args:
            files: 処理するファイルリスト
            operation: 各ファイルに適用する操作（戻り値は結果辞書）
            connection_check_path: 接続確認用パス

        Returns:
            各ファイルの処理結果リスト
        """
        results = []
        total = len(files)

        for i, filepath in enumerate(files):
            # 接続確認
            if connection_check_path and self._should_check_connection():
                if not self.handler.check_connection_with_retry(connection_check_path):
                    logger.error("NAS接続が失われました。処理を中断します。")
                    break

            # 操作実行
            try:
                result = operation(filepath)
                results.append(result)
            except Exception as e:
                results.append({
                    "filepath": str(filepath),
                    "success": False,
                    "error": str(e)
                })
                logger.error(f"処理エラー: {filepath} - {e}")

            self._processed_count += 1

            # 進捗コールバック
            if self.progress_callback:
                self.progress_callback(self._processed_count, total)

            # チェックポイント（バッチ単位）
            if self._processed_count % self.batch_size == 0:
                if self.checkpoint_callback:
                    self.checkpoint_callback(self._processed_count)

        # 最終チェックポイント
        if self.checkpoint_callback and self._processed_count % self.batch_size != 0:
            self.checkpoint_callback(self._processed_count)

        return results

    def _should_check_connection(self) -> bool:
        """接続確認が必要かどうかを判定する。"""
        if self._processed_count - self._last_connection_check >= self.connection_check_interval:
            self._last_connection_check = self._processed_count
            return True
        return False

    def reset(self) -> None:
        """カウンターをリセットする。"""
        self._processed_count = 0
        self._last_connection_check = 0
