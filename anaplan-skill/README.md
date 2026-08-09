# Anaplan Skill

Anaplanのワークスペース履歴監査（History Audit）とモデル解析（Model Analyzer）を行うスキルです。Polarsによるデータ処理と、Streamlitベースの依存関係可視化ダッシュボードを提供します。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | スキルの目的と主要機能の概要 |
| [libs/history_audit/config.example.py](libs/history_audit/config.example.py) | 設定ファイルのサンプル（`config.py`としてコピーして使用） |
| [run_local.ps1](run_local.ps1) | Model Analyzerをローカルで起動するPowerShellスクリプト |
| [Dockerfile](Dockerfile) / [.github/workflows/anaplan-skill-deploy.yml](../.github/workflows/anaplan-skill-deploy.yml) | Cloud Runデプロイ用のコンテナ定義とGitHub Actionsワークフロー |

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

Model Analyzerには上記に加えてアプリ内ログイン画面（`streamlit-authenticator`）があり、以下3つの環境変数が必須です（未設定だとエラー表示で`st.stop()`）。これはAnaplan自体への認証情報とは別物で、「誰がこのダッシュボードを開けるか」を制御するものです。

- `APP_LOGIN_USER`: ログイン画面で使うユーザー名
- `APP_LOGIN_PASSWORD_HASH`: ログインパスワードのbcryptハッシュ（平文は保存しない）
- `APP_COOKIE_KEY`: 認証クッキーの署名鍵（再起動をまたいでログイン状態を保持するなら固定値にする）

`APP_LOGIN_PASSWORD_HASH`の生成方法:
```bash
uv run python -c "import streamlit_authenticator as stauth; print(stauth.Hasher.hash('好きなパスワード'))"
```

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
- **Model Analyzerは13タブ構成** — Module Network / Line Item Network / Matrices / Modules / Lists / Line Items / Imports / Processes / Exports / Actions / Model Diff / Capacity / Unused Objectsで、モジュール・ラインアイテム・リスト・アクション類のメタデータをそれぞれ検索・閲覧できる。
- **Unused Objectsタブは未使用候補をメタデータのみから検出** — List（`usedInAppliesTo`が空）、Line Item（`referencedBy`が空）、Process未組み込みのImport/Export/Action、参照も更新もされていないModuleの4種類をヒューリスティックで抽出する。レポート表示専用列やImport書き込み先は誤検知しうるため、削除前にAnaplan UI側での手動確認が必須（タブ内に警告文で明記）。
- **依存関係グラフは確定情報と推論情報を線種で区別** — 実線はAPIメタデータから確定した関係（`referenced_by`・`executes`・`reads_from`）、点線はインポート名とモジュール名の一致から推論した`updates (inferred)`関係。
- **ノード色はモジュール名のMD5ハッシュから決定的に生成** — 同じモジュールは再描画しても常に同じ色になり、既知の種別（Module/Process/Import/Data Source）は固定色を使用。巨大なLine Item Networkは検索必須＋1000ノード超で警告し、ボタン押下でHTML生成・ダウンロードして別ブラウザで開く運用に退避できる。
- **Model Diffタブでベース/比較先モデルをオンザフライ比較** — Polarsの`full`ジョインでModules/Lists/Line Itemsのメタデータ差分をAdded/Removed/Modified/Unchangedに分類する。
- **Capacityタブで容量推定と最適化候補を検出** — セル数×8バイトの簡易計算でモジュール別メモリ消費を推定し、`formula`が空かつ`summary != "None"`かつ`appliesTo`が非空のLine Itemを「Summary OFF」最適化候補として抽出する。
- **AI監査は任意機能** — 表示中の数式（50件以下）をGemini（`gemini-3-flash-preview`）に送信し、PLANS原則（長すぎるIF文・TEXT結合の乱用・不必要なLOOKUP等）違反を診断する。`GEMINI_API_KEY`未設定時はエラーメッセージを返すのみで他機能に影響しない。
- **Excel仕様書出力** — `xlsxwriter`でModules/Lists/LineItems/各Action種別をシート分けしたExcelファイルをダウンロードボタンから取得できる。

## DataFrame列の命名規則

`dashboard.py`/`analyzer.py`のPolars DataFrameでは、列名がcamelCase（例: `moduleName`, `cellCount`, `appliesTo`）とsnake_case（例: `line_item_count`, `estimated_size_mb`, `step_details`）に混在しているが、これは意図した区別である。

- **camelCase** = Anaplan APIのレスポンスをそのまま保持している列（キー名をリネームしない）
- **snake_case** = このコードがローカルで計算・導出した列（集計、フラグ、整形済みテキストなど）

新しい列を追加する際もこの区別に従うこと。API由来の列名を勝手にリネームしない（`Model Diff`タブの`compare_dataframes`呼び出しが列名をそのまま結合キーとして使っているため、リネームすると比較ロジックが壊れる）。

List[Struct]型の列（`appliesTo`など）をStreamlitの`st.dataframe`に渡す前は、`flatten_struct_list_columns`（`dashboard.py`）を必ず通す。素通しすると`to_pandas()`後にセルが`Object`としか表示されない。

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

Model Analyzerダッシュボードを起動する場合（`ANAPLAN_USER`/`ANAPLAN_PASSWORD`に加え、`APP_LOGIN_USER`/`APP_LOGIN_PASSWORD_HASH`/`APP_COOKIE_KEY`も環境変数に必要）:
```bash
uv run streamlit run libs/model_analyzer/dashboard.py
```
ブラウザが開くとまずログイン画面が表示される。`APP_LOGIN_USER`/`APP_LOGIN_PASSWORD_HASH`で設定したID/PASSでログイン後、サイドバーでWorkspace ID / Model IDを入力し、各タブでモジュール間依存関係やライン別アイテムの検索・Excel出力・AI監査を行う。

## ローカルでの起動（PowerShellスクリプト）

[run_local.ps1](run_local.ps1) は必要な環境変数が設定されていることを確認した上で `uv run streamlit run` を実行する。認証情報はスクリプトに埋め込まず、実行前に環境変数として渡す。

```powershell
$env:ANAPLAN_USER = "<Anaplanログインメールアドレス>"
$env:ANAPLAN_PASSWORD = "<Anaplanパスワード>"
$env:ANAPLAN_WS = "<Workspace ID>"       # 省略可、画面からも入力可
$env:ANAPLAN_MODEL = "<Model ID>"        # 省略可、画面からも入力可
$env:APP_LOGIN_USER = "<アプリログイン用ユーザー名>"
$env:APP_LOGIN_PASSWORD_HASH = "<bcryptハッシュ>"
$env:APP_COOKIE_KEY = "<任意の乱数文字列>"

pwsh -File "run_local.ps1"
```

`.env`ファイル（`ANAPLAN_USER="..."`のような形式）から読み込みたい場合は`-EnvFile`オプションを使う。

```powershell
pwsh -File "run_local.ps1" -EnvFile "<.envファイルへのパス>"
```

起動後、ターミナルに表示される `Local URL: http://localhost:8501` をブラウザで開く。停止は Ctrl+C。必要な環境変数が未設定の場合はエラーで一覧表示され、起動しない。

## Cloud Runへのデプロイ

`anaplan-skill/**`への変更を`main`ブランチにpushすると、[.github/workflows/anaplan-skill-deploy.yml](../.github/workflows/anaplan-skill-deploy.yml)（モノレポルート`claude-gemini-skills/.github/workflows/`に配置、GitHubはこの場所しか認識しない）が自動的にDockerイメージをビルドし、Google Cloud Run（サービス名 `anaplan-model-analyzer`、リージョン `asia-northeast1`）へデプロイする。

- **GCP↔GitHub Actions認証**: Workload Identity Federation（長期キー不要。プロジェクト`trim-opus-407712`の既存プール`github-pool`/プロバイダ`sera-provider`を再利用）
- **イメージ格納先**: 既存のArtifact Registryリポジトリ`apps`（`asia-northeast1`）
- **デプロイ用サービスアカウント**: `anaplan-skill-deployer@trim-opus-407712.iam.gserviceaccount.com`（Artifact Registry writer + Cloud Run admin）
- **ランタイム用サービスアカウント**: `anaplan-skill-runtime@trim-opus-407712.iam.gserviceaccount.com`（Secret Managerの各シークレットへのアクセス権のみ）
- **認証情報の受け渡し**: `ANAPLAN_USER`/`ANAPLAN_PASSWORD`/`ANAPLAN_WS`/`ANAPLAN_MODEL`/`APP_LOGIN_USER`/`APP_LOGIN_PASSWORD_HASH`/`APP_COOKIE_KEY`/`GEMINI_API_KEY`はすべてSecret Manager経由でCloud Runに注入。リポジトリやDockerイメージには一切含まれない
- **アクセス制御**: Cloud Run自体は`--allow-unauthenticated`（IAMは開放）。実際のセキュリティ境界はStreamlitアプリ内のログイン画面（`streamlit-authenticator`、`libs/model_analyzer/auth.py`）

デプロイ状況の確認:
```bash
gh run list --repo iida-masashi/skills --workflow=anaplan-skill-deploy.yml
gcloud run services describe anaplan-model-analyzer --region=asia-northeast1 --project=trim-opus-407712 --format='value(status.url)'
```

Secret Managerの値を更新する場合（例: アプリログインのパスワード変更）:
```bash
uv run python -c "import streamlit_authenticator as stauth; print(stauth.Hasher.hash('新しいパスワード'))"
# 出力されたハッシュを新バージョンとして登録
echo -n "<ハッシュ>" | gcloud secrets versions add APP_LOGIN_PASSWORD_HASH --data-file=- --project=trim-opus-407712
```
次回のデプロイ（またはリビジョンの再作成）で`:latest`が新バージョンを指すようになる。
