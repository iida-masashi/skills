# claude-gemini-skills

Claude Code と Gemini CLI の両方から共有して使う、自作エージェントスキル集。

## 構成

各サブフォルダが1つのスキル。`SKILL.md`（フロントマターに `name`/`description`）が本体。エージェントは`description`を見て自動的にスキルを発見・適用するため、通常は明示的に呼び出す必要はない。

いずれのSKILL.mdも `<vault>`、`<quartz-repo>`、`<convmd-repo>`、`<your-org>/<your-repo>` のようなプレースホルダを含む。自分の環境の実パス・リポジトリ名に置き換えて使う。

### Obsidian Vault連携系

| スキル | 使う場面 | 前提条件 |
|---|---|---|
| [`convmd`](./convmd/) | Web記事（Zenn/Qiita/note/X/Wikipedia/GitHub/Reddit/はてな/Substack/Medium等）・動画/音声・ローカルOffice/PDFファイルをObsidian向けMarkdownに変換・取り込みたいとき | convMD CLI（`<convmd-repo>`、uv管理）。機能別に`GEMINI_API_KEY`（OCR/自動リンク）、`XAI_API_KEY`（X/Twitter）、`uv sync --extra whisper`+FFmpeg（音声文字起こし）、pandoc（epub/pdf/docx変換） |
| [`awa-publish`](./awa-publish/) | Obsidian Vault → Quartz → GitHub Pagesへの公開パイプライン（sync→build検証→commit→push）をワンステップで実行したいとき | `<vault>/_work/_sync_to_quartz.py`、Node.js/npx（`quartz build`）、Gitリポジトリ（`<quartz-repo>`）、`gh` CLI（任意） |
| [`awa-sync`](./awa-sync/) | commit/pushせず、Vault→Quartzのローカル同期とビルド確認・プレビューだけしたいとき | awa-publishと同じ（`_sync_to_quartz.py`、npx/quartz build）。git操作は不要 |
| [`vault-api`](./vault-api/) | Obsidian Local REST API経由でVaultを直接操作（全文検索・読み取り・一覧・追記・見出し挿入・リネーム・削除）、または孤立ノート/薄ノート検出等のメンテナンスをしたいとき | Obsidian本体起動中＋Local REST APIプラグイン、PowerShell 7（`pwsh`、UTF-8対応）、`_secrets/obsidian.json`にAPIキー設定（孤立ノート/薄ノート検出等のメンテナンスツールはAPI不要、対象Vaultパスの指定が必要） |
| [`shrine-note-template`](./shrine-note-template/) | 神社・神格の専門ノートを標準12セクション構造で新規作成したいとき | 特になし（テンプレ・ガイドラインのみ）。作成後の検証に`vault-verify-notes.ps1`（任意） |
| [`essay-note-template`](./essay-note-template/) | 神格論・氏族論・伝承等の論考型ノートを新規作成・整備したいとき（shrine-note-templateの論考版） | 特になし。検証に`vault-verify-notes.ps1`（任意） |

### 業務分析・データ処理系

| スキル | 使う場面 | 前提条件 |
|---|---|---|
| [`anaplan-skill`](./anaplan-skill/) | Anaplanの履歴監査（ユーザーアクティビティ分析）やモデル構造解析・依存関係可視化を行いたいとき | `uv`（venv構築）、Polars/NetworkX/PyVis等、`ANAPLAN_USER`/`ANAPLAN_PASSWORD`環境変数、streamlit（ダッシュボード） |
| [`promo-forecast-skill`](./promo-forecast-skill/) | 販売実績から定番需要と販促リフトを分解し、LightGBMで需要予測・ROI分析・価格弾力性・What-Ifシミュレーションを行いたいとき | Python（LightGBM等）、streamlit（ダッシュボード） |
| [`consultant-toolkit`](./consultant-toolkit/) | コンサル向け財務データ取得・SCM/財務ダッシュボード生成、企業分析レポート、ERP PMO自動化を行いたいとき | `pip install -e .`でパッケージインストール、yfinance、Prophet、streamlit。事前に`references/scripts_usage.md`を読む |
| [`pe-market-research`](./pe-market-research/) | PE投資先候補調査（プレイヤーマップ構築→資本構造・株主確認→M&A/OEM適性評価→ファクトチェック）を業界横断で行いたいとき | Workflowツール（`market_map_workflow.js`をagent実行）、WebSearch/WebFetch相当のツールアクセス |

### 開発・レビュー系

| スキル | 使う場面 | 前提条件 |
|---|---|---|
| [`deliverable-review`](./deliverable-review/) | クライアント提出前のPowerPoint/Word/PDFを自己点検（情報漏洩・AI生成痕跡・数値整合性・コンサルスタイル・戦略の質）したいとき | Python（`python-pptx`/`python-docx`/`pdfplumber`/`pypdf`等をrequirements.txtからインストール）。Gemini定性レビュー利用時のみ`GOOGLE_API_KEY` |
| [`python-safe-coding`](./python-safe-coding/) | Pythonコードを安全にリファクタリングし、厳格な型チェック・統一品質ゲート（`psc`）を通したいとき | `psc` CLI、Ruff、MyPy、pytest+coverage、uv、Bandit。Polars必須（pandas禁止方針） |
| [`context-compression-skill`](./context-compression-skill/) | シェルコマンド・検索・ファイル読み込みの出力をコンテキストに入れる前に圧縮・フィルタしたいとき（常時適用の作法スキル） | なし |

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

（`.git`フォルダもマッチしてしまうので、その行だけエラーが出るが無視してよい。気になる場合は1行ずつ`for /D %s in (...) do if not "%~ns"==".git" (...)`のように除外するか、個別に列挙する。）

`mklink /J`（junction）は管理者権限不要。`/D`（シンボリックリンク）は管理者権限が必要なため使っていない。

確認方法:

```bat
fsutil reparsepoint query "C:\Users\<you>\.claude\skills\convmd"
```

`Reparse Tag: Mount Point` と、実体のパスが表示されれば正しくリンクされている。
