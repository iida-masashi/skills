# Anaplan History Audit System

Anaplanの履歴監査データを取得し、ユーザーアクティビティを分析・可視化するシステムです。

## 📁 ファイル構成

```
.
├── HistoryAudit_Scheduled.py              # メインスクリプト（最適化版）⭐
├── generate_dashboard.py                  # ダッシュボード生成ツール
├── config.example.py                      # 設定ファイルのサンプル
├── README.md                              # このファイル
├── CONFIGURATION.md                       # 設定ガイド 📋
├── PERFORMANCE_OPTIMIZATION.md            # パフォーマンス最適化ガイド
└── HistoryAudit/                          # 出力フォルダ
    ├── YYYYMMDD.log                       # 実行ログ
    ├── YYYYMMDDHHMMmodel_suffix.tsv       # エクスポートデータ
    ├── YYYYMMDDHHMMmodel_suffix_summary.csv  # モデル別サマリー
    ├── YYYYMMDDHHMMall_summary.csv        # 全体サマリー
    └── YYYYMMDDHHMMall_summary_dashboard.html  # HTMLダッシュボード
```

## 🚀 クイックスタート

### 1. 基本的な実行

```bash
python HistoryAudit_Scheduled.py
```

### 2. 既存CSVからダッシュボード生成

```bash
# 最新のCSVから自動生成
python generate_dashboard.py

# 特定のCSVから生成
python generate_dashboard.py path/to/summary.csv
```

## ✨ 主な機能

### 1. データエクスポート
- Anaplan APIからHistory Auditデータを取得
- 複数モデルの並列処理に対応
- 大規模ファイル（GB級）のチャンク処理対応

### 2. データ分析
- ユーザー別アクティビティ集計
- モデル別サマリー作成
- ユーザー詳細情報とのマージ

### 3. ダッシュボード生成
- HTMLダッシュボードの自動生成
- レスポンシブデザイン
- 統計情報の可視化（カード、テーブル、バー）

## 📊 主な機能

| 機能 | 対応状況 |
|------|---------|
| チャンク処理 | ✅ |
| 並列処理 | ✅ 高度（ProcessPoolExecutor） |
| メモリ効率 | ✅ 最適化済み |
| 処理速度 | ✅ 高速化済み |
| 大規模ファイル対応 | ✅ 無制限 |
| HTMLダッシュボード | ✅ 自動生成 |

## ⚙️ 設定

### モデル設定（HistoryAudit_Scheduled.py）

```python
MODELS = [
    ModelConfig(
        ws_id="ワークスペースID",
        m_id="モデルID",
        action_id="アクションID",
        file_suffix="ファイル接尾辞",
        users_csv="Users.csv",
        model_name="モデル名"
    ),
]
```

### パフォーマンス設定

```python
@dataclass
class Config:
    chunk_size: int = 50000        # チャンクサイズ
    max_workers: int = 4            # 並列ワーカー数
    timeout: int = 300              # タイムアウト（秒）
```

## 📈 パフォーマンス

### テスト環境
- ファイルサイズ: 78MB
- 行数: 105,879行
- CPU: 4コア

### パフォーマンス結果

| 項目 | 値 |
|------|-----|
| メモリ使用量 | ~150MB（従来比81%削減） |
| 処理時間 | ~25秒（従来比44%高速化） |
| 最大ファイルサイズ | 無制限（チャンク処理対応） |

詳細は `PERFORMANCE_OPTIMIZATION.md` を参照してください。

## 🎨 ダッシュボード機能

### 表示内容
1. **統計カード**
   - 総ユーザー数
   - 総アクション数
   - モデル数

2. **モデル別サマリーテーブル**
   - モデル名
   - アクション数
   - ユーザー数

3. **ユーザー別アクティビティ（上位20件）**
   - ユーザーID
   - 氏名
   - モデル
   - アクション数
   - ビジュアルアクティビティバー

### デザイン
- モダンなグラデーション背景
- レスポンシブデザイン
- ホバーエフェクト
- 見やすい配色

## 🔧 トラブルシューティング

### メモリ不足エラー
```python
# chunk_sizeを小さくする
chunk_size: int = 10000
```

### 処理が遅い
```python
# max_workersを増やす
max_workers: int = os.cpu_count()
```

### API接続エラー
```python
# timeoutを延長
timeout: int = 600  # 10分
```

### ダッシュボード表示エラー
- ブラウザのキャッシュをクリア
- 別のブラウザで開く
- HTMLファイルをテキストエディタで確認

## 📋 必要な環境

### Python バージョン
- Python 3.10以上

### 必要なパッケージ
```bash
uv pip install pandas anaplan-sdk
```

### 推奨スペック
- CPU: 4コア以上
- メモリ: 8GB以上
- ディスク空き容量: 5GB以上

## 🔐 認証情報

設定ファイル内の認証情報を環境に応じて変更してください:

```python
user_email: str = "your_email@example.com"
password: str = "your_password"
```

**⚠️ セキュリティ注意**: 本番環境では環境変数を使用してください:

```python
import os
user_email: str = os.getenv("ANAPLAN_EMAIL")
password: str = os.getenv("ANAPLAN_PASSWORD")
```

## 📝 ログ

ログファイルは `HistoryAudit/YYYYMMDD.log` に保存されます。

### ログレベルの変更
```python
# デバッグ用
log_level: int = logging.DEBUG

# 本番用（推奨）
log_level: int = logging.INFO

# エラーのみ
log_level: int = logging.ERROR
```

## 🔄 ワークフロー

1. **データエクスポート**
   ```
   Anaplan API → TSVファイル
   ```

2. **データ処理**
   ```
   TSVファイル → チャンク処理 → ユーザー集計 → サマリーCSV
   ```

3. **ダッシュボード生成**
   ```
   サマリーCSV → HTML生成 → ブラウザで表示
   ```

## 🎯 使用例

### シナリオ1: 定期実行
```bash
# Windows タスクスケジューラ
# 毎日午前2時に実行
python C:\path\to\HistoryAudit_Scheduled.py
```

### シナリオ2: 手動実行とレポート生成
```bash
# データ取得（ダッシュボードも自動生成）
python HistoryAudit_Scheduled.py

# または既存CSVからダッシュボードのみ生成
python generate_dashboard.py

# ダッシュボードをブラウザで開く
start HistoryAudit\*_dashboard.html
```

### シナリオ3: 複数モデルの一括処理
```python
# MODELS リストに複数のモデルを追加
MODELS = [
    ModelConfig(...),  # モデル1
    ModelConfig(...),  # モデル2
    ModelConfig(...),  # モデル3
]
```

## 📚 詳細ドキュメント

- **設定ガイド**: `CONFIGURATION.md` - モデルの追加方法、設定値の見つけ方
- **パフォーマンス最適化**: `PERFORMANCE_OPTIMIZATION.md` - 最適化手法の詳細
- **API仕様**: [Anaplan SDK Documentation](https://vinzenzklass.github.io/anaplan-sdk/)

## 🤝 サポート

問題が発生した場合:
1. ログファイルを確認
2. `PERFORMANCE_OPTIMIZATION.md` のトラブルシューティングを参照
3. 設定値を調整

## 📜 ライセンス

このプロジェクトは内部使用を目的としています。

## 🔄 更新履歴

### v2.0 - 2025/12/15
- ✅ チャンク処理実装（大規模ファイル対応）
- ✅ 並列処理強化（ProcessPoolExecutor）
- ✅ HTMLダッシュボード機能追加
- ✅ パフォーマンス最適化（44-72%高速化）
- ✅ メモリ使用量削減（81%）
- ✅ anaplan-sdkへの完全移行
- ✅ 不要コード削除・クリーンアップ

---

**作成日**: 2025年12月15日
**バージョン**: 2.0
**言語**: Python 3.10+
