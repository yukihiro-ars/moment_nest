"""
整理計画モジュール

整理計画の作成を担当（Phase 2: Dry-run）。
ファイル名生成、連番決定、衝突チェック、容量確認を行う。
"""

import json
import logging
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from .utils import format_file_size, get_year_from_datetime

logger = logging.getLogger(__name__)


# =============================================================================
# FilePlanner クラス
# =============================================================================

class FilePlanner:
    """
    ファイル整理計画を作成するクラス。
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

        # シーケンスマップ（撮影日時 -> 次の連番）
        self._sequence_map: Dict[str, int] = {}

    def create_plan(
        self,
        analysis_report: Optional[Dict[str, Any]] = None,
        existing_files: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        整理計画を作成する。

        Args:
            analysis_report: 分析レポート（Noneなら読み込み）
            existing_files: 既存ファイル情報（Noneなら読み込み）

        Returns:
            整理計画辞書
        """
        logger.info("Phase 2: 整理計画作成開始")
        start_time = datetime.now()

        # レポート読み込み
        if analysis_report is None:
            analysis_report = self._load_report("analysis_report.json")
        if existing_files is None:
            existing_files = self._load_report("existing_files.json")

        # シーケンスマップ初期化
        self._sequence_map = existing_files.get("sequence_map", {}).copy()

        files = analysis_report.get("files", [])

        # 計画リスト
        move_plan = []  # 移動するファイル
        skip_plan = []  # スキップするファイル
        warnings = []

        for file_info in files:
            filepath = file_info.get("filepath") or str(
                self.source_dir / file_info.get("relative_path", "")
            )
            taken_at = file_info.get("taken_at")
            extension = file_info.get("extension", "").lower()
            size = file_info.get("size", 0)

            # 既に整理済み（source/ vs organized/ 重複）ならスキップ
            if file_info.get("is_duplicate_with_existing"):
                skip_plan.append({
                    "original": filepath,
                    "reason": "already_organized",
                    "message": "既に整理済みのファイルと同一",
                })
                continue

            # 撮影日時がない場合は警告
            if not taken_at:
                warnings.append({
                    "file": filepath,
                    "message": "撮影日時が取得できません",
                })
                # フォールバック: 現在日時を使用
                taken_at = datetime.now()
            elif isinstance(taken_at, str):
                try:
                    taken_at = datetime.fromisoformat(taken_at)
                except ValueError:
                    warnings.append({
                        "file": filepath,
                        "message": f"撮影日時のパースに失敗: {taken_at}",
                    })
                    taken_at = datetime.now()

            # 新しいファイル名とパスを生成
            new_filename = self._generate_filename(taken_at, extension)
            year = get_year_from_datetime(taken_at)
            new_relative_path = f"{year}/{new_filename}"
            new_full_path = self.organized_dir / new_relative_path

            move_plan.append({
                "original": filepath,
                "new_path": str(new_full_path),
                "new_relative_path": new_relative_path,
                "taken_at": taken_at.isoformat() if isinstance(taken_at, datetime) else taken_at,
                "size": size,
                "size_formatted": format_file_size(size),
                "is_internal_duplicate": file_info.get("is_duplicate_internal", False),
            })

        # 内部重複の警告
        internal_dup_count = sum(1 for m in move_plan if m.get("is_internal_duplicate"))
        if internal_dup_count > 0:
            warnings.append({
                "file": "(複数)",
                "message": f"source/内に{internal_dup_count}件の重複ファイルがあります",
            })

        # ディスク容量チェック
        total_size = sum(m["size"] for m in move_plan)
        disk_check = self._check_disk_space(total_size)

        # 計画サマリー
        elapsed = (datetime.now() - start_time).total_seconds()

        plan = {
            "created_at": datetime.now().isoformat(),
            "source_dir": str(self.source_dir),
            "organized_dir": str(self.organized_dir),
            "summary": {
                "total_files": len(files),
                "move_count": len(move_plan),
                "skip_count": len(skip_plan),
                "warning_count": len(warnings),
                "total_size": total_size,
                "total_size_formatted": format_file_size(total_size),
            },
            "disk_check": disk_check,
            "move_plan": move_plan,
            "skip_plan": skip_plan,
            "warnings": warnings,
            "elapsed_seconds": elapsed,
        }

        # レポート保存
        self._save_report("organize_plan.json", plan)
        self._save_plan_text(plan)

        logger.info(f"Phase 2 完了: {len(move_plan)}件移動予定, {len(skip_plan)}件スキップ")

        return plan

    def _generate_filename(self, taken_at: datetime, extension: str) -> str:
        """
        撮影日時からファイル名を生成する。

        Args:
            taken_at: 撮影日時
            extension: 拡張子（ドット付き）

        Returns:
            YYYYMMDDhhmmss-NN.ext 形式のファイル名
        """
        base = taken_at.strftime("%Y%m%d%H%M%S")

        # シーケンス番号を決定
        if base in self._sequence_map:
            seq = self._sequence_map[base]
        else:
            seq = 1

        # シーケンスマップを更新
        self._sequence_map[base] = seq + 1

        # 拡張子の正規化
        if not extension.startswith("."):
            extension = "." + extension

        return f"{base}-{seq:02d}{extension}"

    def _check_disk_space(self, required_bytes: int) -> Dict[str, Any]:
        """
        ディスク容量をチェックする。

        Args:
            required_bytes: 必要なバイト数

        Returns:
            チェック結果辞書
        """
        result = {
            "required": required_bytes,
            "required_formatted": format_file_size(required_bytes),
            "available": None,
            "available_formatted": None,
            "sufficient": None,
            "error": None,
        }

        try:
            # organized_dir のディスク情報を取得
            target_path = self.organized_dir
            if not target_path.exists():
                target_path = target_path.parent

            if target_path.exists():
                usage = shutil.disk_usage(target_path)
                result["available"] = usage.free
                result["available_formatted"] = format_file_size(usage.free)
                result["sufficient"] = usage.free >= required_bytes
            else:
                result["error"] = "保存先パスが存在しません"
                result["sufficient"] = False

        except OSError as e:
            result["error"] = str(e)
            result["sufficient"] = False

        return result

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

    def _save_plan_text(self, plan: Dict[str, Any]) -> None:
        """整理計画をテキスト形式で保存する（人間可読）。"""
        lines = []

        lines.append("整理計画")
        lines.append("=" * 60)
        lines.append(f"作成日時: {plan['created_at'][:19].replace('T', ' ')}")
        lines.append("")

        # サマリー
        summary = plan["summary"]
        lines.append(f"処理予定: {summary['move_count']}ファイル")
        lines.append(f"スキップ: {summary['skip_count']}ファイル（重複等）")
        lines.append(f"必要容量: {summary['total_size_formatted']}")
        lines.append("")

        # ディスク容量
        disk = plan["disk_check"]
        if disk["available_formatted"]:
            lines.append(f"空き容量: {disk['available_formatted']}")
            status = "✓ OK" if disk["sufficient"] else "✗ 不足"
            lines.append(f"容量チェック: {status}")
        else:
            lines.append(f"容量チェック: エラー - {disk.get('error', '不明')}")
        lines.append("")

        # 移動計画
        lines.append("-" * 60)
        lines.append("移動計画")
        lines.append("-" * 60)

        for item in plan["move_plan"][:100]:  # 最初の100件のみ表示
            lines.append("")
            lines.append(f"{item['original']} ({item['size_formatted']})")
            lines.append(f"  → {item['new_relative_path']}")
            lines.append(f"  撮影日時: {item['taken_at'][:19].replace('T', ' ')}")
            if item.get("is_internal_duplicate"):
                lines.append("  ⚠ source/内に重複あり")

        if len(plan["move_plan"]) > 100:
            lines.append(f"\n... 他 {len(plan['move_plan']) - 100}件")

        # スキップ
        if plan["skip_plan"]:
            lines.append("")
            lines.append("-" * 60)
            lines.append("スキップファイル")
            lines.append("-" * 60)

            for item in plan["skip_plan"][:50]:  # 最初の50件のみ
                lines.append("")
                lines.append(f"{item['original']}")
                lines.append(f"  理由: {item['message']}")

            if len(plan["skip_plan"]) > 50:
                lines.append(f"\n... 他 {len(plan['skip_plan']) - 50}件")

        # 警告
        if plan["warnings"]:
            lines.append("")
            lines.append("-" * 60)
            lines.append("警告")
            lines.append("-" * 60)

            for warning in plan["warnings"]:
                lines.append(f"⚠ {warning['file']}: {warning['message']}")

        # 保存
        filepath = self.reports_dir / "organize_plan.txt"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"計画テキスト保存: {filepath}")


# =============================================================================
# サマリー表示ヘルパー
# =============================================================================

def print_plan_summary(plan: Dict[str, Any]) -> None:
    """整理計画のサマリーを表示する。"""
    print("\n" + "=" * 60)
    print("📋 Phase 2: 整理計画")
    print("=" * 60)

    summary = plan.get("summary", {})
    print(f"\n処理予定: {summary.get('move_count', 0):,}ファイル")
    print(f"スキップ: {summary.get('skip_count', 0):,}ファイル")
    print(f"必要容量: {summary.get('total_size_formatted', '不明')}")

    disk = plan.get("disk_check", {})
    if disk.get("available_formatted"):
        print(f"\n空き容量: {disk['available_formatted']}")
        if disk.get("sufficient"):
            print("✓ ディスク容量: OK")
        else:
            print("✗ ディスク容量: 不足しています！")
    elif disk.get("error"):
        print(f"\n⚠ 容量チェックエラー: {disk['error']}")

    warnings = plan.get("warnings", [])
    if warnings:
        print(f"\n⚠ 警告: {len(warnings)}件")
        for w in warnings[:5]:
            print(f"  - {w['message']}")
        if len(warnings) > 5:
            print(f"  ... 他 {len(warnings) - 5}件")

    print(f"\n詳細は reports/organize_plan.txt を確認してください")
