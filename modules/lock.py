"""
ロック管理モジュール

二重起動防止、ロックファイル管理を担当。
複数PCからの同時実行を防止する。
"""

import json
import logging
import socket
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)


# =============================================================================
# 例外クラス
# =============================================================================

class LockError(Exception):
    """ロック関連のエラー"""
    pass


class LockExistsError(LockError):
    """ロックが既に存在するエラー"""
    def __init__(self, lock_info: Dict[str, Any], message: str = ""):
        self.lock_info = lock_info
        super().__init__(message or self._format_message())

    def _format_message(self) -> str:
        """エラーメッセージをフォーマットする。"""
        info = self.lock_info
        return (
            f"既に処理が実行中、または前回異常終了した可能性があります\n\n"
            f"ロックファイル情報:\n"
            f"  開始時刻: {info.get('started_at', '不明')}\n"
            f"  実行PC: {info.get('pc_name', '不明')}\n"
            f"  フェーズ: {info.get('current_phase', '不明')}\n\n"
            f"【対処方法】\n"
            f"1. 他のPCやプロセスで実行していないか確認\n"
            f"2. 実行していない場合は、ロックファイルを手動削除してください\n"
            f"3. 再度このプログラムを実行してください"
        )


# =============================================================================
# ロックマネージャー
# =============================================================================

class LockManager:
    """
    ロックファイルを管理するクラス。
    organized/ ディレクトリに .photo-organizer.lock を作成して二重起動を防止。
    """

    LOCK_FILENAME = ".photo-organizer.lock"

    def __init__(self, organized_dir: Union[str, Path], config: Optional[Dict[str, Any]] = None):
        """
        Args:
            organized_dir: organized/ ディレクトリのパス
            config: 設定辞書（lockセクションを参照）
        """
        self.organized_dir = Path(organized_dir)
        self.lock_path = self.organized_dir / self.LOCK_FILENAME

        self.config = config or {}
        lock_config = self.config.get("lock", {})
        self.auto_delete_hours = lock_config.get("auto_delete_hours", 24)

        self._lock_acquired = False
        self._lock_info: Dict[str, Any] = {}

    def acquire(self, force: bool = False) -> bool:
        """
        ロックを取得する。

        Args:
            force: 既存のロックを強制的に上書きするか

        Returns:
            ロック取得成功ならTrue

        Raises:
            LockExistsError: ロックが既に存在し、forceがFalseの場合
        """
        # 既存ロックのチェック
        existing = self.check_existing_lock()

        if existing:
            if force:
                logger.warning("既存のロックを強制的に上書きします")
                self.release(force=True)
            else:
                raise LockExistsError(existing)

        # ロックファイル作成
        self._lock_info = {
            "started_at": datetime.now().isoformat(),
            "pc_name": self._get_pc_name(),
            "current_phase": "initializing",
        }

        try:
            # organized/ ディレクトリを作成（存在しない場合）
            self.organized_dir.mkdir(parents=True, exist_ok=True)

            with open(self.lock_path, "w", encoding="utf-8") as f:
                json.dump(self._lock_info, f, ensure_ascii=False, indent=2)

            self._lock_acquired = True
            logger.info(f"ロックを取得しました: {self.lock_path}")
            return True

        except OSError as e:
            logger.error(f"ロックファイル作成エラー: {e}")
            return False

    def release(self, force: bool = False) -> bool:
        """
        ロックを解放する。

        Args:
            force: 自身が取得していないロックも解放するか

        Returns:
            解放成功ならTrue
        """
        if not self._lock_acquired and not force:
            logger.warning("ロックを取得していないため、解放できません")
            return False

        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
                logger.info(f"ロックを解放しました: {self.lock_path}")

            self._lock_acquired = False
            self._lock_info = {}
            return True

        except OSError as e:
            logger.error(f"ロックファイル削除エラー: {e}")
            return False

    def update_phase(self, phase: str) -> bool:
        """
        現在のフェーズを更新する。

        Args:
            phase: 新しいフェーズ名

        Returns:
            更新成功ならTrue
        """
        if not self._lock_acquired:
            logger.warning("ロックを取得していないため、フェーズを更新できません")
            return False

        self._lock_info["current_phase"] = phase
        self._lock_info["updated_at"] = datetime.now().isoformat()

        try:
            with open(self.lock_path, "w", encoding="utf-8") as f:
                json.dump(self._lock_info, f, ensure_ascii=False, indent=2)
            logger.debug(f"フェーズを更新: {phase}")
            return True

        except OSError as e:
            logger.error(f"ロックファイル更新エラー: {e}")
            return False

    def check_existing_lock(self) -> Optional[Dict[str, Any]]:
        """
        既存のロックファイルをチェックする。

        Returns:
            ロック情報辞書（存在しない場合はNone）
        """
        if not self.lock_path.exists():
            return None

        try:
            with open(self.lock_path, "r", encoding="utf-8") as f:
                lock_info = json.load(f)
            return lock_info

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"ロックファイル読み取りエラー: {e}")
            # 破損したロックファイルとして情報を返す
            return {
                "started_at": "不明（ファイル破損）",
                "pc_name": "不明",
                "current_phase": "不明",
            }

    def is_old_lock(self, hours: Optional[int] = None) -> bool:
        """
        既存のロックが古い（指定時間以上前）かどうかを判定する。

        Args:
            hours: 判定基準の時間（デフォルトはauto_delete_hours）

        Returns:
            古いロックならTrue、ロックがない場合もFalse
        """
        if hours is None:
            hours = self.auto_delete_hours

        lock_info = self.check_existing_lock()
        if not lock_info:
            return False

        started_at_str = lock_info.get("started_at")
        if not started_at_str or started_at_str.startswith("不明"):
            # 開始時刻が不明な場合は古いとみなす
            return True

        try:
            started_at = datetime.fromisoformat(started_at_str)
            age = datetime.now() - started_at
            return age > timedelta(hours=hours)

        except ValueError:
            # パースできない場合は古いとみなす
            return True

    def is_same_pc(self) -> bool:
        """
        既存のロックが同じPCから取得されたものかを判定する。

        Returns:
            同じPCならTrue
        """
        lock_info = self.check_existing_lock()
        if not lock_info:
            return False

        return lock_info.get("pc_name") == self._get_pc_name()

    def get_lock_info(self) -> Dict[str, Any]:
        """
        現在のロック情報を取得する。

        Returns:
            ロック情報辞書
        """
        if self._lock_acquired:
            return self._lock_info.copy()
        return self.check_existing_lock() or {}

    def get_lock_age_hours(self) -> Optional[float]:
        """
        ロックの経過時間を取得する。

        Returns:
            経過時間（時間単位）、ロックがない場合はNone
        """
        lock_info = self.check_existing_lock()
        if not lock_info:
            return None

        started_at_str = lock_info.get("started_at")
        if not started_at_str or started_at_str.startswith("不明"):
            return None

        try:
            started_at = datetime.fromisoformat(started_at_str)
            age = datetime.now() - started_at
            return age.total_seconds() / 3600

        except ValueError:
            return None

    def _get_pc_name(self) -> str:
        """PC名を取得する。"""
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"

    def __enter__(self) -> "LockManager":
        """コンテキストマネージャー: ロック取得"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """コンテキストマネージャー: ロック解放"""
        self.release()


# =============================================================================
# ユーザー対話ヘルパー
# =============================================================================

def prompt_lock_action(lock_manager: LockManager) -> str:
    """
    ロックが存在する場合のユーザーアクションを取得する。

    Args:
        lock_manager: LockManagerインスタンス

    Returns:
        ユーザーの選択: "force", "cancel", "wait"
    """
    lock_info = lock_manager.get_lock_info()
    is_old = lock_manager.is_old_lock()
    is_same_pc = lock_manager.is_same_pc()
    age_hours = lock_manager.get_lock_age_hours()

    print("\n" + "=" * 60)
    print("⚠️  ロックファイルが存在します")
    print("=" * 60)
    print(f"\n開始時刻: {lock_info.get('started_at', '不明')}")
    print(f"実行PC: {lock_info.get('pc_name', '不明')}")
    print(f"フェーズ: {lock_info.get('current_phase', '不明')}")

    if age_hours is not None:
        print(f"経過時間: {age_hours:.1f} 時間")

    if is_old:
        print(f"\n⚡ このロックは {lock_manager.auto_delete_hours} 時間以上前のものです。")

    if is_same_pc:
        print("💻 このロックは同じPCから取得されたものです。")

    print("\n選択してください:")
    print("  [1] ロックを削除して続行")
    print("  [2] キャンセル（終了）")

    while True:
        choice = input("\n選択 (1/2): ").strip()
        if choice == "1":
            return "force"
        elif choice == "2":
            return "cancel"
        else:
            print("1 または 2 を入力してください。")


def format_lock_error_message(lock_info: Dict[str, Any], lock_path: Path) -> str:
    """
    ロックエラーメッセージをフォーマットする。

    Args:
        lock_info: ロック情報辞書
        lock_path: ロックファイルのパス

    Returns:
        フォーマットされたエラーメッセージ
    """
    return (
        f"\n{'=' * 60}\n"
        f"❌ エラー: 既に処理が実行中、または前回異常終了した可能性があります\n"
        f"{'=' * 60}\n\n"
        f"ロックファイル: {lock_path}\n"
        f"開始時刻: {lock_info.get('started_at', '不明')}\n"
        f"実行PC: {lock_info.get('pc_name', '不明')}\n"
        f"フェーズ: {lock_info.get('current_phase', '不明')}\n\n"
        f"【対処方法】\n"
        f"1. 他のPCやプロセスで実行していないか確認\n"
        f"2. 実行していない場合は、上記ロックファイルを手動削除してください\n"
        f"3. 再度このプログラムを実行してください\n"
    )
