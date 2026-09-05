---
name: vault-publish
description: Sync an Obsidian Vault (awa-garden, religion-garden, cosme-garden, or solution-garden) to its Quartz repo's content/, verify a local build, commit, and push to deploy the digital garden. Invoke when the user wants to publish Vault changes, deploy to the Quartz site, or update a public digital garden — for the 阿波説 (awa) Vault, the religion research Vault, the cosme (化粧品SCM) Vault, or the solution (業務ソリューション調査) Vault. Also handles sync-only/preview requests (no commit/push) via the --sync-only flag — use this skill even when the user just wants to sync or preview locally without publishing.
---

# vault-publish: Vault → Quartz → 公開パイプライン

Vault → Quartz → 公開ホスティングの公開フロー全体をワンステップで実行する。**4つの対象（ターゲット）を扱える**: 阿波説デジタルガーデン(awa)、宗教研究デジタルガーデン(religion)、化粧品SCM研究ガーデン(cosme)、業務ソリューション調査(solution、旧wmstms／食品・お菓子WMS/TMS調査)。awa/religionはGitHub Pages（完全公開）、**cosme/solutionはCloudflare Pages（限定公開・プライベート）**とホスティング先が異なる点に注意。

## ターゲット定義

| ターゲット | Vault | Syncスクリプト | Quartzリポジトリ | GitHub repo | ホスティング | 公開URL |
|---|---|---|---|---|---|---|
| **awa**（既定） | `D:\Vault\awa` | `D:\Vault\awa\_work\_sync_to_quartz.py` | `C:\Users\iidam\quartz` | `iida-masashi/awa-garden`（public） | GitHub Pages | `https://iida-masashi.github.io/awa-garden/` |
| **religion** | `D:\Vault\religion` | `D:\Vault\religion\_work\_sync_to_quartz_religion.py` | `C:\Users\iidam\quartz-religion` | `iida-masashi/religion-garden`（public） | GitHub Pages | `https://iida-masashi.github.io/religion-garden/` |
| **cosme** | `D:\Vault\cosme` | `D:\Vault\cosme\_work\_sync_to_quartz_cosme.py` | `C:\Users\iidam\quartz-cosme` | `iida-masashi/cosme-garden`（**private**） | Cloudflare Pages（GitHub Actions経由でwrangler deploy） | `https://cosme-garden.pages.dev/`（Basic認証必須） |
| **solution** | `D:\Vault\solution` | `D:\Vault\solution\_work\_sync_to_quartz_solution.py` | `C:\Users\iidam\quartz-solution` | `iida-masashi/solution-garden`（**private**、未作成） | Cloudflare Pages / Local | `https://solution-garden.pages.dev/` |

以降、選択したターゲットの行を `<vault>` `<sync-script>` `<quartz-repo>` `<gh-repo>` `<pages-url>` として読み替える。

## When to use

ユーザーが以下のような表現をしたとき:
- 「Vaultを公開して」「デジタルガーデンを更新」「Quartzをデプロイ」
- 「awa-garden に push」「religion-garden に push」「cosme-garden に push」「solution を同期」
- 「/vault-publish」「/vault-publish religion」のように明示的に呼び出されたとき
- 「同期だけして」「ローカルで先に見たい」「push せずに反映」「プレビューだけ」→ `--sync-only` を使う（下記「Sync-only モード」参照）

### ターゲットの決め方

1. ユーザーが `religion`／`宗教`／`religion-garden` 等を明示、または直前の会話が `D:\Vault\religion` 配下のVault操作なら **religion**。
2. ユーザーが `阿波`／`awa`／`awa-garden` 等を明示、または直前の会話が `D:\Vault\awa` 配下のVault操作なら **awa**。
3. ユーザーが `cosme`／`化粧品`／`cosme-garden` 等を明示、または直前の会話が `D:\Vault\cosme` 配下のVault操作なら **cosme**。
4. ユーザーが `solution`／`WMS`／`TMS`／`食品`／`お菓子` 等を明示、または直前の会話が `D:\Vault\solution` 配下のVault操作なら **solution**。
5. どれとも判断できない場合は、明示的にユーザーへ確認する（黙って awa を既定にしない — 誤ったリポジトリへ push する事故を防ぐため）。

## Pipeline (in order)

1. **Sync & Mermaid Lint**: `<sync-script>` を実行
   - **Mermaid自動構文検査 (`mermaid_validator.py`)**: 同期開始前に全Markdown内のMermaid構文（矢印・クォート・サブグラフ整合性）を自動検証。エラー時は安全に同期停止。
   - Mirror Vault subtrees → `<quartz-repo>/content/`
   - Apply frontmatter fix(YAML 不正対応)
   - Apply dewikify(broken wikilink を外部 URL / プレーンテキスト化)
2. **Build verify** (default ON、`--skip-build` で skip 可):
   - `cd <quartz-repo> && npx quartz build` を実行
   - YAML エラーなど発生時は **halt して詳細表示**(ユーザーが Vault を直す必要がある)
3. **`--sync-only` ならここで停止**（下記「Sync-only モード」参照）。commit/push は行わない。
4. **Pre-Commit 監査 & 承認確認（重要規律）**:
   - `python scripts/audit_mermaid_styling.py <vault>` でダイアグラムのアクセシビリティを検証。
   - **必ずユーザーに変更ファイル一覧、変更概要、コミットメッセージ案を提示し、明示的な承認指示を待つ（自動コミット・自動プッシュ厳禁）。**
5. **Commit & Push**: ユーザー承認後、安全に実行
   - `python scripts/safe_git_push.py <quartz-repo>` を実行（接続リセット等の一時エラー時に指数バックオフで最大5回自動リトライ）。

## Sync-only モード（push なしプレビュー）

「同期だけして」「ローカルで先に見たい」「push せずに反映」等、pushを伴わない同期・プレビューが目的の場合は `--sync-only` を使う。commit/push ステップ(4-5)を実行しない点を除き、Pipelineの1-2は通常どおり実行する。

- ユーザーが `--serve` を併用、または「プレビューしたい」と明示した場合のみ、Step 2 の後に `cd <quartz-repo> && npx quartz build --serve` をバックグラウンドで起動し `http://localhost:8080` を案内する（parse に約4分かかるため `run_in_background` + `until grep "Started" ...; do sleep 5; done` 構成で待つ。2ターゲット同時起動はポート衝突の可能性があるため、既に片方が起動中なら停止するか別ポート案内を検討する）
- Report: どのターゲットを同期したか、build結果、(serveした場合)確認用URL、そして「公開するなら `--sync-only` を外して同じ引数で再実行すればよい（syncは既に完了しているので `--skip-sync` を足すと二度手間を避けられる）」ことを伝える
- ファイル変更内容だけ確認したい場合は、実行後に `cd <quartz-repo> && git diff --stat` で確認できる

## Steps to execute

### 1. Pre-flight check

- ターゲットを確定する（上記「ターゲットの決め方」参照）。曖昧なら先にユーザーに確認する。
- 現在のディレクトリは関係ない(全コマンドが絶対パスを使う)
- `<sync-script>` の存在を確認
- `<quartz-repo>/.git` の存在を確認

### 2. Run sync

ユーザーが `--skip-sync` を渡した場合はこのステップを飛ばす（直前に `vault-sync` 等で同じターゲットのsyncが成功済みの場合に使う）。commit message 用のサマリがない場合は「(sync skipped — 直前の実行結果を使用)」とだけ記録する。

awaターゲット:
```bash
cd "D:/Vault/awa/_work" && uv run python _sync_to_quartz.py
```

religionターゲット:
```bash
cd "D:/Vault/religion/_work" && uv run python _sync_to_quartz_religion.py
```

cosmeターゲット:
```bash
cd "D:/Vault/cosme/_work" && uv run python _sync_to_quartz_cosme.py
```
（`uv` が無ければ `/c/Python314/python _sync_to_quartz_cosme.py` で代替可。stdlibのみで動作するので後処理スクリプトのフォールバックは不要）

solutionターゲット:
```bash
cd "D:/Vault/solution/_work" && python _sync_to_quartz_solution.py
```

スクリプトの最後のサマリ(8行程度)を保持して commit message 生成に使う。失敗時(exit non-zero)は **halt して stderr を表示**。

### 3. Build verify (default)

```bash
cd <quartz-repo> && npx quartz build
```

（awaなら `C:/Users/iidam/quartz`、religionなら `C:/Users/iidam/quartz-religion`、cosmeなら `C:/Users/iidam/quartz-cosme`、solutionなら `C:/Users/iidam/quartz-solution`）

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
- **cosmeターゲットのみ追加で伝える**: 「Basic認証が必要（ID/PASSはCloudflare Pages環境変数 `BASIC_AUTH_USER`/`BASIC_AUTH_PASS` で管理、リポジトリには含まれない）」。デプロイはGitHub Actions（`cloudflare/wrangler-action`）経由で `iida-masashi/cosme-garden` の Cloudflare Pages プロジェクトへ行われる。GitHub Pagesではないため `github.io` URLは存在しない。

デプロイ進行状況の確認コマンド（`<gh-repo>` と workflow ID はターゲットに応じて選ぶ）:
- awa: `gh api repos/iida-masashi/awa-garden/actions/workflows/281917513/runs --jq '.workflow_runs[0] | {status, html_url}'`
- religion: `gh api repos/iida-masashi/religion-garden/actions/workflows/321319403/runs --jq '.workflow_runs[0] | {status, html_url}'`
- cosme: `gh api repos/iida-masashi/cosme-garden/actions/workflows/335035241/runs --jq '.workflow_runs[0] | {status, html_url}'`

## Arguments

| Flag | Effect |
|---|---|
| `awa` / `religion` / `cosme` | 対象ターゲットを明示指定（位置引数、例: `/vault-publish religion`） |
| `--skip-sync` | Step 2 (sync) をスキップ。直前に同じターゲットで `--sync-only` 等によりsyncが成功済みの場合に、sync出力の再実行・再表示を避ける |
| `--skip-build` | Step 3 (build verify) をスキップ。push 速度優先 |
| `--sync-only` | commit/push (Step 4-5) を行わず sync+build までで停止。push せずローカルプレビューしたい場合に使う |
| `--serve` | `--sync-only` と併用。build後に `npx quartz build --serve` を起動しプレビューサーバーを立てる |
| `--message "..."` | commit message を上書き |
| `--dry-run` | sync スクリプトを `--dry-run` 付きで実行し、何も commit/push しない |

## What this skill does NOT do

- Vault 側のファイルを編集(同期は片方向 Vault → content) — Vault は source of truth
- 公開設定の変更(repo の visibility, baseUrl, ignorePatterns 等) — それらは別途手動
- Cloudflare側の設定変更(環境変数、Pagesプロジェクト作成等、cosmeターゲット) — 別途 `wrangler` で手動
- watch mode / 自動定期実行 — ユーザーが明示的に呼び出した時のみ動く
- GitHub Actions の他 workflow を停止 — 他は無害なので触らない
- 複数ターゲットを跨いだ操作(awaとreligionを同時にpush等) — 必ず1回の呼び出しにつき1ターゲット

## Notes

- push なしで同期・ローカルプレビューだけしたい場合は `--sync-only`（旧 `vault-sync` スキルは本スキルに統合済み、単独では存在しない）
- 同期スクリプトは idempotent(何度実行しても同じ結果)
- Vault と content の同期は size + mtime 比較。Vault でのタイムスタンプだけ更新したファイルでも copy が走るが、内容は同じなので git diff には現れない
- awa: `D:\Vault\awa\_work\QUARTZ_SYNC_README.md` に運用ドキュメント完備
- cosme: `iida-masashi/cosme-garden` は **private** リポジトリ。公開先の Cloudflare Pages (`cosme-garden.pages.dev`) は `functions/_middleware.js` による Basic 認証で限定公開している。GitHub Pages workflow ではなく `cloudflare/wrangler-action` を使う点、`sources/` サブツリーが同期対象外（一次資料・.chroma_dbキャッシュのため）な点が awa/religion と異なる
- **ターゲットを取り違えると誤ったリポジトリに無関係な内容をpushする事故になる。** 曖昧な指示（単に「公開して」）の場合は必ずどのVaultを指すか確認してから実行する。

## Troubleshooting

| 症状 | 対処 |
|---|---|
| YAML エラーで build 停止 | エラーのファイルを Vault で開き、`epoch: [[X]]Y` のような未 quote の wikilink を `"…"` に手動 quote |
| Mermaid構文エラーでSync停止 | `_work/mermaid_validator.py` の警告に従い、未クォート双方向リンク `<--> |"..."|` や `style='...'` 内のアポストロフィ `L'Oréal` ➔ `L’Oréal` を修正 |
| 日本語ファイル編集による文字化け (Mojibake) | Windows環境でのMarkdown置換は必ず明示的な `encoding='utf-8'` を指定したPythonスクリプト経由で実行すること。コミット前に `git diff` で `縲/繝` 等の混入がないか検証 |
| `Connection was reset` で push 失敗 | スキル内で自動 retry 済。それでもダメなら手動で `git push` を数回試す |
| Actions が起動しない | リモートに workflow ファイルが届いているか確認(`gh api repos/<gh-repo>/contents/.github/workflows/deploy.yml`) |
| sync で大量更新が出るが内容は同じ | mtime ずれが原因。挙動として正しい。git diff で実差分を確認 |
| 公開サイトで Mermaid 図が `Syntax error in text` | **Mermaid ブロック内の `%%`** が原因。Quartz の OFM transformer が `%%…%%` を Obsidian ブロックコメントとみなし**間を全削除**するため、ノード/エッジ定義が消えて図が壊れる（`%%` は Mermaid 自身のコメント構文でもあるため作者が無意識に使う罠）。対処：**mermaid フェンス内の `%%` を全廃**（1個でも残すと次の `%%`/EOF まで食う）。`build` exit 0 ≠ 描画OK（クライアント側描画）なので、`public/<path>.html` の `data-clipboard` ペイロードを読んで図全体が残っているか確認する。sync は `_check_mermaid_comments.py` でこの `%%` を warn-only 検出する（awaのみ、religion側の対応は未確認）。 |
| どちらのターゲットか迷う | 黙って推測せず、ユーザーに確認する。誤ったリポジトリへの push は取り消しにくい |
| cosme: push後もサイトが更新されない/401のまま | GitHub Actions（`wrangler-action`）が失敗している可能性。`gh run list --repo iida-masashi/cosme-garden --limit 1` で確認。Cloudflare側の `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` (GitHub Secrets) または `BASIC_AUTH_USER`/`BASIC_AUTH_PASS` (Cloudflare Pages環境変数) が未設定・期限切れだと失敗する |
| Bashツールで `uv: command not found` | `uv`がPATHに乗っていない環境（WinGet配下等にインストール済みでも）で起きる。`_sync_to_quartz*.py`自体はstdlibのみで動くので `/c/Python314/python <sync-script>` のように system python で直接叩けば1〜3のミラー処理は完走する。ただしスクリプト内部で `_fix_quartz_frontmatter.py` / `_dewikify_broken.py` / `_strip_dataview.py` / `_check_mermaid_comments.py` を `subprocess.run(["uv", "run", "python", ...])` 経由で呼ぶ設計のため、そこで同じエラーが出て後処理が止まる。後処理4スクリプトもいずれも標準ライブラリのみに依存しているため、`_work/` 配下から同様に system python で1本ずつ直接実行すれば代替できる（実行順: frontmatter fix → dewikify → dataview strip → mermaid check）。`npx quartz build` はNode.js経由なのでこの問題の影響を受けない。 |
