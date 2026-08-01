# Anaplan Skill

Anaplanのワークスペース履歴監査（History Audit）とモデル解析（Model Analyzer）を行うスキルです。Polarsによるデータ処理と、Streamlitベースの依存関係可視化ダッシュボードを提供します。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | スキルの目的と主要機能の概要 |
| [libs/history_audit/README.md](libs/history_audit/README.md) | History Auditシステムの詳細（一部、現行のPolars実装より古い記述を含む） |
| [libs/history_audit/CONFIGURATION.md](libs/history_audit/CONFIGURATION.md) | モデル設定の追加方法・認証情報の管理方法 |
| [libs/history_audit/PERFORMANCE_OPTIMIZATION.md](libs/history_audit/PERFORMANCE_OPTIMIZATION.md) | チャンク処理・並列処理の最適化手法の説明 |
| [libs/history_audit/config.example.py](libs/history_audit/config.example.py) | 設定ファイルのサンプル（`config.py`としてコピーして使用） |

## Quick Start

```bash
uv sync
```

History Auditを使う場合は、設定ファイルをコピーして編集します（スクリプトと同じディレクトリに置く必要があります）。

```bash
copy libs\history_audit\config.example.py libs\history_audit\config.py
```

認証情報は環境変数または`.env`ファイル（python-dotenv経由）で渡します。

- `ANAPLAN_USER`（または`ANAPLAN_USERNAME`）: Anaplanログインメールアドレス
- `ANAPLAN_PASSWORD`: Anaplanパスワード
- `ANAPLAN_WS` / `ANAPLAN_MODEL`: Model Analyzerダッシュボードのサイドバー初期値（省略可、画面から入力も可）
- `GEMINI_API_KEY`: Model Analyzerの「AIでPLANS原則違反を監査する」機能を使う場合のみ必須

## 主要コマンド

```bash
# 履歴監査データをAnaplanから取得し、サマリーCSVとHTMLダッシュボードを生成
uv run python libs/history_audit/HistoryAudit_Scheduled.py

# 既存のサマリーCSVからHTMLダッシュボードのみを再生成
uv run python libs/history_audit/generate_dashboard.py [CSV_PATH]
#   CSV_PATH省略時は ./HistoryAudit 内の最新の *all_summary.csv を自動選択

# モデル解析・依存関係可視化ダッシュボードを起動（Streamlit UI、CLI引数なし）
uv run streamlit run libs/model_analyzer/dashboard.py

# テスト実行
uv run pytest
```

## Highlights

- **History Auditはconfig.py駆動** — `MODELS`リストに`ModelConfig(ws_id, m_id, action_id, file_suffix, users_csv, model_name)`を複数登録すると、`ProcessPoolExecutor`（`MAX_WORKERS`、デフォルト`min(CPU数, 4)`）でモデルごとに並列エクスポート・集計する。
- **大規模TSVはPolarsの遅延評価で処理** — `pl.scan_csv`によるlazy scanでユーザー別アクション数を集計し、`Users.csv`と左結合してモデル別・全体サマリーCSVを出力する。
- **Model Analyzerは12タブ構成** — Module Network / Line Item Network / Matrices / Modules / Lists / Line Items / Imports / Processes / Exports / Actions / Model Diff / Capacityで、モジュール・ラインアイテム・リスト・アクション類のメタデータをそれぞれ検索・閲覧できる。
- **依存関係グラフは確定情報と推論情報を線種で区別** — 実線はAPIメタデータから確定した関係（`referenced_by`・`executes`・`reads_from`）、点線はインポート名とモジュール名の一致から推論した`updates (inferred)`関係。
- **ノード色はモジュール名のMD5ハッシュから決定的に生成** — 同じモジュールは再描画しても常に同じ色になり、既知の種別（Module/Process/Import/Data Source）は固定色を使用。巨大なLine Item Networkは検索必須＋1000ノード超で警告し、ボタン押下でHTML生成・ダウンロードして別ブラウザで開く運用に退避できる。
- **Model Diffタブでベース/比較先モデルをオンザフライ比較** — Polarsの`full`ジョインでModules/Lists/Line Itemsのメタデータ差分をAdded/Removed/Modified/Unchangedに分類する。
- **Capacityタブで容量推定と最適化候補を検出** — セル数×8バイトの簡易計算でモジュール別メモリ消費を推定し、`formula`が空かつ`summary != "None"`かつ`appliesTo`が非空のLine Itemを「Summary OFF」最適化候補として抽出する。
- **AI監査は任意機能** — 表示中の数式（50件以下）をGemini（`gemini-3-flash-preview`）に送信し、PLANS原則（長すぎるIF文・TEXT結合の乱用・不必要なLOOKUP等）違反を診断する。`GEMINI_API_KEY`未設定時はエラーメッセージを返すのみで他機能に影響しない。
- **Excel仕様書出力** — `xlsxwriter`でModules/Lists/LineItems/各Action種別をシート分けしたExcelファイルをダウンロードボタンから取得できる。

## 実行例

```bash
uv sync
copy libs\history_audit\config.example.py libs\history_audit\config.py
# config.py を編集してws_id/m_id/action_idなどを設定
uv run python libs/history_audit/HistoryAudit_Scheduled.py
```

出力例（`./HistoryAudit/`配下）:
```
20260801all_summary.csv
20260801all_summary_dashboard.html
```

Model Analyzerダッシュボードを起動する場合:
```bash
uv run streamlit run libs/model_analyzer/dashboard.py
```
ブラウザが開いたら、サイドバーでWorkspace ID / Model IDを入力し、各タブでモジュール間依存関係やライン別アイテムの検索・Excel出力・AI監査を行う。
