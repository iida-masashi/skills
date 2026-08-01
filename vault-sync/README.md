# vault-sync

Obsidian Vault（awa-garden または religion-garden）を対応する Quartz リポジトリの `content/` へ同期し、ローカル build で整合性を確認する。**git commit / push は一切行わない**プレビュー専用スキル。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | ターゲット定義・実行手順・引数一覧 |

## どういう場面で使われるか

ユーザーが以下のような表現をしたとき:
- 「ローカルで先に見たい」「同期だけして」
- 「push せずに反映」「プレビューだけ」
- 「/vault-sync」「/vault-sync religion」のように明示的に呼び出されたとき

フル公開（commit/push まで）したい場合は姉妹スキル `vault-publish` を使う。

## 扱うターゲット

このスキルは2つのVault/Quartzペアを扱う（引数で選択、既定は awa）。

| ターゲット | Vault | Syncスクリプト | Quartzリポジトリ |
|---|---|---|---|
| **awa**（既定） | `D:\Vault\awa` | `D:\Vault\awa\_work\_sync_to_quartz.py` | `C:\Users\iidam\quartz` |
| **religion** | `D:\Vault\religion` | `D:\Vault\religion\_work\_sync_to_quartz_religion.py` | `C:\Users\iidam\quartz-religion` |

ターゲットが曖昧な場合は黙って awa を既定にせず、ユーザーに確認する（取り違えると無関係なVaultの内容でbuildしてしまうため）。

## 処理フロー

1. **Sync** — 対象ターゲットの同期スクリプトを実行（`vault-publish` と同じスクリプト）
2. **Build** — `cd <quartz-repo> && npx quartz build` で整合性を確認。YAMLエラー等で失敗時は詳細表示して halt（Vault側の修正が必要）
3. **(任意) Serve** — ユーザーが `--serve` を渡した、または「プレビューしたい」と明示した場合のみ、`npx quartz build --serve` をバックグラウンドで起動し `http://localhost:8080` を案内
4. **Report** — 同期したターゲット、同期/build結果、（serveした場合）確認用URLを伝え、公開したい場合は同じターゲットを指定して `/vault-publish` を実行するよう案内する

git/push 操作はこのパイプラインに含まれない。

## Arguments

| Flag | Effect |
|---|---|
| `awa` / `religion` | 対象ターゲットを明示指定（位置引数、例: `/vault-sync religion`） |
| `--skip-build` | Build (step 2) をスキップし、同期だけ実行 |
| `--serve` | Step 3 を実行してプレビューサーバーを立てる |
| `--dry-run` | 同期スクリプトを `--dry-run` 付きで実行し、何も変更しない |

## What this skill does NOT do

- git commit / git push（それは `vault-publish` の仕事）
- Vault側ファイルの編集（同期は一方向: Vault → content）
- watch mode
- 2つのターゲットを跨いだ同期（1回の呼び出しにつき1ターゲット）

## Highlights

- **push無しのプレビュー専用** — `vault-publish` から commit/push を取り除いただけの構成で、Pipeline・ターゲット定義・同期スクリプトは `vault-publish` と共通。差分は「pushしない」の1点のみ。
- **2ターゲット対応** — 阿波説（awa）と宗教研究（religion）という別々のVault/Quartzペアを1つのスキルで扱う。ターゲット判定ロジックは `vault-publish` と共通。
- **ターゲット固有パスがSKILL.mdにハードコード済み** — Vaultパス・同期スクリプトパス・Quartzリポジトリパスがテーブルで固定されており、実行前の探索・特定作業が不要。

## `quartz-sync` との違い

より汎用的な姉妹スキル `quartz-sync` は同じ「同期→build→(任意serve)、pushなし」というパイプラインの**型（テンプレート）**を提供するが、対象Vault/Quartzリポジトリパスをハードコードしていない。実行前に「0. 設定の特定」ステップでVaultパス・同期スクリプトの場所・Quartzリポジトリパスをユーザーの発言や過去の会話、Glob検索などから特定する必要がある（不明なら質問する）。同期スクリプトが存在しない場合は適用せず相談する、という前提も明記されている。

対して `vault-sync` は awa/religion という特定の2ターゲットに特化し、それらのパスをSKILL.md内に確定情報として持つため、設定特定のステップが不要。両者の実行手順（Pipeline）自体は同じ形をしている。
