# claude-gemini-skills

Claude Code と Gemini CLI の両方から共有して使う、自作エージェントスキル集。

## 構成

各サブフォルダが1つのスキル。`SKILL.md`（フロントマターに `name`/`description`）が本体。

| スキル | 用途 |
|---|---|
| [`convmd`](./convmd/) | Web記事・SNS・動画/音声・デジタルアーカイブ・ローカルOffice/PDFファイルをObsidian向けMarkdownに変換するCLI（convMD）の呼び出し方の知識 |
| [`awa-publish`](./awa-publish/) | Obsidian Vault → Quartz → GitHub Pagesの公開パイプライン（sync→build検証→commit→push）をワンステップで実行 |
| [`awa-sync`](./awa-sync/) | 上記からcommit/pushを除いた、ローカル同期・プレビュー専用バリアント |
| [`deliverable-review`](./deliverable-review/) | クライアント納品前のPowerPoint/Word/PDF自己点検（情報漏洩・AI生成痕跡・正確性・コンサルスタイル・戦略の質の5〜6分類チェック） |
| [`anaplan-skill`](./anaplan-skill/) | Anaplan連携の需要予測パイプライン監査・モデル分析（Gemini 3アーキテクチャ・Polars対応） |
| [`promo-forecast-skill`](./promo-forecast-skill/) | 販売実績から定番需要と販促リフトを分解し、LightGBMハイブリッドモデルで需要予測・ROI分析・価格弾力性・What-Ifシミュレーションを行う |
| [`consultant-toolkit`](./consultant-toolkit/) | コンサルタント向け財務データ取得・AI駆動SCM/財務ダッシュボード・ERP PMO自動化ツールキット |
| [`python-safe-coding`](./python-safe-coding/) | AST基盤の安全なリファクタリング・厳格な型付け強制・統一品質ゲート（`psc`） |
| [`pe-market-research`](./pe-market-research/) | PE投資先候補調査向けの業界横断リサーチワークフロー（プレイヤー発見→資本構造検証→M&A適性評価→ファクトチェック） |
| [`vault-api`](./vault-api/) | Obsidian Local REST API経由でVaultを直接操作（全文検索・読み取り・一覧・追記・リネーム・削除） |
| [`vault-orphan-check`](./vault-orphan-check/) | Obsidian Vaultの孤立ノート（どこからもwikilinkされていないノート）を検出 |
| [`vault-thin-notes`](./vault-thin-notes/) | Obsidian Vault配下の薄ノート（指定バイト数未満の.md）を検出し強化対象を発見 |

いずれのSKILL.mdも `<vault>`、`<quartz-repo>`、`<convmd-repo>`、`<your-org>/<your-repo>` のようなプレースホルダを含む。自分の環境の実パス・リポジトリ名に置き換えて使う。

## 両ツールから使う仕組み

Claude Code は `~/.claude/skills/<name>/`、Gemini CLI は `~/.gemini/skills/<name>/` をそれぞれ個人スキルディレクトリとして読む。このリポジトリはその実体を1箇所（ここ）に集約し、両方のディレクトリからWindowsのディレクトリジャンクション（`mklink /J`）で参照させることで、片方を編集すれば両方に反映される状態にしている。

### セットアップ（新しい環境での復元）

```bat
git clone https://github.com/iida-masashi/skill.git C:\Users\<you>\claude-gemini-skills

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

## deliverable-review について

このスキルはもともと別リポジトリ（`iida-masashi/checker`）で開発している。ここに置いているのはgit履歴を持たないスナップショットで、実行に必要なファイルのみを含む（`.venv`・`.git`・キャッシュ類は除外済み）。本体の開発・Cloud Runデプロイ等は元リポジトリ側で行う。

## 移管元について

`anaplan-skill`・`promo-forecast-skill`・`consultant-toolkit`・`python-safe-coding`はもともと別のPublicリポジトリ（`iida-masashi/Skills`）で管理していたが、Claude Code / Gemini CLI 両方から使う運用と非公開化のため、このリポジトリに一本化した。旧リポジトリはarchive済み。
