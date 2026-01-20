"""
スキャナーモジュール

ファイルスキャン、ハッシュ計算、分析を担当。
Phase 1a, 1b, 1c の処理を実装。
"""

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Callable

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

from .metadata import MetadataExtractor
from .network import NASFileHandler
from .utils import (
    Checkpoint,
    format_file_size,
    format_duration,
    get_file_extension,
    calculate_hash,
)

logger = logging.getLogger(__name__)


# =============================================================================
# PhotoScanner クラス
# =============================================================================

class PhotoScanner:
    """
    写真・動画ファイルをスキャン・分析するクラス。
    Phase 1a, 1b, 1c の処理を担当。
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

        # レポート・チェックポイントディレクトリ
        self.reports_dir = self.workspace_dir / "reports"
        self.checkpoints_dir = self.workspace_dir / "checkpoints"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        # サブモジュール
        self.metadata_extractor = MetadataExtractor(config)
        self.file_handler = NASFileHandler(config)

        # 対応拡張子
        supported = config.get("supported_extensions", {})
        self.image_extensions = [e.lower() for e in supported.get("image", [".jpg", ".jpeg", ".heic", ".png"])]
        self.video_extensions = [e.lower() for e in supported.get("video", [".mp4", ".mov", ".3gp", ".m4v"])]
        self.all_extensions = self.image_extensions + self.video_extensions

        # ハッシュ最適化設定
        hash_opt = config.get("hash_optimization", {})
        self.skip_unique_sizes = hash_opt.get("skip_unique_sizes", True)

        # ネットワーク設定
        network = config.get("network", {})
        self.checkpoint_interval = network.get("checkpoint_interval", 100)

    # =========================================================================
    # Phase 1a: メタデータスキャン
    # =========================================================================

    def scan_metadata(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Phase 1a: source/ と organized/ をスキャンしてメタデータを抽出する。

        Args:
            progress_callback: 進捗コールバック（処理済み数, 総数）

        Returns:
            メタデータレポート辞書
        """
        logger.info("Phase 1a: メタデータスキャン開始")
        start_time = datetime.now()

        # source/ のスキャン
        logger.info(f"source/ をスキャン中: {self.source_dir}")
        source_files = self._list_supported_files(self.source_dir)
        logger.info(f"  対象ファイル数: {len(source_files)}")

        # メタデータ抽出
        files_metadata = []
        warnings = []

        iterator = self._create_progress_iterator(
            source_files,
            desc="メタデータ抽出",
            progress_callback=progress_callback
        )

        for filepath in iterator:
            try:
                metadata = self.metadata_extractor.extract(filepath)

                # ファイルサイズを追加
                try:
                    metadata["size"] = filepath.stat().st_size
                except OSError:
                    metadata["size"] = 0

                metadata["extension"] = get_file_extension(filepath)
                metadata["relative_path"] = str(filepath.relative_to(self.source_dir))

                files_metadata.append(metadata)

                # 警告チェック
                if metadata.get("error"):
                    warnings.append({
                        "file": str(filepath),
                        "message": metadata["error"]
                    })
                elif metadata.get("date_source") == "file_ctime":
                    warnings.append({
                        "file": str(filepath),
                        "message": "EXIF読み取り失敗、ファイル作成日時を使用"
                    })

            except Exception as e:
                logger.error(f"メタデータ抽出エラー: {filepath} - {e}")
                warnings.append({
                    "file": str(filepath),
                    "message": str(e)
                })

        # organized/ の軽量スキャン
        logger.info(f"organized/ を軽量スキャン中: {self.organized_dir}")
        existing_files = self._scan_existing_files()

        # 統計情報
        stats = self._calculate_metadata_stats(files_metadata)

        # レポート作成
        elapsed = (datetime.now() - start_time).total_seconds()

        metadata_report = {
            "scan_date": datetime.now().isoformat(),
            "source_dir": str(self.source_dir),
            "total_files": len(files_metadata),
            "by_type": stats["by_type"],
            "date_range": stats["date_range"],
            "total_size": stats["total_size"],
            "total_size_formatted": format_file_size(stats["total_size"]),
            "elapsed_seconds": elapsed,
            "elapsed_formatted": format_duration(elapsed),
            "files": files_metadata,
            "warnings": warnings,
        }

        # レポート保存
        self._save_report("metadata_report.json", metadata_report)
        self._save_report("existing_files.json", existing_files)

        if warnings:
            self._save_warnings(warnings)

        logger.info(f"Phase 1a 完了: {len(files_metadata)}ファイル, {format_duration(elapsed)}")

        return metadata_report

    def _scan_existing_files(self) -> Dict[str, Any]:
        """organized/ の既存ファイルを軽量スキャンする。"""
        if not self.organized_dir.exists():
            return {
                "scan_date": datetime.now().isoformat(),
                "organized_dir": str(self.organized_dir),
                "total_files": 0,
                "files": {},
                "size_map": {},
                "sequence_map": {},
            }

        files_info = {}
        size_map = defaultdict(list)
        sequence_map = {}

        existing_files = self._list_supported_files(self.organized_dir)
        logger.info(f"  既存ファイル数: {len(existing_files)}")

        for filepath in existing_files:
            try:
                stat = filepath.stat()
                relative_path = str(filepath.relative_to(self.organized_dir))
                filename = filepath.stem  # 拡張子なし

                files_info[filepath.name] = {
                    "size": stat.st_size,
                    "path": relative_path,
                }

                # サイズマップ
                size_map[stat.st_size].append(relative_path)

                # シーケンスマップ（YYYYMMDDhhmmss-NN 形式から）
                self._update_sequence_map(filename, sequence_map)

            except OSError as e:
                logger.warning(f"既存ファイル情報取得エラー: {filepath} - {e}")

        return {
            "scan_date": datetime.now().isoformat(),
            "organized_dir": str(self.organized_dir),
            "total_files": len(files_info),
            "files": files_info,
            "size_map": dict(size_map),
            "sequence_map": sequence_map,
        }

    def _update_sequence_map(self, filename: str, sequence_map: Dict[str, int]) -> None:
        """ファイル名からシーケンスマップを更新する。"""
        # YYYYMMDDhhmmss-NN 形式をパース
        if "-" in filename:
            parts = filename.rsplit("-", 1)
            if len(parts) == 2:
                base, seq_str = parts
                if len(base) == 14 and base.isdigit():
                    try:
                        seq = int(seq_str)
                        if base not in sequence_map or seq >= sequence_map[base]:
                            sequence_map[base] = seq + 1
                    except ValueError:
                        pass

    def _list_supported_files(self, directory: Path) -> List[Path]:
        """対応形式のファイルをリストする。"""
        files = []
        if not directory.exists():
            return files

        try:
            for filepath in directory.rglob("*"):
                if filepath.is_file():
                    ext = filepath.suffix.lower()
                    if ext in self.all_extensions:
                        files.append(filepath)
        except OSError as e:
            logger.error(f"ディレクトリスキャンエラー: {directory} - {e}")

        return files

    def _calculate_metadata_stats(self, files_metadata: List[Dict]) -> Dict[str, Any]:
        """メタデータから統計情報を計算する。"""
        by_type = {"image": 0, "video": 0}
        total_size = 0
        dates = []

        for meta in files_metadata:
            ext = meta.get("extension", "").lower()
            if ext in self.image_extensions:
                by_type["image"] += 1
            elif ext in self.video_extensions:
                by_type["video"] += 1

            total_size += meta.get("size", 0)

            taken_at = meta.get("taken_at")
            if taken_at:
                if isinstance(taken_at, datetime):
                    dates.append(taken_at)
                elif isinstance(taken_at, str):
                    try:
                        dates.append(datetime.fromisoformat(taken_at))
                    except ValueError:
                        pass

        date_range = {}
        if dates:
            date_range = {
                "earliest": min(dates).isoformat(),
                "latest": max(dates).isoformat(),
            }

        return {
            "by_type": by_type,
            "total_size": total_size,
            "date_range": date_range,
        }

    # =========================================================================
    # Phase 1b: ハッシュ計算
    # =========================================================================

    def scan_hash(
        self,
        metadata_report: Optional[Dict[str, Any]] = None,
        existing_files: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Phase 1b: ハッシュ計算（サイズベース最適化）。

        Args:
            metadata_report: Phase 1a のメタデータレポート（Noneなら読み込み）
            existing_files: 既存ファイル情報（Noneなら読み込み）
            progress_callback: 進捗コールバック

        Returns:
            ハッシュレポート辞書
        """
        logger.info("Phase 1b: ハッシュ計算開始")
        start_time = datetime.now()

        # レポート読み込み
        if metadata_report is None:
            metadata_report = self._load_report("metadata_report.json")
        if existing_files is None:
            existing_files = self._load_report("existing_files.json")

        # チェックポイント
        checkpoint = Checkpoint(self.checkpoints_dir / "phase1b_hash.json")
        checkpoint.set_phase("phase1b_hash")

        # ファイルリストとサイズマップ作成
        source_files = metadata_report.get("files", [])
        source_size_map = defaultdict(list)

        for meta in source_files:
            size = meta.get("size", 0)
            filepath = meta.get("filepath") or str(self.source_dir / meta.get("relative_path", ""))
            source_size_map[size].append(filepath)

        # 既存ファイルのサイズマップ
        existing_size_map = existing_files.get("size_map", {})
        # キーを整数に変換
        existing_size_map = {int(k): v for k, v in existing_size_map.items()}

        # ハッシュ計算対象を決定
        hash_targets = []
        skipped_unique = 0

        for size, filepaths in source_size_map.items():
            existing_count = len(existing_size_map.get(size, []))
            source_count = len(filepaths)

            if self.skip_unique_sizes:
                # サイズが一意（source内で1つ、かつexistingにもない）ならスキップ
                if source_count == 1 and existing_count == 0:
                    skipped_unique += 1
                    continue

            # 重複の可能性あり → ハッシュ計算対象
            hash_targets.extend(filepaths)

        logger.info(f"  ハッシュ計算対象: {len(hash_targets)}ファイル")
        logger.info(f"  スキップ（サイズ一意）: {skipped_unique}ファイル")

        # 既存ファイルのハッシュも必要な場合は追加
        existing_hash_targets = []
        for size, filepaths in existing_size_map.items():
            if size in source_size_map and len(source_size_map[size]) > 0:
                for relpath in filepaths:
                    existing_hash_targets.append(str(self.organized_dir / relpath))

        if existing_hash_targets:
            logger.info(f"  既存ファイルのハッシュ計算: {len(existing_hash_targets)}ファイル")

        # ハッシュ計算実行
        checkpoint.set_total(len(hash_targets) + len(existing_hash_targets))

        hash_results = []
        all_targets = hash_targets + existing_hash_targets

        iterator = self._create_progress_iterator(
            all_targets,
            desc="ハッシュ計算",
            progress_callback=progress_callback
        )

        for i, filepath in enumerate(iterator):
            # チェックポイント確認
            if checkpoint.should_skip(filepath):
                result = checkpoint.get_processed_result(filepath)
                if result:
                    hash_results.append(result)
                continue

            # ハッシュ計算
            file_hash = self.file_handler.calculate_hash(filepath)

            result = {
                "path": filepath,
                "size": self._get_file_size(filepath),
                "hash": file_hash,
                "hash_status": "calculated" if file_hash else "failed",
                "is_existing": filepath in existing_hash_targets or str(filepath) in existing_hash_targets,
            }

            hash_results.append(result)
            checkpoint.mark_processed(filepath, result)

            # 定期的にチェックポイント保存
            if (i + 1) % self.checkpoint_interval == 0:
                checkpoint.save()

        checkpoint.save()

        # スキップしたファイルの結果を追加
        for meta in source_files:
            filepath = meta.get("filepath") or str(self.source_dir / meta.get("relative_path", ""))
            if filepath not in hash_targets:
                hash_results.append({
                    "path": filepath,
                    "size": meta.get("size", 0),
                    "hash": None,
                    "hash_status": "skipped_unique_size",
                    "is_existing": False,
                })

        # レポート作成
        elapsed = (datetime.now() - start_time).total_seconds()

        hash_report = {
            "scan_date": datetime.now().isoformat(),
            "total_files": len(source_files),
            "hash_calculated": len(hash_targets) + len(existing_hash_targets),
            "hash_skipped": skipped_unique,
            "optimization_stats": {
                "unique_sizes": skipped_unique,
                "duplicate_sizes": len(hash_targets),
                "existing_checked": len(existing_hash_targets),
            },
            "elapsed_seconds": elapsed,
            "elapsed_formatted": format_duration(elapsed),
            "files": hash_results,
        }

        self._save_report("hash_report.json", hash_report)

        logger.info(f"Phase 1b 完了: {len(hash_targets)}件計算, {format_duration(elapsed)}")

        return hash_report

    def _get_file_size(self, filepath: Union[str, Path]) -> int:
        """ファイルサイズを取得する。"""
        try:
            return Path(filepath).stat().st_size
        except OSError:
            return 0

    # =========================================================================
    # Phase 1c: 分析
    # =========================================================================

    def analyze(
        self,
        metadata_report: Optional[Dict[str, Any]] = None,
        hash_report: Optional[Dict[str, Any]] = None,
        existing_files: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Phase 1c: メタデータとハッシュを統合して分析する。

        Args:
            metadata_report: メタデータレポート
            hash_report: ハッシュレポート
            existing_files: 既存ファイル情報

        Returns:
            分析レポート辞書
        """
        logger.info("Phase 1c: 分析開始")
        start_time = datetime.now()

        # レポート読み込み
        if metadata_report is None:
            metadata_report = self._load_report("metadata_report.json")
        if hash_report is None:
            hash_report = self._load_report("hash_report.json")
        if existing_files is None:
            existing_files = self._load_report("existing_files.json")

        # ハッシュマップ作成
        hash_map = {}  # filepath -> hash
        hash_to_files = defaultdict(list)  # hash -> [filepaths]

        for item in hash_report.get("files", []):
            filepath = item.get("path")
            file_hash = item.get("hash")
            is_existing = item.get("is_existing", False)

            if filepath and file_hash:
                hash_map[filepath] = file_hash
                hash_to_files[file_hash].append({
                    "path": filepath,
                    "is_existing": is_existing,
                })

        # 重複検出
        duplicates_source_internal = []  # source/ 内の重複
        duplicates_source_vs_organized = []  # source/ vs organized/ の重複

        for file_hash, files in hash_to_files.items():
            if len(files) < 2:
                continue

            source_files = [f for f in files if not f["is_existing"]]
            existing_files_list = [f for f in files if f["is_existing"]]

            # source/ 内の重複
            if len(source_files) >= 2:
                duplicates_source_internal.append({
                    "hash": file_hash,
                    "files": [f["path"] for f in source_files],
                })

            # source/ vs organized/ の重複
            if source_files and existing_files_list:
                duplicates_source_vs_organized.append({
                    "hash": file_hash,
                    "source_files": [f["path"] for f in source_files],
                    "existing_files": [f["path"] for f in existing_files_list],
                })

        # メタデータとハッシュを統合
        integrated_files = []
        for meta in metadata_report.get("files", []):
            filepath = meta.get("filepath") or str(self.source_dir / meta.get("relative_path", ""))

            integrated = {
                **meta,
                "hash": hash_map.get(filepath),
            }

            # 重複状態を追加
            file_hash = integrated.get("hash")
            if file_hash:
                is_internal_dup = any(
                    filepath in dup["files"]
                    for dup in duplicates_source_internal
                )
                is_cross_dup = any(
                    filepath in dup["source_files"]
                    for dup in duplicates_source_vs_organized
                )
                integrated["is_duplicate_internal"] = is_internal_dup
                integrated["is_duplicate_with_existing"] = is_cross_dup
            else:
                integrated["is_duplicate_internal"] = False
                integrated["is_duplicate_with_existing"] = False

            integrated_files.append(integrated)

        # 統計情報
        statistics = self._calculate_analysis_stats(
            metadata_report,
            duplicates_source_internal,
            duplicates_source_vs_organized
        )

        # レポート作成
        elapsed = (datetime.now() - start_time).total_seconds()

        analysis_report = {
            "analysis_date": datetime.now().isoformat(),
            "total_files": len(integrated_files),
            "duplicates": {
                "source_internal": duplicates_source_internal,
                "source_internal_count": len(duplicates_source_internal),
                "source_vs_organized": duplicates_source_vs_organized,
                "source_vs_organized_count": len(duplicates_source_vs_organized),
            },
            "statistics": statistics,
            "elapsed_seconds": elapsed,
            "elapsed_formatted": format_duration(elapsed),
            "files": integrated_files,
        }

        # レポート保存
        self._save_report("analysis_report.json", analysis_report)
        self._save_duplicates_report(duplicates_source_internal, duplicates_source_vs_organized)

        logger.info(f"Phase 1c 完了: {format_duration(elapsed)}")
        logger.info(f"  source/内重複: {len(duplicates_source_internal)}グループ")
        logger.info(f"  source/ vs organized/重複: {len(duplicates_source_vs_organized)}グループ")

        return analysis_report

    def _calculate_analysis_stats(
        self,
        metadata_report: Dict[str, Any],
        duplicates_internal: List[Dict],
        duplicates_cross: List[Dict]
    ) -> Dict[str, Any]:
        """分析統計情報を計算する。"""
        files = metadata_report.get("files", [])

        # 形式別カウント
        by_extension = defaultdict(int)
        by_camera = defaultdict(int)

        for meta in files:
            ext = meta.get("extension", "unknown").lower()
            by_extension[ext] += 1

            camera = meta.get("camera_model") or meta.get("camera_make") or "unknown"
            by_camera[camera] += 1

        # 重複ファイル数
        internal_dup_files = sum(len(d["files"]) - 1 for d in duplicates_internal)
        cross_dup_files = sum(len(d["source_files"]) for d in duplicates_cross)

        return {
            "date_range": metadata_report.get("date_range", {}),
            "by_type": metadata_report.get("by_type", {}),
            "by_extension": dict(by_extension),
            "by_camera": dict(by_camera),
            "total_size": metadata_report.get("total_size", 0),
            "total_size_formatted": metadata_report.get("total_size_formatted", ""),
            "duplicate_stats": {
                "internal_groups": len(duplicates_internal),
                "internal_duplicate_files": internal_dup_files,
                "cross_groups": len(duplicates_cross),
                "cross_duplicate_files": cross_dup_files,
                "total_duplicate_files": internal_dup_files + cross_dup_files,
            },
        }

    def _save_duplicates_report(
        self,
        duplicates_internal: List[Dict],
        duplicates_cross: List[Dict]
    ) -> None:
        """重複ファイルレポートをテキスト形式で保存する。"""
        lines = []
        lines.append("重複ファイルレポート")
        lines.append("=" * 60)
        lines.append(f"作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # source/ 内の重複
        lines.append("-" * 60)
        lines.append("■ source/ 内の重複")
        lines.append("-" * 60)

        if duplicates_internal:
            for i, dup in enumerate(duplicates_internal, 1):
                lines.append(f"\n[グループ {i}] ハッシュ: {dup['hash'][:16]}...")
                for filepath in dup["files"]:
                    lines.append(f"  - {filepath}")
        else:
            lines.append("なし")

        lines.append("")

        # source/ vs organized/ の重複
        lines.append("-" * 60)
        lines.append("■ source/ vs organized/ の重複（既に整理済み）")
        lines.append("-" * 60)

        if duplicates_cross:
            for i, dup in enumerate(duplicates_cross, 1):
                lines.append(f"\n[グループ {i}] ハッシュ: {dup['hash'][:16]}...")
                lines.append("  source/:")
                for filepath in dup["source_files"]:
                    lines.append(f"    - {filepath}")
                lines.append("  organized/:")
                for filepath in dup["existing_files"]:
                    lines.append(f"    - {filepath}")
        else:
            lines.append("なし")

        # 保存
        duplicates_path = self.reports_dir / "duplicates.txt"
        with open(duplicates_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"重複レポート保存: {duplicates_path}")

    # =========================================================================
    # ユーティリティ
    # =========================================================================

    def _create_progress_iterator(
        self,
        items: List,
        desc: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        """プログレス表示付きイテレータを作成する。"""
        total = len(items)

        if TQDM_AVAILABLE:
            iterator = tqdm(items, desc=desc, unit="files")
        else:
            iterator = items

        for i, item in enumerate(iterator):
            yield item
            if progress_callback:
                progress_callback(i + 1, total)

    def _save_report(self, filename: str, data: Dict[str, Any]) -> None:
        """レポートをJSONファイルに保存する。"""
        # datetimeオブジェクトをシリアライズ可能にする
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        filepath = self.reports_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=serialize)
        logger.info(f"レポート保存: {filepath}")

    def _load_report(self, filename: str) -> Dict[str, Any]:
        """レポートをJSONファイルから読み込む。"""
        filepath = self.reports_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"レポートが見つかりません: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_warnings(self, warnings: List[Dict]) -> None:
        """警告をテキストファイルに保存する。"""
        lines = []
        lines.append("警告レポート")
        lines.append("=" * 60)
        lines.append(f"作成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"警告数: {len(warnings)}")
        lines.append("")

        for warning in warnings:
            lines.append(f"ファイル: {warning['file']}")
            lines.append(f"  メッセージ: {warning['message']}")
            lines.append("")

        filepath = self.reports_dir / "warnings.txt"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"警告レポート保存: {filepath}")


# =============================================================================
# サマリー表示ヘルパー
# =============================================================================

def print_metadata_summary(report: Dict[str, Any]) -> None:
    """Phase 1a のサマリーを表示する。"""
    print("\n" + "=" * 60)
    print("📊 Phase 1a: メタデータスキャン結果")
    print("=" * 60)

    print(f"\n対象ディレクトリ: {report.get('source_dir')}")
    print(f"総ファイル数: {report.get('total_files'):,}")

    by_type = report.get("by_type", {})
    print(f"  - 画像: {by_type.get('image', 0):,}")
    print(f"  - 動画: {by_type.get('video', 0):,}")

    print(f"\n総サイズ: {report.get('total_size_formatted', '不明')}")

    date_range = report.get("date_range", {})
    if date_range:
        print(f"日付範囲: {date_range.get('earliest', '?')[:10]} ～ {date_range.get('latest', '?')[:10]}")

    warnings = report.get("warnings", [])
    if warnings:
        print(f"\n⚠️  警告: {len(warnings)}件")

    print(f"\n処理時間: {report.get('elapsed_formatted', '不明')}")


def print_hash_summary(report: Dict[str, Any]) -> None:
    """Phase 1b のサマリーを表示する。"""
    print("\n" + "=" * 60)
    print("📊 Phase 1b: ハッシュ計算結果")
    print("=" * 60)

    print(f"\n総ファイル数: {report.get('total_files'):,}")
    print(f"ハッシュ計算: {report.get('hash_calculated'):,}")
    print(f"スキップ: {report.get('hash_skipped'):,}")

    stats = report.get("optimization_stats", {})
    print(f"\n最適化統計:")
    print(f"  - サイズ一意（スキップ）: {stats.get('unique_sizes', 0):,}")
    print(f"  - 重複サイズ（計算）: {stats.get('duplicate_sizes', 0):,}")
    print(f"  - 既存ファイル確認: {stats.get('existing_checked', 0):,}")

    print(f"\n処理時間: {report.get('elapsed_formatted', '不明')}")


def print_analysis_summary(report: Dict[str, Any]) -> None:
    """Phase 1c のサマリーを表示する。"""
    print("\n" + "=" * 60)
    print("📊 Phase 1c: 分析結果")
    print("=" * 60)

    print(f"\n総ファイル数: {report.get('total_files'):,}")

    duplicates = report.get("duplicates", {})
    print(f"\n重複検出:")
    print(f"  - source/内重複: {duplicates.get('source_internal_count', 0)}グループ")
    print(f"  - source/ vs organized/重複: {duplicates.get('source_vs_organized_count', 0)}グループ")

    stats = report.get("statistics", {}).get("duplicate_stats", {})
    print(f"\n重複ファイル数:")
    print(f"  - source/内の重複ファイル: {stats.get('internal_duplicate_files', 0)}")
    print(f"  - 既に整理済みのファイル: {stats.get('cross_duplicate_files', 0)}")

    print(f"\n処理時間: {report.get('elapsed_formatted', '不明')}")
