---
name: quartz-publish
description: Sync an Obsidian Vault to a Quartz site's content/ folder, verify a local build, commit, and push to deploy via GitHub Pages (or equivalent). Invoke when the user wants to publish Vault changes, deploy to the Quartz site, or update a public digital garden.
---

# quartz-publish: Vault → Quartz → GitHub Pages 公開パイプライン

Obsidian Vault を Quartz サイトとして公開するパイプライン(sync → build 検証 → commit → push)をワンステップで実行する汎用スキル。

**このスキルは特定のVault/リポジトリに紐付いていない。使用対象のVault・同期スクリプト・Quartzリポジトリ・GitHubのorg/repoは、実行のたびに(または初回のみ)特定・確認すること(下記「0. 設定の特定」参照)。**

## When to use

ユーザーが以下のような表現をしたとき:
- 「Vaultを公開して」「デジタルガーデンを更新」「Quartzをデプロイ」
- 「〇〇(サイト名)に push」「変更を反映したい」
- 「/quartz-publish」のように明示的に呼び出されたとき

## 0. 設定の特定(初回・不明時は必須)

このスキルの実行には以下が必要。会話の過去の文脈・メモリで既に判明していればそれを使い、不明ならユーザーに確認するか、慣例的な場所を探索する。

| 項目 | 特定方法 |
|---|---|
| **Vaultパス** | ユーザーの発言・過去の会話・メモリから推定。不明なら質問する |
| **同期スクリプトの場所・実行方法** | 慣例上 `<vault>/_work/` や `<vault>/scripts/` 配下。README(`*SYNC*README*.md`等)があれば先に読む |
| **Quartzリポジトリのパス** | 同期スクリプト内にハードコードされているか、引数で指定する設計かを確認 |
| **公開URL・GitHub org/repo** | Quartzリポジトリの `git remote -v` や `package.json`/`quartz.config.ts` の `baseUrl` から確認する。推測でURLを出さない |

これらが確認できない場合、推測で埋めずユーザーに確認する。

## Pipeline (in order)

1. **Sync**: 同期スクリプトを実行
   - Mirror Vault subtrees → `content/`
   - (スクリプトが対応していれば) frontmatter fix・dewikify等の後処理を適用
2. **Build verify** (default ON、`--skip-build` で skip 可):
   - `cd <quartz-repo> && npx quartz build` を実行
   - YAML エラーなど発生時は **halt して詳細表示**(ユーザーが Vault を直す必要がある)
3. **Commit**: 同期結果から自動メッセージ生成(or `--message` で上書き)
4. **Push**: `git push`
   - ネットワークエラー(`Recv failure: Connection was reset` 等)で失敗した場合、
     `git config http.postBuffer 524288000` を設定して **1 回だけ retry**

## Steps to execute

### 1. Pre-flight check

- 現在のディレクトリは関係ない(全コマンドが絶対パスを使う想定)
- 同期スクリプトの存在を確認
- `<quartz-repo>/.git` の存在を確認

### 2. Run sync

```bash
cd <vault>/<sync-script-dir> && uv run python <sync_script_name>.py
```

スクリプトの最後のサマリ(出力の末尾数行)を保持して commit message 生成に使う。失敗時(exit non-zero)は **halt して stderr を表示**。

### 3. Build verify (default)

```bash
cd <quartz-repo> && npx quartz build
```

成功時の最終行は通常 `Done processing N files in Xs` 相当。
失敗時は YAML エラーの可能性が高い。エラー出力をそのままユーザーに見せて halt する。

ユーザーが `--skip-build` を渡した場合のみこのステップを飛ばす。

### 4. Stage and commit

```bash
cd <quartz-repo> && git add -A && git status --short | head -5
```

変更がない場合は「No changes to publish.」と報告して終了する(push しない)。

commit message は以下の優先順位:
- ユーザーが `--message "..."` を指定 → それを使う
- それ以外 → `sync: <sync summary 1行要約>` を自動生成 (例: `sync: 12 files updated, 3 conversions`)

コミット:
```bash
cd <quartz-repo> && git commit -m "<message>"
```

**git commit/pushはユーザーへの影響が大きい操作である。ユーザーが明示的にこのスキルの実行を指示していない限り(=このスキル自体が明示的な公開指示への応答である場合を除き)、pushの直前で一度確認を取る。**

### 5. Push (with retry on network error)

```bash
cd <quartz-repo> && git push 2>&1
```

失敗 (`Connection was reset` / `RPC failed` 等) → 一度だけ retry:

```bash
cd <quartz-repo> && git config http.postBuffer 524288000 && git push 2>&1
```

それでも失敗したら halt してエラー表示。

### 6. Report

成功時、ユーザーに以下を伝える:
- 公開URL(判明していれば)
- GitHub Actions等のCI URL(判明していれば)
- デプロイが自動で走ることと、おおよその所要時間

任意でCIの実行状況をAPI経由(例: `gh api repos/<org>/<repo>/actions/runs --jq '.workflow_runs[0] | {status, html_url}'`)で確認できることを伝える。

## Arguments

| Flag | Effect |
|---|---|
| `--skip-build` | Step 3 (build verify) をスキップ。push 速度優先 |
| `--message "..."` | commit message を上書き |
| `--dry-run` | 同期スクリプトの `--dry-run` 相当を実行し、何も commit/push しない(スクリプトが対応している場合のみ) |

## What this skill does NOT do

- Vault 側のファイルを編集(同期は片方向 Vault → content) — Vault は source of truth
- 公開設定の変更(repo の visibility, baseUrl, ignorePatterns 等) — それらは別途手動
- watch mode / 自動定期実行 — ユーザーが明示的に呼び出した時のみ動く
- CI/CDの他 workflow を停止・変更 — 他は無害なので触らない
- 同期スクリプト自体の新規作成(既存スクリプトが前提)

## Notes

- 同期スクリプトは通常 idempotent(何度実行しても同じ結果)であることが望ましい。そうでない場合はユーザーに注意を促す
- Vault と content の同期比較方式(size+mtime、ハッシュ等)によっては、内容が同じでもタイムスタンプ差でコピーが走ることがある。git diff に現れなければ実害なし
- 運用ドキュメント(README等)が同期スクリプトと同じ場所にあれば、実行前に一読する

## Troubleshooting

| 症状 | 対処 |
|---|---|
| YAML エラーで build 停止 | エラーのファイルを Vault で開き、`epoch: [[X]]Y` のような未 quote の wikilink を `"…"` に手動 quote |
| ネットワークエラーで push 失敗 | スキル内で自動 retry 済。それでもダメなら手動で `git push` を数回試す |
| CIが起動しない | リモートに workflow ファイルが届いているか確認 |
| sync で大量更新が出るが内容は同じ | mtime ずれ等が原因のことが多い。挙動として正しいことが多いが、git diff で実差分を確認する |
| 公開サイトで Mermaid 図が `Syntax error in text` | **Mermaid ブロック内の `%%`** が原因になりうる。Quartz の OFM(Obsidian Flavored Markdown) transformer は `%%…%%` を Obsidian のブロックコメントとみなし**間を全削除**するため、mermaidフェンス内にあるとノード/エッジ定義が消えて図が壊れる（`%%` は Mermaid 自身のコメント構文でもあるため作者が無意識に使いがちな罠）。対処：**mermaid フェンス内の `%%` を全廃**（1個でも残すと次の `%%`/EOFまで食われる）。`build` の exit 0 は描画OKを意味しない（Mermaidはクライアント側描画のため）。疑わしい場合は生成された `public/<path>.html` 内の該当コードブロックのペイロードを直接確認する |
