# 開発タスクリスト（TODO）

## 🎯 v1.0 リリース目標

家族写真・動画のNAS整理ツールを完成させ、実用可能な状態にする。

---

## Phase 0: プロジェクトセットアップ

### 基本構造
- [x] プロジェクト仕様書作成（SPECIFICATION.md）
- [x] README.md作成
- [x] TODO.md作成（このファイル）
- [x] DEVELOPMENT.md作成
- [x] ディレクトリ構造の作成
- [x] requirements.txt作成
- [x] config.json テンプレート作成
- [x] .gitignore 作成

### 共通モジュール基盤
- [x] `modules/__init__.py` 作成
- [x] `modules/utils.py` 基本ユーティリティ
  - [x] ファイルサイズフォーマット関数
  - [x] 日時フォーマット関数
  - [x] パス操作ヘルパー
- [x] ログ設定（標準ライブラリ logging）
- [x] 設定ファイル読み込み（config.json）

---

## Phase 1: コアモジュール実装

### 1.1 メタデータ抽出（modules/metadata.py）
- [x] EXIF抽出クラス（画像用）
  - [x] JPEG, PNG対応
  - [x] HEIC対応
  - [x] DateTimeOriginal 取得
  - [x] カメラ機種、GPS情報取得（将来用）
- [x] 動画メタデータ抽出クラス
  - [x] MP4, MOV, 3GP, M4V対応
  - [x] creation_time 取得
  - [x] ffmpeg-python 使用
- [x] フォールバック処理
  - [x] EXIF失敗時にファイル作成日時使用
  - [x] エラーハンドリング

### 1.2 ネットワークハンドラー（modules/network.py）
- [x] NASFileHandler クラス
  - [x] リトライ機構（exponential backoff）
  - [x] タイムアウト設定
  - [x] 接続確認メソッド
  - [x] エラーハンドリング
- [x] バッチ処理サポート
- [x] 進捗コールバック対応

### 1.3 ロック管理（modules/lock.py）
- [x] LockManager クラス
  - [x] ロックファイル作成・削除
  - [x] ロック存在チェック
  - [x] 24時間自動削除確認
  - [x] PC名、開始時刻記録
  - [x] current_phase 更新メソッド
- [x] エラーメッセージ生成
- [x] ユーザー確認プロンプト

### 1.4 チェックポイント管理（modules/utils.py に追加）
- [x] Checkpoint クラス
  - [x] JSON保存・読み込み
  - [x] 処理済みファイル記録
  - [x] 進捗率計算
  - [x] 再開判定

---

## Phase 2: スキャン・分析機能

### 2.1 Phase 1a: メタデータスキャン（modules/scanner.py）
- [x] PhotoScanner クラス
- [x] source/ ディレクトリスキャン
  - [x] 再帰的ファイル検索
  - [x] 対応形式フィルタリング
  - [x] メタデータ抽出
  - [x] プログレスバー表示（tqdm）
- [x] organized/ 軽量スキャン
  - [x] ファイル名リスト作成
  - [x] ファイルサイズマップ作成
- [x] metadata_report.json 出力
- [x] existing_files.json 出力
- [x] warnings.txt 出力

### 2.2 Phase 1b: ハッシュ計算（modules/scanner.py に追加）
- [x] サイズベースグループ化
  - [x] ファイルサイズでグループ化
  - [x] サイズ一意判定
  - [x] 重複サイズ抽出
- [x] ハッシュ計算（SHA-256）
  - [x] source/ 内の重複候補
  - [x] source/ vs organized/ の重複候補
  - [x] チェックポイント保存（100件ごと）
  - [x] 再開対応
  - [x] プログレスバー表示
- [x] hash_report.json 出力
- [x] 最適化統計情報出力

### 2.3 Phase 1c: 分析（modules/scanner.py に追加）
- [x] メタデータ + ハッシュ統合
- [x] 重複検出
  - [x] source/ 内の重複
  - [x] source/ vs organized/ の重複
- [x] 統計情報生成
  - [x] ファイル数、日付範囲
  - [x] 形式別カウント
- [x] analysis_report.json 出力
- [x] duplicates.txt 出力（種別ごと）

---

## Phase 3: 整理計画・実行

### 3.1 Phase 2: 整理計画（modules/planner.py）
- [x] FilePlanner クラス
- [x] ファイル名生成ロジック
  - [x] YYYYMMDDhhmmss-NN 形式
  - [x] 連番決定（既存ファイル考慮）
  - [x] ファイル名衝突チェック
- [x] 重複ファイル処理
  - [x] source/ vs organized/ 重複はスキップ
- [x] ディスク容量チェック
- [x] organize_plan.txt 出力
  - [x] 移動計画リスト
  - [x] スキップファイルリスト
  - [x] 警告・エラー
  - [x] 必要容量

### 3.2 Phase 3: 整理実行（modules/organizer.py）
- [x] FileOrganizer クラス
- [x] 年ごとのフォルダ作成
- [x] バッチ処理
  - [x] ファイルコピー（移動ではない）
  - [x] NAS接続確認（5バッチごと）
  - [x] リトライ処理
- [x] コピー後ハッシュ検証
- [x] チェックポイント保存
- [x] プログレスバー表示
- [x] organize_log.json 出力
- [x] success.txt / failed.txt 出力

---

## Phase 4: クリーンアップ機能

### 4.1 Phase 5a: オリジナル削除（modules/cleaner.py）
- [x] FileCleaner クラス
- [x] organize_log.json 読み込み
- [x] 削除対象フィルタリング
  - [x] status="success" のみ
  - [x] hash_verified=true のみ
- [x] 削除前確認プロンプト
- [x] ファイル削除実行
- [x] 削除ログ出力

### 4.2 Phase 5b: 重複削除（modules/cleaner.py に追加）
- [x] duplicates.txt 読み込み
- [x] 重複グループ表示
- [x] ユーザー選択UI
  - [x] 各グループで残すファイル選択
  - [x] または自動選択（最初のファイル）
- [x] 削除実行
- [x] 削除ログ出力

---

## Phase 5: 対話モード実装

### 5.1 メインスクリプト（organize.py）
- [x] 対話モード フローコントロール
- [x] 起動時ロックチェック
- [x] Phase 1a 実行 → 確認プロンプト
- [x] Phase 1b 実行 → 確認プロンプト
- [x] Phase 1c 実行 → 確認プロンプト
- [x] Phase 2 実行 → 確認プロンプト
- [x] Phase 3 実行 → 確認プロンプト
- [x] Phase 4 説明（ユーザー確認期間）
- [x] Phase 5a 実行 → 確認プロンプト
- [x] Phase 5b 実行（オプション） → 確認プロンプト
- [x] 終了時ロック削除

### 5.2 レポート表示
- [x] Phase 1a サマリー表示
  - [x] ファイル数、日付範囲
  - [x] 警告リスト
- [x] Phase 1b サマリー表示
  - [x] ハッシュ計算数、スキップ数
  - [x] 削減時間
- [x] Phase 1c サマリー表示
  - [x] 重複検出結果
  - [x] 統計情報
- [x] Phase 2 計画表示
  - [x] 移動ファイル数
  - [x] スキップファイル数
  - [x] 必要容量
- [x] Phase 3 結果表示
  - [x] 成功/失敗数
- [x] Phase 5 削除対象表示

---

## Phase 6: テスト・デバッグ

### 6.1 単体テスト
- [ ] metadata.py テスト
  - [ ] EXIF抽出テスト（各形式）
  - [ ] 動画メタデータテスト
  - [ ] フォールバックテスト
- [ ] network.py テスト
  - [ ] リトライ機構テスト
  - [ ] タイムアウトテスト
- [ ] lock.py テスト
  - [ ] ロック取得・解放テスト
  - [ ] 24時間判定テスト
- [ ] scanner.py テスト
  - [ ] サイズグループ化テスト
  - [ ] ハッシュ計算テスト
- [ ] planner.py テスト
  - [ ] ファイル名生成テスト
  - [ ] 連番テスト
- [ ] organizer.py テスト
  - [ ] コピー・検証テスト

### 6.2 統合テスト
- [ ] 初回実行テスト
  - [ ] 少量ファイル（10件）
  - [ ] 中量ファイル（100件）
- [ ] 2回目以降実行テスト
  - [ ] 既存ファイルとの連番
  - [ ] 重複検出
- [ ] 中断・再開テスト
  - [ ] チェックポイントからの再開
- [ ] エラーハンドリングテスト
  - [ ] ネットワークエラー
  - [ ] ファイル読み取りエラー
- [ ] ロックファイルテスト
  - [ ] 二重起動防止
  - [ ] 24時間自動削除

### 6.3 実環境テスト
- [ ] 実際のNASで動作確認
- [ ] 大量ファイル（1000件以上）でテスト
- [ ] 長時間処理の安定性確認
- [ ] メモリ使用量確認

---

## Phase 7: ドキュメント・リリース準備

### 7.1 ドキュメント整備
- [x] SPECIFICATION.md 完成
- [x] README.md 完成
- [x] TODO.md 完成（このファイル）
- [ ] DEVELOPMENT.md 完成
- [ ] CHANGELOG.md 作成
- [ ] コード内コメント追加
- [ ] docstring 追加

### 7.2 リリース準備
- [ ] バージョン番号設定（v1.0.0）
- [ ] ライセンス決定・追加
- [ ] config.json サンプル作成
- [ ] インストール手順確認
- [ ] トラブルシューティング追加

---

## 優先度付き タスク

### 🔴 High Priority（最優先）
1. [ ] 基本構造セットアップ
2. [ ] metadata.py 実装
3. [ ] scanner.py（Phase 1a）実装
4. [ ] 対話モード基本フロー

### 🟡 Medium Priority（重要）
5. [ ] network.py（リトライ機構）実装
6. [ ] scanner.py（Phase 1b, 1c）実装
7. [ ] planner.py 実装
8. [ ] organizer.py 実装
9. [ ] lock.py 実装

### 🟢 Low Priority（後回し可）
10. [ ] cleaner.py 実装
11. [ ] 単体テスト
12. [ ] ドキュメント整備

---

## マイルストーン

### Milestone 1: 基本スキャン機能（1週間）
- [ ] Phase 1a（メタデータスキャン）動作
- [ ] レポート出力確認

### Milestone 2: 重複検出機能（1週間）
- [ ] Phase 1b（ハッシュ計算）動作
- [ ] Phase 1c（分析）動作
- [ ] 最適化効果確認

### Milestone 3: 整理機能（1週間）
- [ ] Phase 2（計画）動作
- [ ] Phase 3（実行）動作
- [ ] ネットワーク安定性確認

### Milestone 4: 完成（1週間）
- [ ] Phase 5（クリーンアップ）動作
- [ ] 対話モード完成
- [ ] 実環境テスト完了
- [ ] v1.0 リリース

---

## 既知の課題・検討事項

### 技術的課題
- [ ] HEIC形式の互換性確認（pillow-heif）
- [ ] 大容量動画ファイルのハッシュ計算時間
- [ ] メモリ使用量の最適化（大量ファイル時）

### 機能追加検討
- [ ] プログレスバーの詳細表示
- [ ] エラー時の自動リトライ回数調整
- [ ] ログレベル設定（DEBUG, INFO, WARNING）

### v2.0 以降の検討
- [ ] プロジェクト管理機能
- [ ] インデックスファイル（高速化）
- [ ] Web UI
- [ ] AI タグ付け

---

## 進捗記録

- 2025-01-XX: プロジェクト開始、仕様策定完了
- 2025-01-XX: （今後の進捗を記録）
