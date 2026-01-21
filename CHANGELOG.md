# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2025-01-XX

### Added

#### Core Features
- **Phase 1a: メタデータスキャン**
  - JPEG, PNG, HEIC 画像の EXIF データ抽出
  - MP4, MOV, 3GP, M4V 動画のメタデータ抽出
  - フォールバック処理（EXIF なしの場合はファイル作成日時を使用）
  - プログレスバー表示（tqdm）

- **Phase 1b: ハッシュ計算**
  - SHA-256 によるファイルハッシュ計算
  - サイズベースの最適化（サイズが一意なファイルはハッシュ計算をスキップ）
  - チェックポイント機能による中断・再開対応

- **Phase 1c: 分析**
  - source/ 内の重複ファイル検出
  - source/ vs organized/ の重複ファイル検出
  - 統計情報生成（ファイル数、日付範囲、形式別カウント）

- **Phase 2: 整理計画**
  - `YYYYMMDDhhmmss-NN` 形式のファイル名生成
  - 既存ファイルとの衝突回避（連番自動調整）
  - ディスク容量チェック
  - 人間可読な計画ファイル出力

- **Phase 3: 整理実行**
  - ファイルコピー（移動ではなくコピー）
  - コピー後のハッシュ検証
  - バッチ処理とチェックポイント保存
  - 定期的な NAS 接続確認

- **Phase 5a: オリジナル削除**
  - 整理成功・検証済みファイルのみ削除対象
  - 削除前確認プロンプト

- **Phase 5b: 重複削除**
  - 重複グループの表示
  - ユーザー選択または自動選択

#### Infrastructure
- **ネットワーク処理**
  - リトライ機構（Exponential Backoff）
  - タイムアウト設定
  - バッチ処理サポート

- **ロック管理**
  - 二重起動防止
  - PC 名・開始時刻記録
  - 24 時間経過後の自動削除確認

- **チェックポイント**
  - JSON 形式での進捗保存
  - 処理済みファイル記録
  - 中断・再開対応

#### User Interface
- 対話モードによる段階的処理
- 各フェーズ後の確認プロンプト
- サマリー表示
- プログレスバー

#### Documentation
- README.md（使用方法、設定例）
- SPECIFICATION.md（詳細仕様）
- DEVELOPMENT.md（開発者ガイド）
- TODO.md（開発タスク管理）

#### Testing
- 129 件の単体テスト
- pytest による自動テスト

### Technical Details

- Python 3.8+ 対応
- 依存ライブラリ: Pillow, pillow-heif, ffmpeg-python, tqdm
- 設定ファイル: config.json

---

## [Unreleased]

### Planned for Future Versions
- プロジェクト管理機能
- インデックスファイル（高速化）
- Web UI
- AI タグ付け

---

## Notes

### Version Numbering
- Major: 互換性のない変更
- Minor: 後方互換性のある機能追加
- Patch: 後方互換性のあるバグ修正

### Date Format
- ISO 8601 形式（YYYY-MM-DD）
