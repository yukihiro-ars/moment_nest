"""
整理実行モジュール

ファイルの実際の整理（コピー・検証）を担当（Phase 3）。
バッチ処理、リトライ、チェックポイントをサポート。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

from .network import NASFileHandler
from .utils import Checkpoint, format_file_size, format_duration

logger = logging.getLogger(__name__)


# =============================================================================
# FileOrganizer クラス
# =============================================================================

class FileOrganizer:
    """
    ファイル整理を実行するクラス。
    コピー → ハッシュ検証 → ログ記録の流れで安全に処理。
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
        self.checkpoints_dir = self.workspace_dir / "checkpoints"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        # ネットワークハンドラー
        self.file_handler = NASFileHandler(config)

        # 設定値
        network = config.get("network", {})
        self.batch_size = network.get("batch_size", 50)
        self.checkpoint_interval = network.get("checkpoint_interval", 100)
        self.connection_check_interval = network.get("connection_check_interval", 250)

    def organize(
        self,
        plan: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        整理計画に従ってファイルを整理する。

        Args:
            plan: 整理計画（Noneなら読み込み）
            progress_callback: 進捗コールバック

        Returns:
            実行ログ辞書
        """
        logger.info("Phase 3: 整理実行開始")
        start_time = datetime.now()

        # 計画読み込み
        if plan is None:
            plan = self._load_report("organize_plan.json")

        move_plan = plan.get("move_plan", [])

        if not move_plan:
            logger.info("移動対象ファイルがありません")
            return self._create_empty_log()

        # ディスク容量チェック
        disk_check = plan.get("disk_check", {})
        if disk_check.get("sufficient") is False:
            raise RuntimeError(
                f"ディスク容量が不足しています。"
                f"必要: {disk_check.get('required_formatted')}, "
                f"空き: {disk_check.get('available_formatted')}"
            )

        # チェックポイント
        checkpoint = Checkpoint(self.checkpoints_dir / "phase3_organize.json")
        checkpoint.set_phase("phase3_organize")
        checkpoint.set_total(len(move_plan))

        # 年フォルダの作成
        self._create_year_folders(move_plan)

        # 実行
        operations = []
        success_count = 0
        failed_count = 0
        skipped_count = 0

        iterator = self._create_progress_iterator(
            move_plan,
            desc="ファイル整理",
            progress_callback=progress_callback
        )

        for i, item in iterator:
            original = item["original"]
            new_path = item["new_path"]

            # チェックポイント確認（既に処理済みならスキップ）
            if checkpoint.should_skip(original):
                existing_result = checkpoint.get_processed_result(original)
                if existing_result:
                    operations.append(existing_result)
                    if existing_result.get("status") == "success":
                        success_count += 1
                    elif existing_result.get("status") == "skipped":
                        skipped_count += 1
                    else:
                        failed_count += 1
                continue

            # 接続確認（定期的に）
            if i > 0 and i % self.connection_check_interval == 0:
                if not self.file_handler.check_connection_with_retry(self.organized_dir):
                    logger.error("NAS接続が失われました。処理を中断します。")
                    break

            # ファイルコピー
            result = self._copy_and_verify(original, new_path)
            operations.append(result)

            if result["status"] == "success":
                success_count += 1
            elif result["status"] == "skipped":
                skipped_count += 1
            else:
                failed_count += 1

            # チェックポイント保存
            checkpoint.mark_processed(original, result)
            if (i + 1) % self.checkpoint_interval == 0:
                checkpoint.save()

        checkpoint.save()

        # ログ作成
        elapsed = (datetime.now() - start_time).total_seconds()

        organize_log = {
            "executed_at": datetime.now().isoformat(),
            "source_dir": str(self.source_dir),
            "organized_dir": str(self.organized_dir),
            "total": len(move_plan),
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "elapsed_seconds": elapsed,
            "elapsed_formatted": format_duration(elapsed),
            "operations": operations,
        }

        # レポート保存
        self._save_report("organize_log.json", organize_log)
        self._save_result_files(operations)

        logger.info(
            f"Phase 3 完了: 成功 {success_count}, 失敗 {failed_count}, "
            f"スキップ {skipped_count}, {format_duration(elapsed)}"
        )

        return organize_log

    def _copy_and_verify(self, original: str, new_path: str) -> Dict[str, Any]:
        """
        ファイルをコピーしてハッシュ検証する。

        Args:
            original: コピー元パス
            new_path: コピー先パス

        Returns:
            操作結果辞書
        """
        result = {
            "status": "failed",
            "original": original,
            "new": new_path,
            "hash_verified": None,
            "error": None,
            "copied_at": None,
        }

        # コピー元の存在確認
        if not Path(original).exists():
            result["status"] = "skipped"
            result["error"] = "コピー元ファイルが存在しません"
            return result

        # コピー先が既に存在する場合
        if Path(new_path).exists():
            result["status"] = "skipped"
            result["error"] = "コピー先ファイルが既に存在します"
            return result

        # コピー実行
        copy_result = self.file_handler.copy_file(original, new_path, verify=True)

        if copy_result["success"]:
            result["status"] = "success"
            result["hash_verified"] = copy_result.get("hash_verified", True)
            result["copied_at"] = datetime.now().isoformat()
        else:
            result["status"] = "failed"
            result["error"] = copy_result.get("error", "コピーエラー")
            result["hash_verified"] = copy_result.get("hash_verified")

        return result

    def _create_year_folders(self, move_plan: List[Dict]) -> None:
        """年フォルダを作成する。"""
        years = set()
        for item in move_plan:
            new_path = Path(item["new_path"])
            # organized_dir/YYYY/filename.ext から YYYY を抽出
            relative = new_path.relative_to(self.organized_dir)
            year = relative.parts[0] if relative.parts else None
            if year and year.isdigit():
                years.add(year)

        for year in years:
            year_dir = self.organized_dir / year
            year_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"年フォルダ作成: {year_dir}")

    def _create_progress_iterator(
        self,
        items: List,
        desc: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        """プログレス表示付きイテレータを作成する。"""
        total = len(items)

        if TQDM_AVAILABLE:
            iterator = tqdm(enumerate(items), total=total, desc=desc, unit="files")
            for i, item in iterator:
                yield i, item
                if progress_callback:
                    progress_callback(i + 1, total)
        else:
            for i, item in enumerate(items):
                yield i, item
                if progress_callback:
                    progress_callback(i + 1, total)

    def _create_empty_log(self) -> Dict[str, Any]:
        """空のログを作成する。"""
        return {
            "executed_at": datetime.now().isoformat(),
            "source_dir": str(self.source_dir),
            "organized_dir": str(self.organized_dir),
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "elapsed_seconds": 0,
            "elapsed_formatted": "0秒",
            "operations": [],
        }

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

    def _save_result_files(self, operations: List[Dict]) -> None:
        """成功・失敗ファイルリストを保存する。"""
        success_files = []
        failed_files = []

        for op in operations:
            if op["status"] == "success":
                success_files.append(f"{op['original']} -> {op['new']}")
            elif op["status"] == "failed":
                failed_files.append(f"{op['original']}: {op.get('error', '不明なエラー')}")

        # success.txt
        success_path = self.reports_dir / "success.txt"
        with open(success_path, "w", encoding="utf-8") as f:
            f.write("整理成功ファイル\n")
            f.write("=" * 60 + "\n")
            f.write(f"作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"成功数: {len(success_files)}\n\n")
            for line in success_files:
                f.write(line + "\n")

        # failed.txt
        failed_path = self.reports_dir / "failed.txt"
        with open(failed_path, "w", encoding="utf-8") as f:
            f.write("整理失敗ファイル\n")
            f.write("=" * 60 + "\n")
            f.write(f"作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"失敗数: {len(failed_files)}\n\n")
            for line in failed_files:
                f.write(line + "\n")

        logger.info(f"結果ファイル保存: {success_path}, {failed_path}")


# =============================================================================
# サマリー表示ヘルパー
# =============================================================================

def print_organize_summary(log: Dict[str, Any]) -> None:
    """整理実行結果のサマリーを表示する。"""
    print("\n" + "=" * 60)
    print("📁 Phase 3: 整理実行結果")
    print("=" * 60)

    print(f"\n総ファイル数: {log.get('total', 0):,}")
    print(f"  ✓ 成功: {log.get('success', 0):,}")
    print(f"  ✗ 失敗: {log.get('failed', 0):,}")
    print(f"  ⊘ スキップ: {log.get('skipped', 0):,}")

    print(f"\n処理時間: {log.get('elapsed_formatted', '不明')}")

    # 失敗があれば表示
    failed_ops = [op for op in log.get("operations", []) if op["status"] == "failed"]
    if failed_ops:
        print(f"\n⚠ 失敗したファイル:")
        for op in failed_ops[:10]:
            print(f"  - {op['original']}")
            print(f"    エラー: {op.get('error', '不明')}")
        if len(failed_ops) > 10:
            print(f"  ... 他 {len(failed_ops) - 10}件")

    print(f"\n詳細は reports/organize_log.json を確認してください")


def confirm_organize() -> bool:
    """整理実行の確認を取る。"""
    print("\n" + "-" * 60)
    print("⚠️  注意: この操作はファイルをコピーします。")
    print("コピー後、Phase 5 でオリジナルを削除できます。")
    print("-" * 60)

    while True:
        answer = input("\n整理を実行しますか？ [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        elif answer in ("n", "no"):
            return False
        else:
            print("y または n を入力してください。")
