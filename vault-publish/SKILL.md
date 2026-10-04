---
name: vault-publish
description: Sync an Obsidian Vault (awa-garden, religion-garden, solution-garden, or cpg-vault) to its Quartz repo's content/, verify a local build, commit, and push to deploy the digital garden. Invoke when the user wants to publish Vault changes, deploy to the Quartz site, or update a public digital garden — for the 阿波説 (awa) Vault, the religion research Vault, the solution (業務ソリューション調査) Vault, or the cpg (CPG統合ナレッジベース／飲料・お菓子・化粧品SCM調査・cosmeを統合済み) Vault. Also handles sync-only/preview requests (no commit/push) via the --sync-only flag — use this skill even when the user just wants to sync or preview locally without publishing.
---

# vault-publish: Vault → Quartz → 公開パイプライン

Vault → Quartz → 公開ホスティングの公開フロー全体をワンステップで実行する。**4つの対象（ターゲット）を扱える**: 阿波説デジタルガーデン(awa)、宗教研究デジタルガーデン(religion)、業務ソリューション調査(solution、旧wmstms／食品・お菓子WMS/TMS調査)、CPG統合ナレッジベース(cpg、飲料・お菓子・化粧品SCM・SCMソリューション統合)。awa/religionはGitHub Pages（完全公開）、**solution/cpgはCloudflare Pages（限定公開・プライベート）**とホスティング先が異なる点に注意。**cpgのみ他3ターゲットと異なるアーキテクチャ**（下記「cpgターゲットの特殊性」参照）。

**cosmeターゲットは廃止済み（2026-09-09）**: `D:\Vault\cosme`はcpg Vaultの`03_Cosmetics_and_Beauty/`へ統合され、独立Vault・独立Quartzリポジトリ・独立GitHub repo（cosme-garden）はいずれも現存しない。cosme関連の公開作業は`cpg`ターゲットとして扱う。

## ターゲット定義

| ターゲット | Vault | Syncスクリプト | Quartzリポジトリ | GitHub repo | ホスティング | 公開URL |
|---|---|---|---|---|---|---|
| **awa**（既定） | `D:\Vault\awa` | `D:\Vault\awa\_work\_sync_to_quartz.py` | `C:\Users\iidam\quartz` | `iida-masashi/awa-garden`（public） | GitHub Pages | `https://iida-masashi.github.io/awa-garden/` |
| **religion** | `D:\Vault\religion` | `D:\Vault\religion\_work\_sync_to_quartz_religion.py` | `C:\Users\iidam\quartz-religion` | `iida-masashi/religion-garden`（public） | GitHub Pages | `https://iida-masashi.github.io/religion-garden/` |
| **solution** | `D:\Vault\solution` | `D:\Vault\solution\_work\_sync_to_quartz_solution.py` | `C:\Users\iidam\quartz-solution` | `iida-masashi/solution-garden`（**private**、未作成） | Cloudflare Pages / Local | `https://solution-garden.pages.dev/` |
| **cpg** | `D:\Vault\cpg`（Vault自体がQuartzリポジトリ兼gitリポジトリ） | `D:\Vault\cpg\_work\_sync_to_quartz_cpg.py`（content先はVault外） | ―（Vault自体がQuartzリポジトリ、下記参照） | `iida-masashi/cpg-vault`（**private**） | Cloudflare Pages（GitHub Actions経由でwrangler deploy） | `https://cpg-vault.pages.dev/`（Basic認証必須） |

以降、選択したターゲットの行を `<vault>` `<sync-script>` `<quartz-repo>` `<gh-repo>` `<pages-url>` として読み替える（cpgターゲットは`<quartz-repo>` = `<vault>` = `D:\Vault\cpg`として扱う。contentミラー先だけが例外的にVault外。下記「cpgターゲットの特殊性」参照）。

## cpgターゲットの特殊性（他3ターゲットとの違い）

cpgは2026-09-09にawaと同じ見た目のQuartzサイトへ移行し、さらに単一リポジトリ構成に統合された。他3ターゲット（awa/religion/solution）は「Vault（非公開）→ 別リポジトリのQuartz content/へ片方向sync」という2リポジトリ構成だが、cpgは**Quartz本体（`quartz/`, `quartz.config.ts`, `quartz.layout.ts`, `package.json`）をVault直下に同居させた単一リポジトリ**である。ただしcontentミラー先だけはVault外（`C:\Users\iidam\quartz-cpg-content`）に置く——Vault内に置くとObsidianが同じノートを二重にインデックスしwikilink alias衝突を起こすため。

- **Step 1 (Sync)**: `D:\Vault\cpg\_work\_sync_to_quartz_cpg.py` を実行。他ターゲットと同じくfrontmatter fix・dewikify・dataview strip・mermaid `%%`チェックの後処理が走る。全6セクション＋`sources/`（一次資料アーカイブ、ユーザー判断で公開継続）をミラー。
- **Step 2 (Build verify)**: `cd D:\Vault\cpg && npx quartz build -d C:/Users/iidam/quartz-cpg-content`（`-d`でVault外のcontentディレクトリを明示指定する点が他ターゲットと異なる）。
- **Step 4-5 (Commit & Push)は `D:\Vault\cpg` 直下で実行**（他ターゲットと同じく`<quartz-repo>` = ここでは`<vault>`）。
- **旧`build_site.py`パイプラインは`deploy-legacy.yml`として残置**（`workflow_dispatch`専用、手動ロールバック手段）。通常の公開作業では使わない。
- **CI（`deploy.yml`）はcontentミラー先を`${{ runner.temp }}/quartz-content`に置く**（`${{ github.workspace }}`配下ではない）。**理由**: Quartzの`glob()`は`globby({gitignore: true})`を使うため、`.gitignore`に一致するパスを入力ディレクトリに指定すると「Found 0 input files」＝空サイトを黙ってデプロイする重大な罠がある（2026-09-09に実際にこれで本番サイトが一時空になった）。ローカル・CIともにcontentディレクトリは**リポジトリの`.gitignore`パターンに絶対に一致させないこと**。
- **Quartzコアに2ファイルの改変あり**（`quartz/plugins/emitters/contentIndex.tsx`, `quartz/plugins/transformers/links.ts`）。`sources/`配下の一次資料アーカイブ（SEC提出書類等、最大2.7MB）の全文テキストが検索インデックスに入ると8MBに肥大化しブラウザがOOMクラッシュする実害が出たための対処（`content`フィールドを`sources/`のみ空にする、popoverも無効化）。将来Quartzをアップグレードする際はこの2箇所の再適用が必要。
- **デプロイはCloudflare Pages側のGit連携ではなくGitHub Actions（`.github/workflows/deploy.yml`、`cloudflare/wrangler-action`）経由**。リポジトリSecrets `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` が必須（設定済み）。
- **ワークフロー内でsecretsをif条件に直接使えない**（GitHub Actionsの仕様上 `if: secrets.X != ''` は`Unrecognized named-value`エラーになる）。`deploy.yml`はjobレベルの`env: HAS_CLOUDFLARE_SECRETS: ${{ secrets.X != '' }}`経由でstepの`if: env.HAS_CLOUDFLARE_SECRETS == 'true'`を制御する形で実装済み。このパターンを崩さないこと。
- **ファイル名はASCII換算255バイト以内にする**（GitHub ActionsのUbuntu/ext4ランナーはWindows/NTFSと異なり255バイト制限があり、長い日本語ファイル名でcheckoutが失敗する実例あり）。
- **新しいトップレベルフォルダ（ドメイン）を公開する前のチェック**（04/07/99_Sushiで毎回踏んだ）:
  1. `_work/_sync_to_quartz_cpg.py` の `MIRROR_SUBTREES` に `("<フォルダ>", "<フォルダ>")` を追加する。ハードコードのリストなので、追加しないとエラーなしで公開対象から漏れる。sync後に `C:/Users/iidam/quartz-cpg-content/<フォルダ>` へ実際に来ているか確認する。
  2. フォルダ内にconvMDの `primary_sources/` がある場合、`.gitignore` の `.chroma_db` 除外は `sources/**/.chroma_db/` 限定なので `<フォルダ>/**/.chroma_db/` を追記する。`git add --dry-run <フォルダ> | grep -E 'chroma|\.db'` で0件を確認する。
  3. Gemini等が生成した解説書は mermaid に `%%{init: ...}%%` を入れがち。`validate_mermaid.py <フォルダ>` で MERMAID_COMMENT_HAZARD が出たら init ブロックを除去する。
  4. 作業ツリーには `.obsidian/plugins/` の更新など無関係な未コミット変更が残っていることが多い。Step 4 の `git add -A` は使わず、今回の対象パスだけを明示してステージする。

## When to use

ユーザーが以下のような表現をしたとき:
- 「Vaultを公開して」「デジタルガーデンを更新」「Quartzをデプロイ」
- 「awa-garden に push」「religion-garden に push」「cpg-vault に push」「solution を同期」
- 「/vault-publish」「/vault-publish religion」のように明示的に呼び出されたとき
- 「同期だけして」「ローカルで先に見たい」「push せずに反映」「プレビューだけ」→ `--sync-only` を使う（下記「Sync-only モード」参照）

### ターゲットの決め方

1. ユーザーが `religion`／`宗教`／`religion-garden` 等を明示、または直前の会話が `D:\Vault\religion` 配下のVault操作なら **religion**。
2. ユーザーが `阿波`／`awa`／`awa-garden` 等を明示、または直前の会話が `D:\Vault\awa` 配下のVault操作なら **awa**。
3. ユーザーが `solution`／`WMS`／`TMS`／`食品`／`お菓子` 等を明示、または直前の会話が `D:\Vault\solution` 配下のVault操作なら **solution**。
4. ユーザーが `cpg`／`CPG`／`cpg-vault`／`飲料`／`化粧品`／`cosme` 等を明示、または直前の会話が `D:\Vault\cpg` 配下のVault操作なら **cpg**（`cosme`はcpgに統合済みのため cpg ターゲットとして扱う）。
5. どれとも判断できない場合は、明示的にユーザーへ確認する（黙って awa を既定にしない — 誤ったリポジトリへ push する事故を防ぐため）。

## Pipeline (in order)

0. **Vault Hygiene & Pre-flight Audits (保守・事前監査)**:
   - **赤リンク・異体字監査 (`scripts/audit_vault_links.py`)**:
     ```bash
     python scripts/audit_vault_links.py --vault <vault> --check-redlinks --top 30
     python scripts/audit_vault_links.py --vault <vault> --find-variants
     python scripts/audit_vault_links.py --vault <vault> --fix-variants [--apply]
     ```
     Vault内の未作成ノートへのリンク（赤リンク）を検出。特に「売↔賣」「弥↔彌」「島↔嶋」「高↔髙」などの漢字の表記揺れ（異体字）を自動検出し、`--apply` で安全に一括正規化。
   - **タグ監査＆正規化 (`scripts/audit_vault_tags.py`)**:
     ```bash
     python scripts/audit_vault_tags.py --vault <vault> --audit
     python scripts/audit_vault_tags.py --vault <vault> --normalize [--apply]
     ```
     Frontmatter内のタグ集計、`阿波忌部` vs `氏族/阿波忌部` などの階層表記揺れを可視化し、5:1ルールで自動正規化。

1. **Sync & Sanitization**: `<sync-script>` を実行
   - **Mermaid自動構文・コントラスト検査 (`mermaid-hygiene` / `validate_mermaid.py`)**: 同期開始前に全Markdown内のMermaid構文（矢印・クォート・サブグラフ記号・暗色背景コントラスト）を自動検証。エラー時は安全に同期停止。
   - **Mirror Vault subtrees** → `<quartz-repo>/content/`
   - **一括サニタイズ (`scripts/sanitize_quartz_content.py`)**:
     1. Frontmatter修正 (YAML不正・未クォートwikilink対応)
     2. Dataviewブロック除去 (静的プレースホルダー化)
     3. 壊れたwikilink除去 (404赤リンク防止・プレーンテキスト化 / Shrine-heritager・Web_Archives元URLスマート解決)
     4. AI編集ログ・更新履歴の脱色除去 (読者向けクリーン化)
     5. 改行コード正規化 (LF統一)

2. **Build verify** (default ON、`--skip-build` で skip 可):
   - `cd <quartz-repo> && npx quartz build` を実行
   - YAML エラーなど発生時は **halt して詳細表示**(ユーザーが Vault を直す必要がある)

3. **Post-Build Internal Link Audit (事後監査・検証)**:
   - **Quartzリンク切れ監査 (`scripts/audit_quartz_links.py`)**:
     ```bash
     python scripts/audit_quartz_links.py --public-dir <quartz-repo>/public [--report-file report.md]
     ```
     生成されたHTML群を走査し、ブラウザ上で404になる内部リンクが存在しないかを完全検証。

4. **`--sync-only` ならここで停止**（下記「Sync-only モード」参照）。commit/push は行わない。

5. **Pre-Commit 監査 & 承認確認（重要規律）**:
   - `python scripts/audit_mermaid_styling.py <vault>` でダイアグラムのアクセシビリティを検証。
   - **必ずユーザーに変更ファイル一覧、変更概要、コミットメッセージ案を提示し、明示的な承認指示を待つ（自動コミット・自動プッシュ厳禁）。**

6. **Commit & Push**: ユーザー承認後、安全に実行
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
- `<sync-script>` の存在を確認、`<quartz-repo>/.git` の存在を確認（cpgは`<quartz-repo>` = `D:\Vault\cpg`）

### 2. Run sync

ユーザーが `--skip-sync` を渡した場合はこのステップを飛ばす（直前に `--sync-only` 等で同じターゲットのsyncが成功済みの場合に使う）。commit message 用のサマリがない場合は「(sync skipped — 直前の実行結果を使用)」とだけ記録する。

awaターゲット:
```bash
cd "D:/Vault/awa/_work" && uv run python _sync_to_quartz.py
```

religionターゲット:
```bash
cd "D:/Vault/religion/_work" && uv run python _sync_to_quartz_religion.py
```

solutionターゲット:
```bash
cd "D:/Vault/solution/_work" && python _sync_to_quartz_solution.py
```

cpgターゲット:
```bash
cd "D:/Vault/cpg/_work" && python _sync_to_quartz_cpg.py
```
（contentミラー先はVault外の`C:/Users/iidam/quartz-cpg-content`固定。他ターゲットと違い環境変数指定は不要——ローカル実行時のデフォルト値がそのまま正しい）

スクリプトの最後のサマリ(8行程度)を保持して commit message 生成に使う。失敗時(exit non-zero)は **halt して stderr を表示**。

### 3. Build verify (default)

```bash
cd <quartz-repo> && npx quartz build
```
（awaなら `C:/Users/iidam/quartz`、religionなら `C:/Users/iidam/quartz-religion`、solutionなら `C:/Users/iidam/quartz-solution`）

**cpgのみ**contentディレクトリを明示指定する:
```bash
cd "D:/Vault/cpg" && npx quartz build -d "C:/Users/iidam/quartz-cpg-content"
```

成功時の最終行は `Done processing N files in Xs`。失敗時は YAML/Mermaid エラーの可能性が高い。エラー出力をそのままユーザーに見せて halt する。

**cpg固有の罠**: ビルド出力に`Parsed 0 Markdown files`のような0件表示が出たら、contentディレクトリ（`-d`で指定した先）がリポジトリの`.gitignore`パターンに一致していないか確認する（Quartzの`glob()`は`gitignore: true`でglobbyを呼ぶため、gitignore対象ディレクトリは中身があっても「見えない」扱いになる）。ローカルのVault外配置はこの罠を回避済みだが、CI環境のワークフローを変更する際は特に注意。

ユーザーが `--skip-build` を渡した場合のみこのステップを飛ばす。

### 4. Stage and commit

```bash
cd <quartz-repo> && git add -A && git status --short | head -5
```
（cpgは`<quartz-repo>` = `D:/Vault/cpg`）

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
（cpgは`<quartz-repo>`の代わりに`D:/Vault/cpg`）

失敗 (`Connection was reset` / `RPC failed` 等) → 一度だけ retry:

```bash
cd <quartz-repo> && git config http.postBuffer 524288000 && git push 2>&1
```

それでも失敗したら halt してエラー表示。

### 6. Report

成功時、ユーザーに以下を伝える:
- 公開 URL: `<pages-url>`
- Actions URL: `https://github.com/<gh-repo>/actions`
- 「GitHub Actions が自動でデプロイします(約 1-2 分)」（**cpgターゲットは除く**、下記参照）
- **cpgターゲットのみ追加で伝える**: 「Basic認証が必要（ID/PASSはCloudflare Pages環境変数 `BASIC_AUTH_USER`/`BASIC_AUTH_PASS` で管理、リポジトリには含まれない）」。デプロイはGitHub Actions（`cloudflare/wrangler-action`）経由で対象repoの Cloudflare Pages プロジェクトへ行われる。GitHub Pagesではないため `github.io` URLは存在しない。`sources/`（一次資料アーカイブ）もpublicに含まれBasic認証保護下で公開される旨（非公開の生データではなく既にVault内で管理されている引用元アーカイブである点は明記するが、機微情報を含む場合は個別に判断）。**cpgは所要時間が他ターゲットと大きく異なり、実測で10〜15分以上（一度は15分超）かかることが常態**。「約1-2分」ではなく「約10-15分、それ以上かかることもある」と案内し、一度の確認で完了しないことを前提に複数回のポーリングを促す。**進行中か停止しているかの判断は、job全体のstatusだけでなくstep単位のconclusion（`gh api .../jobs`）と、runの`updated_at`タイムスタンプが直近で更新され続けているかを併用する**。「Build Quartz」ステップが完了済みで「Deploy to Cloudflare Pages」だけがin_progressのまま長時間続いていても、それ自体は正常な範囲（ハングではない）というのがこのrepoでの実測パターン。

デプロイ進行状況の確認コマンド（`<gh-repo>` と workflow ID はターゲットに応じて選ぶ）:
- awa: `gh api repos/iida-masashi/awa-garden/actions/workflows/281917513/runs --jq '.workflow_runs[0] | {status, html_url}'`
- religion: `gh api repos/iida-masashi/religion-garden/actions/workflows/321319403/runs --jq '.workflow_runs[0] | {status, html_url}'`
- cpg: `gh api repos/iida-masashi/cpg-vault/actions/workflows/336933300/runs --jq '.workflow_runs[0] | {status, conclusion, html_url}'`（cpgはconclusionがsuccessでもデプロイstepがskippedのことがある、または成功と出てもコンテンツ0件のことがあるため、`gh api repos/iida-masashi/cpg-vault/actions/runs/<id>/jobs`でstep単位の確認に加え、ログの`Parsed N Markdown files`行の数値も必ず確認する）

## Arguments

| Flag | Effect |
|---|---|
| `awa` / `religion` / `solution` / `cpg` | 対象ターゲットを明示指定（位置引数、例: `/vault-publish religion`） |
| `--skip-sync` | Step 2 (sync) をスキップ。直前に同じターゲットで `--sync-only` 等によりsyncが成功済みの場合に、sync出力の再実行・再表示を避ける |
| `--skip-build` | Step 3 (build verify) をスキップ。push 速度優先 |
| `--sync-only` | commit/push (Step 4-5) を行わず sync+build までで停止。push せずローカルプレビューしたい場合に使う |
| `--serve` | `--sync-only` と併用。build後に `npx quartz build --serve` を起動しプレビューサーバーを立てる |
| `--message "..."` | commit message を上書き |
| `--dry-run` | sync スクリプトを `--dry-run` 付きで実行し、何も commit/push しない |

## What this skill does NOT do

- Vault 側のファイルを編集(同期は片方向 Vault → content) — Vault は source of truth
- 公開設定の変更(repo の visibility, baseUrl, ignorePatterns 等) — それらは別途手動
- Cloudflare側の設定変更(環境変数、Pagesプロジェクト作成等、cpgターゲット) — 別途 `wrangler` で手動
- watch mode / 自動定期実行 — ユーザーが明示的に呼び出した時のみ動く
- GitHub Actions の他 workflow を停止 — 他は無害なので触らない
- 複数ターゲットを跨いだ操作(awaとreligionを同時にpush等) — 必ず1回の呼び出しにつき1ターゲット

## Notes

- push なしで同期・ローカルプレビューだけしたい場合は `--sync-only`（旧 `vault-sync` スキルは本スキルに統合済み、単独では存在しない）
- 同期スクリプトは idempotent(何度実行しても同じ結果)
- Vault と content の同期は size + mtime 比較。Vault でのタイムスタンプだけ更新したファイルでも copy が走るが、内容は同じなので git diff には現れない
- awa: `D:\Vault\awa\_work\QUARTZ_SYNC_README.md` に運用ドキュメント完備
- cpg: `iida-masashi/cpg-vault` は **private**。他3ターゲットと違い2リポジトリ構成ではなく単一リポジトリ（詳細は上記「cpgターゲットの特殊性」）。公開先の Cloudflare Pages (`cpg-vault.pages.dev`) は `functions/_middleware.ts` による Basic 認証で限定公開している。`sources/`サブツリーはユーザー判断でリポジトリに含まれ、そのまま公開される（一次資料アーカイブのリンク切れ対策が目的）。`.gitignore`は`sources/**/.chroma_db/`パターンでconvMDキャッシュのみ除外
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
| cpg: push後もサイトが更新されない/401のまま | GitHub Actions（`wrangler-action`）が失敗している可能性。`gh run list --repo iida-masashi/cpg-vault --limit 1` で確認。Cloudflare側の `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` (GitHub Secrets) または `BASIC_USERNAME`/`BASIC_PASSWORD` (Cloudflare Pages環境変数、未設定時は`functions/_middleware.ts`内のデフォルト値が使われる) が未設定・期限切れだと失敗する |
| cpg: Actions run が success でもサイトが更新されない | `conclusion: success` は `Deploy to Cloudflare Pages` stepが`skipped`でも成立する（他のstepが全部successならjob全体もsuccess扱いになるため）。`gh api repos/iida-masashi/cpg-vault/actions/runs/<id>/jobs`でstep単位のconclusionを必ず確認する。Secretsが1件も無いと毎回skippedになる |
| cpg: Actions run が success で全step successでもコンテンツが空/激減している | **最重要の罠（2026-09-09に実際に本番サイトが一時空になった）**。ビルドログの`Parsed N Markdown files`行を必ず確認する。`N`が想定より大幅に少ない・0の場合、`-d`で指定したcontentディレクトリがリポジトリの`.gitignore`パターンに一致している可能性が高い。Quartzの`glob()`は`globby({gitignore: true})`を使うため、gitignore対象ディレクトリは中身があっても「見えない」扱いになりビルドが静かに空サイトを生成する。緊急時は`gh workflow run deploy-legacy.yml --repo iida-masashi/cpg-vault`で旧`build_site.py`パイプラインを手動実行し一時復旧できる |
| cpg: `Deploy to Cloudflare Pages`のif条件が機能しない | GitHub Actionsは`secrets`コンテキストをjob/stepの`if:`式で直接参照できない（`Unrecognized named-value: 'secrets'`でworkflow file自体がparse失敗しjob数0件になる）。job-levelの`env:`に一度代入してからstepの`if: env.X == 'true'`で参照する形にする（`.github/workflows/deploy.yml`は対応済み、崩さないこと） |
| cpg: `Deploy to Cloudflare Pages`が`[code: 7003]`で失敗 | `CLOUDFLARE_ACCOUNT_ID`が不正（コピー時の文字欠落等）。Cloudflare Account IDは32文字の16進数文字列。`echo -n "$ID" \| wc -c`で長さ確認を促す |
| cpg: `Deploy to Cloudflare Pages`が`Authentication error [code: 10000]`で失敗 | `CLOUDFLARE_API_TOKEN`の権限不足、またはAccount Resourcesが対象アカウントに紐付いていない。`curl -s https://api.cloudflare.com/client/v4/user/tokens/verify -H "Authorization: Bearer <token>"`でトークン自体の有効性を確認し、`curl -s https://api.cloudflare.com/client/v4/accounts/<account-id>/pages/projects/cpg-vault -H "Authorization: Bearer <token>"`でプロジェクトへのアクセス権を確認する |
| cpg: `actions/checkout`が`File name too long`で失敗 | GitHub ActionsのUbuntuランナー（ext4、255バイト制限）とWindows/NTFS（文字数ベース制限）の差。日本語ファイル名は1文字3バイトになるため、Windows上では作成できてもpush後のActions checkoutで失敗する。`python3 -c "print(len('<filename>'.encode('utf-8')))"`で事前確認し、255バイトを超える場合は短縮する |
| cpg: ローカルプレビュー中にブラウザがメモリ不足でクラッシュする | `sources/`配下の一次資料アーカイブ（SEC提出書類等、最大2.7MB）の全文が検索インデックス（`contentIndex.json`）に含まれ肥大化するのが原因（2026-09-09に実害あり、修正済み）。`quartz/plugins/emitters/contentIndex.tsx`の`sources/`向けcontent空化パッチが外れていないか確認する。`ls -la public/static/contentIndex.json`が数MB以上あれば要注意 |
| cpg: 旧build_site.py（`deploy-legacy.yml`）を使う場面 | Quartzパイプライン（`deploy.yml`）に問題が起きた際の緊急ロールバックのみ。通常運用では使わない。`gh workflow run deploy-legacy.yml --repo iida-masashi/cpg-vault`で手動起動、`--project-name=cpg-vault`は同一なので同じCloudflare Pagesプロジェクトを上書きする点に注意（Quartz版に戻す際は改めて`deploy.yml`側をpushし直す） |
| Bashツールで `uv: command not found` | `uv`がPATHに乗っていない環境（WinGet配下等にインストール済みでも）で起きる。`_sync_to_quartz*.py`自体はstdlibのみで動くので `/c/Python314/python <sync-script>` のように system python で直接叩けば1〜3のミラー処理は完走する。ただしスクリプト内部で `_fix_quartz_frontmatter.py` / `_dewikify_broken.py` / `_strip_dataview.py` / `_check_mermaid_comments.py` を `subprocess.run(["uv", "run", "python", ...])` 経由で呼ぶ設計のため、そこで同じエラーが出て後処理が止まる。後処理4スクリプトもいずれも標準ライブラリのみに依存しているため、`_work/` 配下から同様に system python で1本ずつ直接実行すれば代替できる（実行順: frontmatter fix → dewikify → dataview strip → mermaid check）。`npx quartz build` はNode.js経由なのでこの問題の影響を受けない。 |
