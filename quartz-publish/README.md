# quartz-publish

Obsidian Vault を Quartz サイトとして公開するパイプライン（sync → build 検証 → commit → push）をワンステップで実行する汎用スキル。特定の Vault やリポジトリに紐付いておらず、対象の Vault・同期スクリプト・Quartz リポジトリ・GitHub の org/repo は実行のたびに（または初回のみ）特定・確認する設計。

## 使い方

以下のような表現をしたときに呼び出す:

- 「Vaultを公開して」「デジタルガーデンを更新」「Quartzをデプロイ」
- 「〇〇(サイト名)に push」「変更を反映したい」
- 「/quartz-publish」のように明示的に呼び出したとき

初回・設定不明時は先に「0. 設定の特定」を行う。Vault パス、同期スクリプトの場所・実行方法、Quartz リポジトリのパス、公開URL・GitHub org/repo を、会話の文脈やメモリ、慣例的な配置（`<vault>/_work/` 等）、リポジトリ内の設定（`git remote -v`、`quartz.config.ts` の `baseUrl` 等）から特定する。推測で埋めず、不明ならユーザーに確認する。

### 処理フロー

1. **Sync** — 同期スクリプトを実行し、Vault のサブツリーを `content/` にミラー（対応していれば frontmatter fix・dewikify 等の後処理も適用）
2. **Build verify**（既定 ON、`--skip-build` でスキップ可） — `npx quartz build` を実行。YAML エラー等が出たら halt して詳細を表示（Vault 側の修正が必要）
3. **Commit** — 同期結果から自動でメッセージを生成（`--message` で上書き可）
4. **Push** — `git push`。ネットワークエラー時は `http.postBuffer` を設定して1回だけ retry

git commit/push はユーザーへの影響が大きい操作のため、push 直前で確認を取る（このスキル自体が明示的な公開指示への応答である場合を除く）。

### 引数

| Flag | 効果 |
|---|---|
| `--skip-build` | build 検証をスキップ（push 速度優先） |
| `--message "..."` | commit message を上書き |
| `--dry-run` | 同期スクリプトの `--dry-run` 相当を実行し、commit/push はしない |

## Highlights

- **汎用テンプレート** — 特定 Vault にハードコードされた設定を持たず、対象を毎回（または初回のみ）特定する運用。同一構造の Vault→Quartz パイプラインを複数プロジェクトで使い回すための土台
- **Build 検証をデフォルトで挟む** — sync 直後に `quartz build` を走らせ、YAML エラー等を push 前に検出。失敗時は halt してユーザーに Vault 側の修正を促す
- **Push のネットワークエラーに1回だけ自動 retry** — `Connection was reset` 等は `http.postBuffer` 拡大で再試行、それでも失敗すれば halt
- **片方向同期が前提** — Vault が source of truth であり、このスキルは Vault 側ファイルを編集しない。公開設定（visibility、baseUrl、ignorePatterns等）の変更や、同期スクリプト自体の新規作成もスコープ外
- **Mermaid の `%%` トラップに関する既知のトラブルシューティングを内包** — Quartz の OFM transformer が mermaid フェンス内の `%%…%%` をコメントとみなし削除してしまう問題（build成功は描画OKを意味しない）への対処法を記載

## quartz-publish と vault-publish の違い

同リポジトリには特定 Vault 専用の `vault-publish` スキルも存在する。使い分けは以下:

| | **quartz-publish**（本スキル） | **vault-publish** |
|---|---|---|
| 対象 | 未特定・汎用。実行ごとに Vault/リポジトリを特定 | `awa`（阿波説 Vault）と `religion`（宗教研究 Vault）の2ターゲットに固定 |
| 設定 | 会話の文脈・メモリ・探索で都度特定 | ターゲットごとの Vault パス・同期スクリプト・Quartz リポジトリ・GitHub repo・公開URLを表内にハードコード済み |
| ターゲット選択 | 該当なし（単一の未特定対象） | 曖昧な指示では黙って既定を使わず、必ずユーザーに確認（誤ったリポジトリへの push を防ぐため） |
| 用途 | 新しい Vault/Quartz 構成や、都度設定を確認しながら使う場合の汎用手順 | awa-garden / religion-garden の運用に特化した即応スキル |

処理フロー（sync → build 検証 → commit → push、`--skip-build` / `--message` / `--dry-run` 引数、Mermaid `%%` トラブルシューティング）自体は両スキルで共通。
