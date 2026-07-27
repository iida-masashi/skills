---
name: awa-publish
description: Sync an Obsidian Vault (awa-garden or religion-garden) to its Quartz repo's content/, verify a local build, commit, and push to deploy the digital garden on GitHub Pages. Invoke when the user wants to publish Vault changes, deploy to the Quartz site, or update a public digital garden — for either the 阿波説 (awa) Vault or the religion research Vault.
---

# awa-publish: Vault → Quartz → GitHub Pages 公開パイプライン

Vault → Quartz → GitHub Pages の公開フロー全体をワンステップで実行する。**2つの対象（ターゲット）を扱える**: 阿波説デジタルガーデン(awa)と宗教研究デジタルガーデン(religion)。

## ターゲット定義

| ターゲット | Vault | Syncスクリプト | Quartzリポジトリ | GitHub repo | 公開URL |
|---|---|---|---|---|---|
| **awa**（既定） | `D:\Vault` | `D:\Vault\_work\_sync_to_quartz.py` | `C:\Users\iidam\quartz` | `iida-masashi/awa-garden` | `https://iida-masashi.github.io/awa-garden/` |
| **religion** | `D:\religion` | `D:\religion\_work\_sync_to_quartz_religion.py` | `C:\Users\iidam\quartz-religion` | `iida-masashi/religion-garden` | `https://iida-masashi.github.io/religion-garden/` |

以降、選択したターゲットの行を `<vault>` `<sync-script>` `<quartz-repo>` `<gh-repo>` `<pages-url>` として読み替える。

## When to use

ユーザーが以下のような表現をしたとき:
- 「Vaultを公開して」「デジタルガーデンを更新」「Quartzをデプロイ」
- 「awa-garden に push」「religion-garden に push」「変更を反映したい」
- 「/awa-publish」「/awa-publish religion」のように明示的に呼び出されたとき

### ターゲットの決め方

1. ユーザーが `religion`／`宗教`／`religion-garden` 等を明示、または直前の会話が `D:\religion` 配下のVault操作なら **religion**。
2. ユーザーが `阿波`／`awa`／`awa-garden` 等を明示、または直前の会話が `D:\Vault` 配下のVault操作なら **awa**。
3. どちらとも判断できない場合は、明示的にユーザーへ確認する（黙って awa を既定にしない — 誤ったリポジトリへ push する事故を防ぐため）。

## Pipeline (in order)

1. **Sync**: `<sync-script>` を実行
   - Mirror Vault subtrees → `<quartz-repo>/content/`
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

- ターゲットを確定する（上記「ターゲットの決め方」参照）。曖昧なら先にユーザーに確認する。
- 現在のディレクトリは関係ない(全コマンドが絶対パスを使う)
- `<sync-script>` の存在を確認
- `<quartz-repo>/.git` の存在を確認

### 2. Run sync

awaターゲット:
```bash
cd "D:/Vault/_work" && uv run python _sync_to_quartz.py
```

religionターゲット:
```bash
cd "D:/religion/_work" && uv run python _sync_to_quartz_religion.py
```

スクリプトの最後のサマリ(8行程度)を保持して commit message 生成に使う。失敗時(exit non-zero)は **halt して stderr を表示**。

### 3. Build verify (default)

```bash
cd <quartz-repo> && npx quartz build
```

（awaなら `C:/Users/iidam/quartz`、religionなら `C:/Users/iidam/quartz-religion`）

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
- 公開 URL: `<pages-url>`
- Actions URL: `https://github.com/<gh-repo>/actions`
- 「GitHub Actions が自動でデプロイします(約 1-2 分)」

デプロイ進行状況の確認コマンド（`<gh-repo>` と workflow ID はターゲットに応じて選ぶ）:
- awa: `gh api repos/iida-masashi/awa-garden/actions/workflows/281917513/runs --jq '.workflow_runs[0] | {status, html_url}'`
- religion: `gh api repos/iida-masashi/religion-garden/actions/workflows/321319403/runs --jq '.workflow_runs[0] | {status, html_url}'`

## Arguments

| Flag | Effect |
|---|---|
| `awa` / `religion` | 対象ターゲットを明示指定（位置引数、例: `/awa-publish religion`） |
| `--skip-build` | Step 3 (build verify) をスキップ。push 速度優先 |
| `--message "..."` | commit message を上書き |
| `--dry-run` | sync スクリプトを `--dry-run` 付きで実行し、何も commit/push しない |

## What this skill does NOT do

- Vault 側のファイルを編集(同期は片方向 Vault → content) — Vault は source of truth
- 公開設定の変更(repo の visibility, baseUrl, ignorePatterns 等) — それらは別途手動
- watch mode / 自動定期実行 — ユーザーが明示的に呼び出した時のみ動く
- GitHub Actions の他 workflow を停止 — 他は無害なので触らない
- 2つのターゲットを跨いだ操作(awaとreligionを同時にpush等) — 必ず1回の呼び出しにつき1ターゲット

## Notes

- 同期スクリプトは idempotent(何度実行しても同じ結果)
- Vault と content の同期は size + mtime 比較。Vault でのタイムスタンプだけ更新したファイルでも copy が走るが、内容は同じなので git diff には現れない
- awa: `D:\Vault\_work\QUARTZ_SYNC_README.md` に運用ドキュメント完備
- **ターゲットを取り違えると誤ったリポジトリに無関係な内容をpushする事故になる。** 曖昧な指示（単に「公開して」）の場合は必ずどちらのVaultを指すか確認してから実行する。

## Troubleshooting

| 症状 | 対処 |
|---|---|
| YAML エラーで build 停止 | エラーのファイルを Vault で開き、`epoch: [[X]]Y` のような未 quote の wikilink を `"…"` に手動 quote |
| `Connection was reset` で push 失敗 | スキル内で自動 retry 済。それでもダメなら手動で `git push` を数回試す |
| Actions が起動しない | リモートに workflow ファイルが届いているか確認(`gh api repos/<gh-repo>/contents/.github/workflows/deploy.yml`) |
| sync で大量更新が出るが内容は同じ | mtime ずれが原因。挙動として正しい。git diff で実差分を確認 |
| 公開サイトで Mermaid 図が `Syntax error in text` | **Mermaid ブロック内の `%%`** が原因。Quartz の OFM transformer が `%%…%%` を Obsidian ブロックコメントとみなし**間を全削除**するため、ノード/エッジ定義が消えて図が壊れる（`%%` は Mermaid 自身のコメント構文でもあるため作者が無意識に使う罠）。対処：**mermaid フェンス内の `%%` を全廃**（1個でも残すと次の `%%`/EOF まで食う）。`build` exit 0 ≠ 描画OK（クライアント側描画）なので、`public/<path>.html` の `data-clipboard` ペイロードを読んで図全体が残っているか確認する。sync は `_check_mermaid_comments.py` でこの `%%` を warn-only 検出する（awaのみ、religion側の対応は未確認）。 |
| どちらのターゲットか迷う | 黙って推測せず、ユーザーに確認する。誤ったリポジトリへの push は取り消しにくい |
