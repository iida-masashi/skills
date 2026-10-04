# claude-gemini-skills

Claude Code と Gemini CLI の両方から共有して使う、自作エージェントスキル集。

## 構成

各サブフォルダが1つのスキル。`SKILL.md`（フロントマターに `name`/`description`）が本体。エージェントは`description`を見て自動的にスキルを発見・適用するため、通常は明示的に呼び出す必要はない。

いずれのSKILL.mdも `<vault>`、`<quartz-repo>`、`<convmd-repo>`、`<your-org>/<your-repo>` のようなプレースホルダを含む。自分の環境の実パス・リポジトリ名に置き換えて使う。

### Obsidian Vault連携系

| スキル | 使う場面 | 前提条件 |
|---|---|---|
| [`convmd`](./convmd/) | Web記事（Zenn/Qiita/note/X/Wikipedia/GitHub/Reddit/はてな/Substack/Medium等）・動画/音声・ローカルOffice/PDFファイルをObsidian向けMarkdownに変換・取り込みたいとき | convMD CLI（`<convmd-repo>`、uv管理）。機能別に`GEMINI_API_KEY`（OCR/自動リンク）、`XAI_API_KEY`（X/Twitter）、`uv sync --extra whisper`+FFmpeg（音声文字起こし）、pandoc（epub/pdf/docx変換） |
| [`vault-publish`](./vault-publish/) | 阿波説(awa)・宗教研究(religion)・業務ソリューション調査(solution)・CPG統合ナレッジ(cpg) の各Vaultを、Quartz経由で公開（sync→build検証→commit→push）したいとき。公開先は GitHub Pages、cpg は GitHub Actions 経由の Cloudflare Pages。`--sync-only`でcommit/pushせずローカル同期・ビルド確認・プレビューだけも可（旧`vault-sync`スキルはこれに統合され廃止済み） | Vault側の同期スクリプト、Node.js/npx（`quartz build`）、対象Quartzリポジトリ、`gh` CLI（任意） |
| [`mermaid-hygiene`](./mermaid-hygiene/) | Vault/Quartz の Mermaid 図の構文エラー（Mermaid 11 のレキサー制約、subgraph ID の記号、`%%` コメント等）と、暗い背景色のノードの文字色コントラストを検査したいとき | Python（`scripts/validate_mermaid.py` にファイルまたはフォルダを渡す） |
| [`vault-api`](./vault-api/) | Obsidian Local REST API経由でVaultを直接操作（全文検索・読み取り・一覧・追記・見出し挿入・リネーム・削除）、または孤立ノート/薄ノート検出等のメンテナンスをしたいとき | Obsidian本体起動中＋Local REST APIプラグイン、PowerShell 7（`pwsh`、UTF-8対応）、`_secrets/obsidian.json`にAPIキー設定（孤立ノート/薄ノート検出等のメンテナンスツールはAPI不要、対象Vaultパスの指定が必要） |
| [`shrine-note-template`](./shrine-note-template/) | 神社・神格の専門ノートを標準12セクション構造で新規作成したいとき | 特になし（テンプレ・ガイドラインのみ）。作成後の検証に`vault-verify-notes.ps1`（任意） |
| [`essay-note-template`](./essay-note-template/) | 神格論・氏族論・伝承等の論考型ノートを新規作成・整備したいとき（shrine-note-templateの論考版） | 特になし。検証に`vault-verify-notes.ps1`（任意） |
| [`religion-research`](./religion-research/) | 宗教（天理教・その分派異端運動等）・食文化（郷土料理・儀礼食）・音楽（民族音楽・伝承歌謡）・土着の民族文化（親族制度・通過儀礼）を文化人類学的に調査し、宗教研究Vault（`religion-garden`）に構造化ノートを構築・維持したいとき | 特になし（指示書のみ、スクリプトは持たない）。領域別の詳細は`references/`配下（religion/food/music/ethnic-culture） |

### 業務分析・データ処理系

| スキル | 使う場面 | 前提条件 |
|---|---|---|
| [`anaplan-skill`](./anaplan-skill/) | Anaplanの履歴監査（ユーザーアクティビティ分析）やモデル構造解析・依存関係可視化を行いたいとき | `uv`（venv構築）、Polars/NetworkX/PyVis等、`ANAPLAN_USER`/`ANAPLAN_PASSWORD`環境変数、streamlit（ダッシュボード） |
| [`promo-forecast-skill`](./promo-forecast-skill/) | 販売実績から定番需要と販促リフトを分解し、LightGBMで需要予測・ROI分析・価格弾力性・What-Ifシミュレーションを行いたいとき | Python（LightGBM等）、streamlit（ダッシュボード） |
| [`consultant-toolkit`](./consultant-toolkit/) | コンサル向け財務データ取得・SCM/財務ダッシュボード生成、企業分析レポート、ERP PMO自動化を行いたいとき | `pip install -e .`でパッケージインストール、yfinance、Prophet、streamlit。事前に`references/scripts_usage.md`を読む |
| [`pe-market-research`](./pe-market-research/) | PE投資先候補調査（プレイヤーマップ構築→資本構造・株主確認→M&A/OEM適性評価→ファクトチェック）を業界横断で行いたいとき | Workflowツール（`market_map_workflow.js`をagent実行）、WebSearch/WebFetch相当のツールアクセス |
| [`solution-market-research`](./solution-market-research/) | 特定機能領域（WMS/TMS/ERP/MES/CRM等）向けのソフトウェア/システムソリューションを業界横断で調査し、RFP候補一覧・ベンダー比較表・Fit/Gap適合度マトリクスを作りたいとき。AI生成の既存調査資料の裏取り・ハルシネーション（実在しない製品名等）チェックにも使う | `web-search`スキル |
| [`value-chain-research`](./value-chain-research/) | 業界のバリューチェーン/サプライチェーン構造（組織ガバナンス、S&OP等のプロセス、企業別ITスタック、学術論文サーベイ、地域権限分界）を体系調査したいとき | `web-search`スキル |

### 開発・レビュー系

| スキル | 使う場面 | 前提条件 |
|---|---|---|
| [`deliverable-review`](./deliverable-review/) | クライアント提出前のPowerPoint/Word/PDFを自己点検（情報漏洩・AI生成痕跡・数値整合性・コンサルスタイル・戦略の質）し、メタデータを消したサニタイズ版を作りたいとき。Claude Code からは CLI＋Claude 自身の定性レビュー、ブラウザからは Cloud Run の Web UI（Gemini 3.8 Flash 定性レビュー既定ON） | Python 3.14（`python-pptx`/`python-docx`/`pdfplumber`/`pypdf`/`lxml`等をrequirements.txtからインストール）。Web UI の Gemini 定性レビュー利用時のみ`GOOGLE_API_KEY` |
| [`python-safe-coding`](./python-safe-coding/) | Pythonコードを安全にリファクタリングし、厳格な型チェック・統一品質ゲート（`psc`）を通したいとき | `psc` CLI、Ruff、MyPy、pytest+coverage、uv、Bandit。Polars必須（pandas禁止方針） |
| [`context-compression-skill`](./context-compression-skill/) | ビルド・テスト・巨大ファイル・表データ・広域検索・Web調査など大量出力をコンテキストに入れる前に圧縮したいとき（中核ルールはグローバル CLAUDE.md / GEMINI.md に常駐、本スキルは詳細版） | なし |
| [`api-orchestrator`](./api-orchestrator/) | Gemini API と Grok (xAI) API の呼び出しを一本化し、`--provider`での切替・相互フォールバック・動的モデル選択・リトライ・Web検索・MCP経由のツール呼び出しを行いたいとき | `pip install -r requirements.txt`、`.env`に`GOOGLE_API_KEY`（or `GEMINI_API_KEY`）と`XAI_API_KEY`（片方のみでも可）、MCPサーバー起動用にNode.js（npx）・`uv`（uvx） |
| [`web-search`](./web-search/) | Web検索・URL取得を行いたいとき（標準でGemini API優先、失敗時はClaudeネイティブのWebSearch/WebFetchにフォールバック） | `<gemini-scripts-dir>`に`gemini_websearch.py`/`gemini_webfetch.py`と`.env`、`convMD` uvプロジェクトが別途必要 |
| [`gcp-docker-deploy`](./gcp-docker-deploy/) | Dockerizedアプリ（Streamlit/FastAPI/Node.js等）をGitHub Actions経由でGoogle Cloud（Cloud RunまたはVM）にデプロイしたいとき、Cloud Run/VMの選定に迷うとき、WIF/サービスアカウント鍵のどちらで認証するか決めたいとき | `gcloud`/`gh` CLI、Artifact Registry、Workload Identity Federation設定（またはサービスアカウントJSON鍵）。手順のみでスクリプトは持たない |

## 自動デプロイ（GitHub Actions）

GitHub Actions はリポジトリ直下の `.github/workflows/` だけを実行する（スキルのサブフォルダ内に置いた workflow は動かない）。各 workflow は `paths` で対象スキルのフォルダに絞っている。

| workflow | 対象 | デプロイ先 | 認証 |
|---|---|---|---|
| `anaplan-skill-deploy.yml` | `anaplan-skill/**` | Cloud Run `anaplan-model-analyzer` | Workload Identity Federation |
| `deliverable-review-deploy.yml` | `deliverable-review/**` | Cloud Run `deliverable-review`（pytest 通過後にビルド・デプロイ） | Workload Identity Federation |

WIF 用のリポジトリ Secrets（`GCP_WIF_PROVIDER` / `GCP_DEPLOYER_SA`）は両 workflow で共通。

## 両ツールから使う仕組み

Claude Code は `~/.claude/skills/<name>/`、Gemini CLI は `~/.gemini/skills/<name>/` をそれぞれ個人スキルディレクトリとして読む。このリポジトリはその実体を1箇所（ここ）に集約し、両方のディレクトリからWindowsのディレクトリジャンクション（`mklink /J`）で参照させることで、片方を編集すれば両方に反映される状態にしている。

### セットアップ（新しい環境での復元）

```bat
git clone https://github.com/iida-masashi/skills.git C:\Users\<you>\claude-gemini-skills

for /D %s in ("C:\Users\<you>\claude-gemini-skills\*") do (
  mklink /J "C:\Users\<you>\.claude\skills\%~ns" "%s"
  mklink /J "C:\Users\<you>\.gemini\skills\%~ns" "%s"
)
```

（`.git`・`.github`フォルダもマッチしてしまうので、その行だけエラーが出るか不要なリンクができる。気になる場合は`for /D %s in (...) do if not "%~ns"==".git" if not "%~ns"==".github" (...)`のように除外するか、個別に列挙する。）

`mklink /J`（junction）は管理者権限不要。`/D`（シンボリックリンク）は管理者権限が必要なため使っていない。

確認方法:

```bat
fsutil reparsepoint query "C:\Users\<you>\.claude\skills\convmd"
```

`Reparse Tag: Mount Point` と、実体のパスが表示されれば正しくリンクされている。
