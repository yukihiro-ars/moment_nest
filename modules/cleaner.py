"""
クリーンアップモジュール

ファイル削除（オリジナル削除、重複削除）を担当。
Phase 5a, 5b の処理を実装。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

from .network import NASFileHandler
from .utils import format_file_size, format_duration

logger = logging.getLogger(__name__)


# =============================================================================
# FileCleaner クラス
# =============================================================================

class FileCleaner:
    """
    ファイル削除を行うクラス。
    Phase 5a（オリジナル削除）、Phase 5b（重複削除）を担当。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: 設定辞書
        """
        self.config = config
        self.paths = config.get("paths", {})
        self.source_dir = Path(self.paths.get("source_dir", ""))
        self.organized_dir = Path(self.paths.get("organized_dir", ""))
        self.workspace_dir = Path(self.paths.get("workspace_dir", "."))

        self.reports_dir = self.workspace_dir / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # ネットワークハンドラー
        self.file_handler = NASFileHandler(config)

    # =========================================================================
    # Phase 5a: オリジナル削除
    # =========================================================================

    def cleanup_originals(
        self,
        organize_log: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Phase 5a: 整理済みのオリジナルファイルを削除する。

        Args:
            organize_log: 整理ログ（Noneなら読み込み）
            progress_callback: 進捗コールバック

        Returns:
            削除ログ辞書
        """
        logger.info("Phase 5a: オリジナル削除開始")
        start_time = datetime.now()

        # ログ読み込み
        if organize_log is None:
            organize_log = self._load_report("organize_log.json")

        operations = organize_log.get("operations", [])

        # 削除対象をフィルタリング
        # status="success" かつ hash_verified=true のファイルのみ
        delete_targets = []
        skipped = []

        for op in operations:
            original = op.get("original")
            if not original:
                continue

            if op.get("status") == "success" and op.get("hash_verified") is True:
                # ファイルが存在するか確認
                if Path(original).exists():
                    delete_targets.append({
                        "path": original,
                        "new_path": op.get("new"),
                    })
                else:
                    skipped.append({
                        "path": original,
                        "reason": "already_deleted",
                    })
            else:
                skipped.append({
                    "path": original,
                    "reason": f"status={op.get('status')}, hash_verified={op.get('hash_verified')}",
                })

        logger.info(f"  削除対象: {len(delete_targets)}ファイル")
        logger.info(f"  スキップ: {len(skipped)}ファイル")

        if not delete_targets:
            logger.info("削除対象ファイルがありません")
            return self._create_cleanup_log([], skipped, start_time, "phase5a")

        # 削除実行
        delete_results = []
        success_count = 0
        failed_count = 0

        for i, target in enumerate(delete_targets):
            filepath = target["path"]

            result = self.file_handler.delete_file(filepath)

            delete_result = {
                "path": filepath,
                "new_path": target["new_path"],
                "success": result["success"],
                "error": result.get("error"),
                "deleted_at": datetime.now().isoformat() if result["success"] else None,
            }

            delete_results.append(delete_result)

            if result["success"]:
                success_count += 1
            else:
                failed_count += 1

            if progress_callback:
                progress_callback(i + 1, len(delete_targets))

        # ログ作成
        cleanup_log = self._create_cleanup_log(
            delete_results, skipped, start_time, "phase5a"
        )
        cleanup_log["success"] = success_count
        cleanup_log["failed"] = failed_count

        # レポート保存
        self._save_report("cleanup_originals_log.json", cleanup_log)

        logger.info(
            f"Phase 5a 完了: 成功 {success_count}, 失敗 {failed_count}, "
            f"{format_duration(cleanup_log['elapsed_seconds'])}"
        )

        return cleanup_log

    # =========================================================================
    # Phase 5b: 重複削除
    # =========================================================================

    def cleanup_duplicates(
        self,
        analysis_report: Optional[Dict[str, Any]] = None,
        auto_select: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Phase 5b: source/内の重複ファイルを削除する。

        Args:
            analysis_report: 分析レポート（Noneなら読み込み）
            auto_select: 自動選択モード（最初のファイルを残す）
            progress_callback: 進捗コールバック

        Returns:
            削除ログ辞書
        """
        logger.info("Phase 5b: 重複削除開始")
        start_time = datetime.now()

        # レポート読み込み
        if analysis_report is None:
            analysis_report = self._load_report("analysis_report.json")

        duplicates = analysis_report.get("duplicates", {})
        source_internal = duplicates.get("source_internal", [])

        if not source_internal:
            logger.info("source/内の重複ファイルはありません")
            return self._create_cleanup_log([], [], start_time, "phase5b")

        logger.info(f"  重複グループ: {len(source_internal)}グループ")

        # 削除対象を決定
        delete_targets = []
        kept_files = []

        for group in source_internal:
            files = group.get("files", [])
            if len(files) < 2:
                continue

            if auto_select:
                # 最初のファイルを残し、残りを削除
                kept_files.append(files[0])
                for filepath in files[1:]:
                    if Path(filepath).exists():
                        delete_targets.append({
                            "path": filepath,
                            "kept": files[0],
                            "hash": group.get("hash"),
                        })
            else:
                # ユーザー選択が必要（この関数では処理しない）
                # 対話モードで別途処理
                pass

        if not auto_select:
            # 対話モードでの選択が必要
            return {
                "phase": "phase5b",
                "requires_interaction": True,
                "duplicate_groups": source_internal,
                "total_groups": len(source_internal),
            }

        logger.info(f"  削除対象: {len(delete_targets)}ファイル")
        logger.info(f"  保持: {len(kept_files)}ファイル")

        # 削除実行
        delete_results = []
        success_count = 0
        failed_count = 0

        for i, target in enumerate(delete_targets):
            filepath = target["path"]

            result = self.file_handler.delete_file(filepath)

            delete_result = {
                "path": filepath,
                "kept": target["kept"],
                "hash": target["hash"],
                "success": result["success"],
                "error": result.get("error"),
                "deleted_at": datetime.now().isoformat() if result["success"] else None,
            }

            delete_results.append(delete_result)

            if result["success"]:
                success_count += 1
            else:
                failed_count += 1

            if progress_callback:
                progress_callback(i + 1, len(delete_targets))

        # ログ作成
        cleanup_log = self._create_cleanup_log(
            delete_results, [], start_time, "phase5b"
        )
        cleanup_log["success"] = success_count
        cleanup_log["failed"] = failed_count
        cleanup_log["kept_files"] = kept_files

        # レポート保存
        self._save_report("cleanup_duplicates_log.json", cleanup_log)

        logger.info(
            f"Phase 5b 完了: 成功 {success_count}, 失敗 {failed_count}, "
            f"{format_duration(cleanup_log['elapsed_seconds'])}"
        )

        return cleanup_log

    def select_duplicates_interactive(
        self,
        duplicate_groups: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        対話的に重複ファイルの削除対象を選択する。

        Args:
            duplicate_groups: 重複グループリスト

        Returns:
            削除対象リスト
        """
        delete_targets = []

        print("\n" + "=" * 60)
        print("🗑️  重複ファイルの選択")
        print("=" * 60)
        print("\n各グループで残すファイルを選択してください。")
        print("選択されなかったファイルが削除対象になります。\n")

        for i, group in enumerate(duplicate_groups):
            files = group.get("files", [])
            if len(files) < 2:
                continue

            print(f"\n[グループ {i + 1}/{len(duplicate_groups)}]")
            print(f"ハッシュ: {group.get('hash', '?')[:16]}...")
            print("-" * 40)

            for j, filepath in enumerate(files):
                size = self._get_file_size(filepath)
                print(f"  [{j + 1}] {filepath}")
                print(f"      サイズ: {format_file_size(size)}")

            print(f"  [0] すべて残す（削除しない）")
            print(f"  [a] 最初のファイルを残す（自動）")

            while True:
                choice = input("\n残すファイル番号を選択 [1-{}/0/a]: ".format(len(files))).strip().lower()

                if choice == "0":
                    # すべて残す
                    print("  → このグループはスキップします")
                    break
                elif choice == "a":
                    # 最初を残す
                    kept = files[0]
                    for filepath in files[1:]:
                        if Path(filepath).exists():
                            delete_targets.append({
                                "path": filepath,
                                "kept": kept,
                                "hash": group.get("hash"),
                            })
                    print(f"  → {files[0]} を残します")
                    break
                elif choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(files):
                        kept = files[idx]
                        for j, filepath in enumerate(files):
                            if j != idx and Path(filepath).exists():
                                delete_targets.append({
                                    "path": filepath,
                                    "kept": kept,
                                    "hash": group.get("hash"),
                                })
                        print(f"  → {kept} を残します")
                        break
                    else:
                        print("無効な番号です。")
                else:
                    print("1-{}, 0, または a を入力してください。".format(len(files)))

        return delete_targets

    def execute_duplicate_deletion(
        self,
        delete_targets: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        選択された重複ファイルを削除する。

        Args:
            delete_targets: 削除対象リスト
            progress_callback: 進捗コールバック

        Returns:
            削除ログ辞書
        """
        start_time = datetime.now()

        if not delete_targets:
            logger.info("削除対象がありません")
            return self._create_cleanup_log([], [], start_time, "phase5b")

        delete_results = []
        success_count = 0
        failed_count = 0

        for i, target in enumerate(delete_targets):
            filepath = target["path"]

            result = self.file_handler.delete_file(filepath)

            delete_result = {
                "path": filepath,
                "kept": target.get("kept"),
                "hash": target.get("hash"),
                "success": result["success"],
                "error": result.get("error"),
                "deleted_at": datetime.now().isoformat() if result["success"] else None,
            }

            delete_results.append(delete_result)

            if result["success"]:
                success_count += 1
            else:
                failed_count += 1

            if progress_callback:
                progress_callback(i + 1, len(delete_targets))

        # ログ作成
        cleanup_log = self._create_cleanup_log(
            delete_results, [], start_time, "phase5b"
        )
        cleanup_log["success"] = success_count
        cleanup_log["failed"] = failed_count

        # レポート保存
        self._save_report("cleanup_duplicates_log.json", cleanup_log)

        return cleanup_log

    # =========================================================================
    # ユーティリティ
    # =========================================================================

    def _create_cleanup_log(
        self,
        delete_results: List[Dict],
        skipped: List[Dict],
        start_time: datetime,
        phase: str
    ) -> Dict[str, Any]:
        """クリーンアップログを作成する。"""
        elapsed = (datetime.now() - start_time).total_seconds()

        return {
            "phase": phase,
            "executed_at": datetime.now().isoformat(),
            "total_targets": len(delete_results),
            "skipped": len(skipped),
            "elapsed_seconds": elapsed,
            "elapsed_formatted": format_duration(elapsed),
            "delete_results": delete_results,
            "skipped_files": skipped,
        }

    def _get_file_size(self, filepath: str) -> int:
        """ファイルサイズを取得する。"""
        try:
            return Path(filepath).stat().st_size
        except OSError:
            return 0

    def _load_report(self, filename: str) -> Dict[str, Any]:
        """レポートを読み込む。"""
        filepath = self.reports_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"レポートが見つかりません: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_report(self, filename: str, data: Dict[str, Any]) -> None:
        """レポートを保存する。"""
        filepath = self.reports_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"レポート保存: {filepath}")


# =============================================================================
# サマリー表示ヘルパー
# =============================================================================

def print_cleanup_originals_summary(log: Dict[str, Any]) -> None:
    """Phase 5a のサマリーを表示する。"""
    print("\n" + "=" * 60)
    print("🗑️  Phase 5a: オリジナル削除結果")
    print("=" * 60)

    print(f"\n削除対象: {log.get('total_targets', 0):,}ファイル")
    print(f"  ✓ 成功: {log.get('success', 0):,}")
    print(f"  ✗ 失敗: {log.get('failed', 0):,}")
    print(f"  ⊘ スキップ: {log.get('skipped', 0):,}")

    print(f"\n処理時間: {log.get('elapsed_formatted', '不明')}")

    # 失敗があれば表示
    failed = [r for r in log.get("delete_results", []) if not r.get("success")]
    if failed:
        print(f"\n⚠ 削除失敗:")
        for r in failed[:5]:
            print(f"  - {r['path']}")
            print(f"    エラー: {r.get('error', '不明')}")
        if len(failed) > 5:
            print(f"  ... 他 {len(failed) - 5}件")


def print_cleanup_duplicates_summary(log: Dict[str, Any]) -> None:
    """Phase 5b のサマリーを表示する。"""
    print("\n" + "=" * 60)
    print("🗑️  Phase 5b: 重複削除結果")
    print("=" * 60)

    print(f"\n削除対象: {log.get('total_targets', 0):,}ファイル")
    print(f"  ✓ 成功: {log.get('success', 0):,}")
    print(f"  ✗ 失敗: {log.get('failed', 0):,}")

    kept = log.get("kept_files", [])
    if kept:
        print(f"\n保持したファイル: {len(kept)}件")

    print(f"\n処理時間: {log.get('elapsed_formatted', '不明')}")


def confirm_cleanup_originals(target_count: int) -> bool:
    """オリジナル削除の確認を取る。"""
    print("\n" + "-" * 60)
    print("⚠️  警告: この操作はオリジナルファイルを削除します。")
    print("削除されたファイルは復元できません。")
    print("-" * 60)
    print(f"\n削除対象: {target_count:,}ファイル")

    while True:
        answer = input("\n本当に削除しますか？ [yes/no]: ").strip().lower()
        if answer == "yes":
            return True
        elif answer in ("n", "no"):
            return False
        else:
            print("'yes' または 'no' を入力してください。")


def confirm_cleanup_duplicates(target_count: int) -> bool:
    """重複削除の確認を取る。"""
    print("\n" + "-" * 60)
    print("⚠️  警告: この操作は重複ファイルを削除します。")
    print("削除されたファイルは復元できません。")
    print("-" * 60)
    print(f"\n削除対象: {target_count:,}ファイル")

    while True:
        answer = input("\n本当に削除しますか？ [yes/no]: ").strip().lower()
        if answer == "yes":
            return True
        elif answer in ("n", "no"):
            return False
        else:
            print("'yes' または 'no' を入力してください。")
