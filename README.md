# NAS写真・動画整理ツール

家族でスマホ等で撮った写真・動画をNASに保存し、撮影日時ベースで体系的に整理するツールです。

## 特徴

- 📅 **撮影日時ベースの整理**: `YYYYMMDDhhmmss-NN`形式で自動リネーム
- 🔍 **重複検出**: ハッシュ計算による確実な重複ファイル検出
- ⚡ **最適化**: サイズベースフィルタリングで処理時間を大幅削減
- 🔒 **安全性**: コピー→確認→削除の段階的処理
- 💬 **対話モード**: 各段階で確認しながら進行
- 🔄 **再開可能**: 処理中断時もチェックポイントから再開

## 対応ファイル形式

### 画像
- JPEG (`.jpg`, `.jpeg`)
- HEIC (`.heic`) - iPhone Live Photos含む
- PNG (`.png`)

### 動画
- MP4 (`.mp4`) - iPhone/Android共通
- MOV (`.mov`) - iPhone標準
- 3GP (`.3gp`) - Android（古い機種）
- M4V (`.m4v`) - iPhone

## システム要件

- Python 3.8以上
- NASへのSMB/CIFS接続
- Windows / macOS / Linux

## セットアップ

### 1. リポジトリのクローン
```bash
git clone <repository-url>
cd photo-organizer
```

### 2. 仮想環境の作成（推奨）
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 3. 依存ライブラリのインストール
```bash
pip install -r requirements.txt
```

### 4. 設定ファイルの作成
`config.json`を編集して、NASのパスを設定してください。

```json
{
  "paths": {
    "source_dir": "Z:/Photos/source",      # 整理前のファイル置き場
    "organized_dir": "Z:/Photos/organized", # 整理後の保存先
    "workspace_dir": "C:/photo-organizer"   # ローカル作業ディレクトリ
  }
}
```

## 使い方

### 基本的な実行フロー

#### 1. ファイルの準備
スマホから撮った写真・動画を `source/` フォルダに配置します。

```
Z:/Photos/source/
├── IMG_1234.jpg
├── VID_5678.mp4
└── ...
```

#### 2. プログラムの実行
```bash
python organize.py
```

#### 3. 対話モードに従って進行
プログラムが段階的に確認しながら進みます：

```
Phase 1a: メタデータ抽出
↓ [確認]
Phase 1b: ハッシュ計算
↓ [確認]
Phase 1c: 分析
↓ [確認]
Phase 2: 整理計画（Dry-run）
↓ [確認]
Phase 3: 整理実行
↓ [確認]
Phase 4: ユーザー確認期間（手動）
↓
Phase 5a: オリジナル削除
↓ [確認]
Phase 5b: 重複削除（オプション）
```

#### 4. 整理結果の確認（Phase 4）
プログラムが一旦終了するので、`organized/` フォルダを確認します。

```
Z:/Photos/organized/
├── 2023/
├── 2024/
│   ├── 20241215143022-01.jpg
│   ├── 20241215143022-02.mp4
│   └── ...
└── 2025/
```

#### 5. クリーンアップ（Phase 5）
確認後、プログラムを再実行して元ファイルを削除します。

### 2回目以降の実行
新しいファイルを `source/` に追加して、同じように実行するだけです。
既存の整理済みファイルとの重複チェックや連番調整は自動で行われます。

## ディレクトリ構成

```
photo-organizer/
├── organize.py              # メインスクリプト
├── config.json              # 設定ファイル
├── requirements.txt         # 依存ライブラリ
├── README.md                # このファイル
├── SPECIFICATION.md         # 詳細仕様書
├── TODO.md                  # 開発タスク
├── DEVELOPMENT.md           # 開発者ガイド
│
├── modules/                 # プログラムモジュール
│   ├── __init__.py
│   ├── scanner.py
│   ├── planner.py
│   ├── organizer.py
│   ├── cleaner.py
│   ├── metadata.py
│   ├── network.py
│   ├── lock.py
│   └── utils.py
│
├── checkpoints/             # 処理状態の保存
├── reports/                 # レポート出力
└── tests/                   # テスト（将来）
```

## トラブルシューティング

### ロックファイルエラー
```
エラー: 既に処理が実行中、または前回異常終了した可能性があります
```

**対処方法**:
1. 他のPCやプロセスで実行していないか確認
2. 実行していない場合は、`organized/.photo-organizer.lock` を削除
3. プログラムを再実行

### 処理が中断した
チェックポイント機能により、再実行すると自動的に続きから再開されます。

### NAS接続エラーが頻発する
`config.json` の `network` セクションで調整できます：
```json
{
  "network": {
    "retry_count": 5,        # リトライ回数を増やす
    "retry_delay": 10,       # リトライ間隔を延ばす
    "batch_size": 25         # バッチサイズを小さくする
  }
}
```

### HEIC形式が読めない
`pillow-heif` のインストールを確認してください：
```bash
pip install pillow-heif
```

## レポートファイル

処理中に生成されるレポートファイル：

- `metadata_report.json`: 全ファイルのメタデータ
- `hash_report.json`: ハッシュ計算結果
- `analysis_report.json`: 分析結果（統合）
- `duplicates.txt`: 重複ファイルリスト
- `organize_plan.txt`: 整理計画
- `organize_log.json`: 整理実行ログ

これらは `workspace_dir/reports/` に保存されます。

## 制限事項（v1.0）

- 単一ソースディレクトリのみ対応
- データベース未使用（ファイル名ベース）
- 並列処理なし
- 対話モード専用

## 将来の拡張予定（v2.0以降）

- [ ] プロジェクト管理機能（複数ソース対応）
- [ ] Web閲覧インターフェース
- [ ] AIタグ付け機能
- [ ] サムネイル生成
- [ ] 並列処理オプション

## ライセンス

（ライセンスを追加してください）

## 作者

（作者情報を追加してください）

## 参考資料

- [詳細仕様書](SPECIFICATION.md)
- [開発者ガイド](DEVELOPMENT.md)
- [開発タスク](TODO.md)
