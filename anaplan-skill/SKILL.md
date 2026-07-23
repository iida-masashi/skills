---
name: anaplan-skill
description: Anaplan integration suite for workspace history auditing and model analysis. Refactored for Gemini 3 Architecture and Polars.
---

# Anaplan Skill

Anaplanを中心としたSCM業務（監査、データ連携、モデル解析）を自動化するスキルです。**Gemini 3 Architecture** および **Polars** に完全準拠しています。

## 🚀 主要機能

### 1. 履歴監査システム (History Audit)
Anaplanの履歴監査データを取得し、ユーザーアクティビティを分析・可視化します。
- **データ処理**: Polarsを用いた爆速集計。
- **メインスクリプト**: `libs/history_audit/HistoryAudit_Scheduled.py`
- **ダッシュボード生成**: `uv run python libs/history_audit/generate_dashboard.py`

### 2. モデル解析と可視化 (Model Analyzer)
Anaplanモデルからモジュール、リスト、ラインアイテム等のメタデータを抽出し、依存関係をネットワークグラフとしてインタラクティブに可視化します。不要なリストの特定やモデル構造のリファクタリングに活用できます。
- **データ処理**: Polars, NetworkX, PyVis を組み合わせた依存関係抽出。
- **メインモジュール**: `libs/model_analyzer/analyzer.py`
- **ダッシュボード**: `uv run streamlit run libs/model_analyzer/dashboard.py`

## 🛠️ セットアップと構成 (uv必須)

### 環境構築
旧来の `pip` は使用せず、必ず `uv` を使用して環境構築を行ってください。

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

### 認証情報
以下の環境変数または `.env` ファイルが必要です。
- `ANAPLAN_USER`: Anaplanログインメールアドレス
- `ANAPLAN_PASSWORD`: Anaplanパスワード

## 💡 使用例

### 監査ログを取得してレポートを生成する場合
1. `uv run python libs/history_audit/HistoryAudit_Scheduled.py` を実行。
2. 生成された `HistoryAudit/*_dashboard.html` をブラウザで確認。

### モデル解析ダッシュボードを確認する場合
1. `uv run streamlit run libs/model_analyzer/dashboard.py` でダッシュボードを起動。

---
*Created by SCM Gal Engineer - Refactored for 2026 Edition*
