#!/usr/bin/env python3
"""
NAS写真・動画整理ツール

家族でスマホ等で撮った写真・動画をNASに保存し、
撮影日時ベースで体系的に整理するツール。

Usage:
    python organize.py [--config CONFIG_PATH]
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from modules.utils import load_config, setup_logging
from modules.lock import LockManager, LockExistsError, prompt_lock_action, format_lock_error_message
from modules.scanner import PhotoScanner, print_metadata_summary, print_hash_summary, print_analysis_summary
from modules.planner import FilePlanner, print_plan_summary
from modules.organizer import FileOrganizer, print_organize_summary, confirm_organize
from modules.cleaner import (
    FileCleaner,
    print_cleanup_originals_summary,
    print_cleanup_duplicates_summary,
    confirm_cleanup_originals,
    confirm_cleanup_duplicates,
)

__version__ = "1.0.0"

logger = logging.getLogger(__name__)


# =============================================================================
# ユーティリティ
# =============================================================================

def print_header():
    """ヘッダーを表示する。"""
    print("\n" + "=" * 60)
    print("📷 NAS写真・動画整理ツール v{}".format(__version__))
    print("=" * 60)


def print_phase_header(phase: str, title: str):
    """フェーズヘッダーを表示する。"""
    print("\n" + "=" * 60)
    print(f"🔹 {phase}: {title}")
    print("=" * 60)


def confirm_continue(message: str = "続行しますか？") -> bool:
    """続行確認を取る。"""
    while True:
        answer = input(f"\n{message} [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        elif answer in ("n", "no"):
            return False
        else:
            print("y または n を入力してください。")


def confirm_skip_to_phase() -> Optional[str]:
    """スキップするフェーズを選択する。"""
    print("\n" + "-" * 60)
    print("スキップオプション:")
    print("  [1] Phase 1a から開始（通常）")
    print("  [2] Phase 1b から開始（メタデータスキャン済み）")
    print("  [3] Phase 1c から開始（ハッシュ計算済み）")
    print("  [4] Phase 2 から開始（分析済み）")
    print("  [5] Phase 3 から開始（計画作成済み）")
    print("  [6] Phase 5a から開始（整理実行済み・削除フェーズ）")
    print("  [7] Phase 5b から開始（重複削除のみ）")
    print("  [0] キャンセル")
    print("-" * 60)

    while True:
        choice = input("\n選択 [0-7]: ").strip()
        if choice == "0":
            return None
        elif choice == "1":
            return "1a"
        elif choice == "2":
            return "1b"
        elif choice == "3":
            return "1c"
        elif choice == "4":
            return "2"
        elif choice == "5":
            return "3"
        elif choice == "6":
            return "5a"
        elif choice == "7":
            return "5b"
        else:
            print("0-7 の数字を入力してください。")


# =============================================================================
# メインフロー
# =============================================================================

class PhotoOrganizer:
    """
    写真・動画整理の対話モードを制御するクラス。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: 設定辞書
        """
        self.config = config
        self.paths = config.get("paths", {})
        self.organized_dir = Path(self.paths.get("organized_dir", ""))

        # モジュール初期化
        self.lock_manager = LockManager(self.organized_dir, config)
        self.scanner = PhotoScanner(config)
        self.planner = FilePlanner(config)
        self.organizer = FileOrganizer(config)
        self.cleaner = FileCleaner(config)

        # レポートキャッシュ
        self.metadata_report = None
        self.existing_files = None
        self.hash_report = None
        self.analysis_report = None
        self.plan = None
        self.organize_log = None

    def run(self, start_phase: Optional[str] = None):
        """
        対話モードを実行する。

        Args:
            start_phase: 開始フェーズ（Noneなら最初から）
        """
        print_header()

        # 設定確認
        print(f"\nソース: {self.paths.get('source_dir')}")
        print(f"整理先: {self.paths.get('organized_dir')}")
        print(f"作業場所: {self.paths.get('workspace_dir')}")

        if not confirm_continue("この設定で開始しますか？"):
            print("\nキャンセルしました。")
            return

        # 開始フェーズの選択
        if start_phase is None:
            print("\n前回の続きから再開しますか？")
            if confirm_continue("フェーズを選択しますか？（Nで最初から）"):
                start_phase = confirm_skip_to_phase()
                if start_phase is None:
                    print("\nキャンセルしました。")
                    return

        # ロック取得
        try:
            self._acquire_lock()
        except LockExistsError as e:
            print(format_lock_error_message(e.lock_info, self.lock_manager.lock_path))
            action = prompt_lock_action(self.lock_manager)
            if action == "force":
                self._acquire_lock(force=True)
            else:
                print("\nキャンセルしました。")
                return

        try:
            # フェーズ実行
            if start_phase is None or start_phase == "1a":
                if not self._run_phase_1a():
                    return
                start_phase = "1b"

            if start_phase == "1b":
                if not self._run_phase_1b():
                    return
                start_phase = "1c"

            if start_phase == "1c":
                if not self._run_phase_1c():
                    return
                start_phase = "2"

            if start_phase == "2":
                if not self._run_phase_2():
                    return
                start_phase = "3"

            if start_phase == "3":
                if not self._run_phase_3():
                    return
                start_phase = "4"

            if start_phase == "4":
                self._run_phase_4()
                return  # Phase 4 で一旦終了

            if start_phase == "5a":
                if not self._run_phase_5a():
                    return
                start_phase = "5b"

            if start_phase == "5b":
                self._run_phase_5b()

            # 完了
            print("\n" + "=" * 60)
            print("✅ すべての処理が完了しました！")
            print("=" * 60)

        finally:
            self._release_lock()

    def _acquire_lock(self, force: bool = False):
        """ロックを取得する。"""
        self.lock_manager.acquire(force=force)
        logger.info("ロックを取得しました")

    def _release_lock(self):
        """ロックを解放する。"""
        if self.lock_manager._lock_acquired:
            self.lock_manager.release()
            logger.info("ロックを解放しました")

    # =========================================================================
    # Phase 1a: メタデータスキャン
    # =========================================================================

    def _run_phase_1a(self) -> bool:
        """Phase 1a を実行する。"""
        print_phase_header("Phase 1a", "メタデータスキャン")
        self.lock_manager.update_phase("phase1a_metadata")

        print("\nsource/ と organized/ をスキャンしてメタデータを抽出します。")

        if not confirm_continue("Phase 1a を実行しますか？"):
            return False

        try:
            self.metadata_report = self.scanner.scan_metadata()
            print_metadata_summary(self.metadata_report)

            # 既存ファイル情報も読み込み
            self.existing_files = self.scanner._load_report("existing_files.json")

            return confirm_continue("Phase 1b に進みますか？")

        except Exception as e:
            logger.exception(f"Phase 1a エラー: {e}")
            print(f"\n❌ エラーが発生しました: {e}")
            return False

    # =========================================================================
    # Phase 1b: ハッシュ計算
    # =========================================================================

    def _run_phase_1b(self) -> bool:
        """Phase 1b を実行する。"""
        print_phase_header("Phase 1b", "ハッシュ計算")
        self.lock_manager.update_phase("phase1b_hash")

        print("\n重複検出のためにハッシュ計算を行います。")
        print("サイズベースの最適化により、必要なファイルのみ計算します。")

        if not confirm_continue("Phase 1b を実行しますか？"):
            return False

        try:
            self.hash_report = self.scanner.scan_hash(
                self.metadata_report,
                self.existing_files
            )
            print_hash_summary(self.hash_report)

            return confirm_continue("Phase 1c に進みますか？")

        except Exception as e:
            logger.exception(f"Phase 1b エラー: {e}")
            print(f"\n❌ エラーが発生しました: {e}")
            return False

    # =========================================================================
    # Phase 1c: 分析
    # =========================================================================

    def _run_phase_1c(self) -> bool:
        """Phase 1c を実行する。"""
        print_phase_header("Phase 1c", "分析")
        self.lock_manager.update_phase("phase1c_analysis")

        print("\nメタデータとハッシュを統合し、重複を検出します。")

        if not confirm_continue("Phase 1c を実行しますか？"):
            return False

        try:
            self.analysis_report = self.scanner.analyze(
                self.metadata_report,
                self.hash_report,
                self.existing_files
            )
            print_analysis_summary(self.analysis_report)

            return confirm_continue("Phase 2 に進みますか？")

        except Exception as e:
            logger.exception(f"Phase 1c エラー: {e}")
            print(f"\n❌ エラーが発生しました: {e}")
            return False

    # =========================================================================
    # Phase 2: 整理計画
    # =========================================================================

    def _run_phase_2(self) -> bool:
        """Phase 2 を実行する。"""
        print_phase_header("Phase 2", "整理計画（Dry-run）")
        self.lock_manager.update_phase("phase2_plan")

        print("\n整理計画を作成します。実際のファイル操作は行いません。")

        if not confirm_continue("Phase 2 を実行しますか？"):
            return False

        try:
            self.plan = self.planner.create_plan(
                self.analysis_report,
                self.existing_files
            )
            print_plan_summary(self.plan)

            # ディスク容量チェック
            disk_check = self.plan.get("disk_check", {})
            if disk_check.get("sufficient") is False:
                print("\n❌ ディスク容量が不足しています。")
                print("容量を確保してから再実行してください。")
                return False

            return confirm_continue("Phase 3（整理実行）に進みますか？")

        except Exception as e:
            logger.exception(f"Phase 2 エラー: {e}")
            print(f"\n❌ エラーが発生しました: {e}")
            return False

    # =========================================================================
    # Phase 3: 整理実行
    # =========================================================================

    def _run_phase_3(self) -> bool:
        """Phase 3 を実行する。"""
        print_phase_header("Phase 3", "整理実行")
        self.lock_manager.update_phase("phase3_organize")

        print("\n整理計画に従ってファイルをコピーします。")
        print("オリジナルファイルはまだ削除されません。")

        if not confirm_organize():
            return False

        try:
            self.organize_log = self.organizer.organize(self.plan)
            print_organize_summary(self.organize_log)

            # 失敗があれば警告
            if self.organize_log.get("failed", 0) > 0:
                print("\n⚠️  一部のファイルでエラーが発生しました。")
                print("reports/failed.txt を確認してください。")

            return confirm_continue("Phase 4（確認期間）に進みますか？")

        except Exception as e:
            logger.exception(f"Phase 3 エラー: {e}")
            print(f"\n❌ エラーが発生しました: {e}")
            return False

    # =========================================================================
    # Phase 4: 確認期間
    # =========================================================================

    def _run_phase_4(self):
        """Phase 4 の説明を表示する。"""
        print_phase_header("Phase 4", "確認期間")
        self.lock_manager.update_phase("phase4_confirmation")

        print("\n" + "-" * 60)
        print("📋 ユーザー確認のお願い")
        print("-" * 60)
        print("""
organized/ フォルダを確認してください：

1. ファイルが正しくコピーされているか
2. 日付順に整理されているか
3. ランダムにファイルを開いて確認

確認が終わったら、このプログラムを再実行して
Phase 5a（オリジナル削除）に進んでください。

コマンド例:
  python organize.py

フェーズ選択で [6] を選ぶと Phase 5a から再開できます。
""")
        print("-" * 60)
        print("\n⏸️  プログラムを終了します。確認後に再実行してください。")

    # =========================================================================
    # Phase 5a: オリジナル削除
    # =========================================================================

    def _run_phase_5a(self) -> bool:
        """Phase 5a を実行する。"""
        print_phase_header("Phase 5a", "オリジナル削除")
        self.lock_manager.update_phase("phase5a_cleanup")

        print("\n整理が成功したオリジナルファイルを削除します。")

        # 削除対象の確認
        try:
            organize_log = self.organizer._load_report("organize_log.json")
            success_count = sum(
                1 for op in organize_log.get("operations", [])
                if op.get("status") == "success" and op.get("hash_verified") is True
            )

            if success_count == 0:
                print("\n削除対象のファイルがありません。")
                return confirm_continue("Phase 5b に進みますか？")

            if not confirm_cleanup_originals(success_count):
                return confirm_continue("Phase 5b に進みますか？")

            cleanup_log = self.cleaner.cleanup_originals(organize_log)
            print_cleanup_originals_summary(cleanup_log)

            return confirm_continue("Phase 5b（重複削除）に進みますか？")

        except FileNotFoundError:
            print("\n❌ organize_log.json が見つかりません。")
            print("Phase 3 を先に実行してください。")
            return False
        except Exception as e:
            logger.exception(f"Phase 5a エラー: {e}")
            print(f"\n❌ エラーが発生しました: {e}")
            return False

    # =========================================================================
    # Phase 5b: 重複削除
    # =========================================================================

    def _run_phase_5b(self):
        """Phase 5b を実行する。"""
        print_phase_header("Phase 5b", "重複削除（オプション）")
        self.lock_manager.update_phase("phase5b_duplicates")

        print("\nsource/ 内の重複ファイルを削除できます。")

        try:
            analysis_report = self.scanner._load_report("analysis_report.json")
            duplicates = analysis_report.get("duplicates", {})
            source_internal = duplicates.get("source_internal", [])

            if not source_internal:
                print("\nsource/ 内に重複ファイルはありません。")
                return

            print(f"\n重複グループ: {len(source_internal)}グループ")

            print("\n選択してください:")
            print("  [1] 対話的に選択（各グループで残すファイルを選ぶ）")
            print("  [2] 自動選択（最初のファイルを残す）")
            print("  [3] スキップ（重複削除しない）")

            while True:
                choice = input("\n選択 [1/2/3]: ").strip()
                if choice == "1":
                    # 対話的選択
                    delete_targets = self.cleaner.select_duplicates_interactive(source_internal)
                    if delete_targets:
                        if confirm_cleanup_duplicates(len(delete_targets)):
                            cleanup_log = self.cleaner.execute_duplicate_deletion(delete_targets)
                            print_cleanup_duplicates_summary(cleanup_log)
                    else:
                        print("\n削除対象がありません。")
                    break
                elif choice == "2":
                    # 自動選択
                    cleanup_log = self.cleaner.cleanup_duplicates(
                        analysis_report,
                        auto_select=True
                    )
                    if cleanup_log.get("total_targets", 0) > 0:
                        print_cleanup_duplicates_summary(cleanup_log)
                    else:
                        print("\n削除対象がありません。")
                    break
                elif choice == "3":
                    print("\n重複削除をスキップしました。")
                    break
                else:
                    print("1, 2, または 3 を入力してください。")

        except FileNotFoundError:
            print("\n❌ analysis_report.json が見つかりません。")
            print("Phase 1c を先に実行してください。")
        except Exception as e:
            logger.exception(f"Phase 5b エラー: {e}")
            print(f"\n❌ エラーが発生しました: {e}")


# =============================================================================
# エントリーポイント
# =============================================================================

def main():
    """メイン関数。"""
    parser = argparse.ArgumentParser(
        description="NAS写真・動画整理ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", "-c",
        default="config.json",
        help="設定ファイルのパス（デフォルト: config.json）"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    args = parser.parse_args()

    # 設定読み込み
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"❌ 設定ファイルが見つかりません: {args.config}")
        print("\nconfig.json.sample を config.json にコピーして編集してください:")
        print("  cp config.json.sample config.json")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 設定ファイルの読み込みエラー: {e}")
        sys.exit(1)

    # ログ設定
    setup_logging(config)

    # 実行
    try:
        app = PhotoOrganizer(config)
        app.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  中断されました。")
        print("次回実行時に続きから再開できます。")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"予期しないエラー: {e}")
        print(f"\n❌ 予期しないエラーが発生しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
