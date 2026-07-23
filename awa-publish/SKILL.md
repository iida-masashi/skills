---
name: awa-publish
description: Sync the Obsidian Vault at <vault> to <quartz-repo>/content/, verify a local build, commit, and push to deploy the 阿波説デジタルガーデン on GitHub Pages (<your-pages-url>). Invoke when the user wants to publish Vault changes, deploy to the Quartz site, or update the public digital garden.
---

# awa-publish: Vault → Quartz → GitHub Pages 公開パイプライン

阿波説デジタルガーデン(`<your-pages-url>`)の公開フロー全体をワンステップで実行する。

## When to use

ユーザーが以下のような表現をしたとき:
- 「Vaultを公開して」「デジタルガーデンを更新」「Quartzをデプロイ」
- 「awa-garden に push」「変更を反映したい」
- 「/awa-publish」のように明示的に呼び出されたとき

## Pipeline (in order)

1. **Sync**: `<vault>/_work/_sync_to_quartz.py` を実行
   - Mirror Vault subtrees → `content/`
   - Apply frontmatter fix(YAML 不正対応)
   - Apply dewikify(broken wikilink を外部 URL / プレーンテキスト化)
2. **Build verify** (default ON、`--skip-build` で skip 可):
   - `cd <quartz-repo> && npx quartz build` を実行
   - YAML エラーなど発生時は **halt して詳細表示**(ユーザーが Vault を直す必要がある)
3. **Commit**: 同期結果から自動メッセージ生成(or `--message` で上書き)
4. **Push**: `git push`
   - `Recv failure: Connection was reset` 等のネットワークエラーで失敗した場合、
     `git config http.postBuffer 524288000` を設定して **1 回だけ retry**

## Steps to execute

### 1. Pre-flight check

- 現在のディレクトリは関係ない(全コマンドが絶対パスを使う)
- `<vault>/_work/_sync_to_quartz.py` の存在を確認
- `<quartz-repo>/.git` の存在を確認

### 2. Run sync

```bash
cd <vault>/_work && uv run python _sync_to_quartz.py
```

スクリプトの最後のサマリ(8行程度)を保持して commit message 生成に使う。失敗時(exit non-zero)は **halt して stderr を表示**。

### 3. Build verify (default)

```bash
cd <quartz-repo> && npx quartz build
```

成功時の最終行は `Done processing N files in Xs`。
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
- 公開 URL: `<your-pages-url>`
- Actions URL: `https://github.com/<your-org>/<your-repo>/actions`
- 「GitHub Actions が自動でデプロイします(約 1-2 分)」

任意で `gh api repos/<your-org>/<your-repo>/actions/workflows/281917513/runs --jq '.workflow_runs[0] | {status, html_url}'` でデプロイ進行状況を取得できることを伝える。

## Arguments

| Flag | Effect |
|---|---|
| `--skip-build` | Step 3 (build verify) をスキップ。push 速度優先 |
| `--message "..."` | commit message を上書き |
| `--dry-run` | `_sync_to_quartz.py --dry-run` を実行し、何も commit/push しない |

## What this skill does NOT do

- Vault 側のファイルを編集(同期は片方向 Vault → content) — Vault は source of truth
- 公開設定の変更(repo の visibility, baseUrl, ignorePatterns 等) — それらは別途手動
- watch mode / 自動定期実行 — ユーザーが明示的に呼び出した時のみ動く
- GitHub Actions の他 workflow を停止 — 他は無害なので触らない

## Notes

- 同期スクリプトは idempotent(何度実行しても同じ結果)
- Vault と content の同期は size + mtime 比較。Vault でのタイムスタンプだけ更新したファイルでも copy が走るが、内容は同じなので git diff には現れない
- `<vault>/_work/QUARTZ_SYNC_README.md` に運用ドキュメント完備

## Troubleshooting

| 症状 | 対処 |
|---|---|
| YAML エラーで build 停止 | エラーのファイルを Vault で開き、`epoch: [[X]]Y` のような未 quote の wikilink を `"…"` に手動 quote |
| `Connection was reset` で push 失敗 | スキル内で自動 retry 済。それでもダメなら手動で `git push` を数回試す |
| Actions が起動しない | リモートに workflow ファイルが届いているか確認(`gh api repos/<your-org>/<your-repo>/contents/.github/workflows/deploy.yml`) |
| sync で大量更新が出るが内容は同じ | mtime ずれが原因。挙動として正しい。git diff で実差分を確認 |
| 公開サイトで Mermaid 図が `Syntax error in text` | **Mermaid ブロック内の `%%`** が原因。Quartz の OFM transformer が `%%…%%` を Obsidian ブロックコメントとみなし**間を全削除**するため、ノード/エッジ定義が消えて図が壊れる（`%%` は Mermaid 自身のコメント構文でもあるため作者が無意識に使う罠）。対処：**mermaid フェンス内の `%%` を全廃**（1個でも残すと次の `%%`/EOF まで食う）。`build` exit 0 ≠ 描画OK（クライアント側描画）なので、`public/<path>.html` の `data-clipboard` ペイロードを読んで図全体が残っているか確認する。sync は `_check_mermaid_comments.py` でこの `%%` を warn-only 検出する。 |
