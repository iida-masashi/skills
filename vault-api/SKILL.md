---
name: vault-api
description: Obsidian Local REST API経由でObsidian Vaultを直接操作する。MCPの代替で、Bash経由のPowerShellスクリプト群（vault-search/vault-read/vault-batch-summary/vault-list/vault-append/vault-mkdir/vault-move/vault-delete/vault-orphans/vault-thin-notes）。全文検索・構造化検索・読み取り・複数ファイル一括サマリ・一覧・追記・フォルダ新規作成・見出し相対挿入・リネーム・削除・孤立ノート検出・薄ノート検出をBashツールで実行可能。
disable-model-invocation: false
---

# vault-api — Obsidian Local REST API ラッパー

Obsidian Vault を Obsidian Local REST API v4.1.2 経由で操作する PowerShell スクリプト群。
MCPサーバーを登録できない・使いたくない環境向けの代替実装。

## 複数Vault対応

複数のVaultをそれぞれ別のAPIキーで管理できる。設定ファイルは`_secrets/obsidian.<vault名>.json`という命名規則（例: `obsidian.<vault名>.json`。vault名は自分で決める任意の識別子）。

Obsidian Local REST APIは**アプリで現在開いているVaultにしか応答しない**ため、実際に扱えるのは常に「今Obsidianで開いているVault」1つだけ。複数Vaultを同時操作するのではなく、開いているVaultに応じて対応するAPIキーへ切り替える仕組み。

切り替え方法：
- 各コマンド・関数に `-Vault <vault名>` を指定する（省略時は `$env:OBSIDIAN_VAULT`、それも未設定なら既定Vault＝`obsidian-api.psm1`内`$script:defaultVault`で設定した値）
- 同一セッションで繰り返し使うなら `Set-ObsidianVault -Vault '<vault名>'` を一度呼ぶと、以降そのプロセス内では省略時にそのVault用キーが使われる

Vaultを切り替える際は、**Obsidianアプリ側でも対象Vaultを開いてから**該当する`-Vault`を指定すること。アプリで開いているVaultと指定したVaultのAPIキーが一致しないと `40101 Authorization required` になる（誤操作防止の安全弁として機能する）。

後方互換: `_secrets/obsidian.json`（Vault名なしの旧命名）のみが存在する環境では、`-Vault`指定に関わらずそのファイルが使われる。

## 構成

| ファイル | 役割 |
|---|---|
| `_secrets/obsidian.<vault名>.json` | Vaultごとの API Key・接続情報（gitignore済み） |
| `tools/obsidian-api.psm1` | 共通モジュール（関数群） |
| `tools/vault-search.ps1` | Vault全文検索 |
| `tools/vault-read.ps1` | ファイル読み取り |
| `tools/vault-batch-summary.ps1` | 複数ファイルのfrontmatter+先頭数行だけを一括取得（分類・下調べフェーズのトークン節約用） |
| `tools/vault-list.ps1` | ディレクトリ一覧 |
| `tools/vault-append.ps1` | ファイル末尾追記 |
| `tools/vault-mkdir.ps1` | フォルダ新規作成（マーカーファイル書き込みによる合成操作） |
| `tools/vault-move.ps1` | ファイルのリネーム/移動 |
| `tools/vault-delete.ps1` | ファイル削除 |
| `tools/vault-orphans.ps1` | 孤立ノート（どこからもwikilinkされていないノート）検出。`-SubPath`絞り込み・`-ExcludeKeywords`・`-OutCsv`対応 |
| `tools/vault-thin-notes.ps1` | 薄ノート（指定バイト数未満）検出。`-Folder`絞り込み・`-Threshold`・`-OutCsv`対応 |
| `tools/vault-shousai-triage.ps1` | `<親>_詳細/<子>.md`分割構造の統合しやすさをprose行数で判定。`-Folder`絞り込み・`-OutCsv`・`-Summary`対応 |
| `tools/vault-basename-collisions.ps1` | 同一basename（拡張子除くファイル名）を持つ.mdファイルの検出。wikilinkの曖昧参照（複数ファイルが同名でどちらに解決されるか不定）を洗い出す。`-OutCsv`対応 |
| `tools/maintenance/` | 個人研究Vault専用の整備ツール群（vault-links/vault-gps等。Local REST APIではなくファイルシステム直接操作、`.gitignore`対象。詳細は`tools/maintenance/README.md`） |

## 使い方（Bash経由）

全ラッパー（vault-orphans/vault-thin-notesを除く）は `-Vault <vault名>` を受け付ける。省略時は `$env:OBSIDIAN_VAULT` または既定Vault。

### 全文検索

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-search.ps1 -Query "検索語" -Limit 20 [-Vault <vault名>]
```

例：「検索語」を検索 → コンテキスト付きで結果を表示

### ファイル読み取り

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-read.ps1 -Path "フォルダ/サブフォルダ/note.md" [-Vault <vault名>]
```

オプション `-Lines N` で先頭N行のみ取得。

### 複数ファイル一括サマリ（トークン節約）

```bash
pwsh -NoProfile -Command "& '<このスキルのtools>/vault-batch-summary.ps1' -Paths @('フォルダ/a.md','フォルダ/b.md') -Vault <vault名>"
# または大量件数はファイル経由で
pwsh -NoProfile -File <このスキルのtools>/vault-batch-summary.ps1 -PathsFile paths.txt -Lines 5 [-Vault <vault名>]
```

各ファイルのfrontmatterと本文冒頭N行（既定5行）だけを返す。分類・棚卸し・増補対象の下調べなど「対象N件の現状をざっと把握したい」場面で、1件ずつ`vault-read`するより出力トークンを大幅に削減できる。**Bash経由で`-Paths`に配列を渡す場合はカンマ区切り文字列ではなく`pwsh -Command`+PowerShell配列リテラル`@(...)`を使うこと**（`-File`経由でカンマ区切り文字列を渡すと1要素として扱われ404になる）。件数が多い場合は`-PathsFile`で改行区切りのパス一覧ファイルを渡す方が安全。**`-PathsFile`にBashのheredoc（`/dev/stdin`）は使えない**（`Get-Content -LiteralPath`が`/proc/self/fd/0`を解決できずエラーになる。PowerShellはWindowsプロセスとしてheredocのfd経由読み込みに対応していないため）。一時ファイルに書き出してから渡すか、件数が少なければ`-Paths`配列リテラルを使うこと。

### フォルダ新規作成

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-mkdir.ps1 -Path "新フォルダ/サブフォルダ" [-Vault <vault名>]
```

Local REST APIに専用のmkdirエンドポイントはなく、Vaultはファイルシステムのミラーでフォルダはファイルの存在に付随して作られる。そのため`_placeholder.md`というマーカーファイルを対象フォルダ配下に書き込むことでフォルダ自体を先に作成する（ドットファイル`.gitkeep`はObsidian側で隠しファイル扱いとなり取得・削除ができないため使わない — 検証済み）。フォルダに実ノートを追加したら、このマーカーファイルは`vault-delete.ps1`で削除してよい（残しても支障はない）。

### ディレクトリ一覧

```bash
# ルート一覧
pwsh -NoProfile -File <このスキルのtools>/vault-list.ps1 [-Vault <vault名>]

# 特定フォルダ
pwsh -NoProfile -File <このスキルのtools>/vault-list.ps1 -Path "フォルダ/" [-Vault <vault名>]
```

### 追記

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-append.ps1 -Path "..." -Content "追記内容" [-Vault <vault名>]
# または
pwsh -NoProfile -File <このスキルのtools>/vault-append.ps1 -Path "..." -ContentFile "/tmp/addition.md" [-Vault <vault名>]
```

### リネーム/移動

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-move.ps1 -From "旧フォルダ/note.md" -To "新フォルダ/note.md" [-Vault <vault名>]
```

内部的には「新パスへ書き込み→旧パス削除」の合成操作（Local REST APIに専用のrename/moveエンドポイントがないため）。

### 削除

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-delete.ps1 -Path "フォルダ/note.md" [-Vault <vault名>]
```

### 孤立ノート検出

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-orphans.ps1 -VaultRoot "<Vaultパス>" [-SubPath "フォルダ"] [-ExcludeKeywords MOC,目次] [-OutCsv path] [-Summary [-Top 10]]
```

Vault配下の全 `.md` を再帰収集し（`.obsidian/`・`templates/`・`資料/`・`MEMORY.md` を除外）、他のどこからも `[[wikilink]]` されていないノートをサイズ降順で出力する。件数が多いVaultでは`-Summary`を付けるとフォルダ別集計+サイズ上位N件のみを返し、生の全件一覧を出力しないためトークンを節約できる（全件が必要な場合は`-OutCsv`でファイル出力）。

### 薄ノート検出

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-thin-notes.ps1 -VaultRoot "<Vaultパス>" [-Folder "部分一致名"] [-Threshold 3000] [-OutCsv path] [-Summary [-Top 10]]
```

指定フォルダ（省略時は全体）配下で指定バイト数未満の `.md` をサイズ昇順で出力する（`.obsidian/`・`templates/`・`資料/`・`_work/` は除外）。強化対象のノートを体系的に発見する用途。`-Summary`はフォルダ別集計+最小サイズ上位N件のみ返す（`vault-orphans`と同様）。

### `_詳細`分割構造の統合しやすさ判定

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-shousai-triage.ps1 -VaultRoot "<Vaultパス>" [-Folder "部分一致名"] [-OutCsv path] [-Summary [-Top 20]]
```

「親ノート＋`<親名>_詳細/`フォルダ内の子ノート」という分割構造（近代化の過程で頻出）を全件走査し、子ノートの**地の文（prose）行数**で統合のしやすさを`Shape`列に分類する:

| Shape | 意味 |
|---|---|
| `EMPTY` | 子ノート0件（フォルダのみ残存。ファイルシステム上空ディレクトリとして残るだけで実害はないが、整理したい場合はユーザーの`!`実行等で削除） |
| `LINK_STUB` | 子1件・地の文ほぼ0行（リンク集）。機械的統合の最有力候補 |
| `SHORT` | 子1件・地の文少数行。統合候補だが軽く目を通す |
| `CHILD_LARGER` | 子の合計サイズが親を上回る。統合方向が逆転しうるため要通読 |
| `NEEDS_READ` | 子が複数件、または内容量が中程度。通読して統合可否を判断 |

**サイズだけで統合可否を判定しない**（`feedback_vault_thin_size_vs_quality`参照）。`Shape=LINK_STUB/SHORT`でも、子ノートが親以外の複数ノートから直接リンクされている場合（`vault-search`で確認）は、単純統合すると被リンクが壊れる。その場合は「親へ統合し、外部参照元のリンクを付け替える」（`Merge-ObsidianChildNote`参照）か、統合を見送るかをユーザーに確認する。

**子の方が親より充実している場合**（`Shape=CHILD_LARGER`や、実際に読んで判明するケース）は、通常と逆に「子の内容を主体にし、親の要旨・frontmatter・被リンクを子へ吸収した上で親を削除する」逆統合を検討する。子ノートへの外部被リンク数が多いほど、子basenameを残す逆統合が被リンク破壊を避けられる。

**親子で祭神論・由来説など対立する記述がある場合**（同じ主題を別角度から論じているだけで、単純な重複ではないケース）は、どちらかを採用して他方を捨てるのではなく、両論を「観点」「通説」「阿波説」等の対比表や併記節として親ノートに残す。

### basename衝突（曖昧wikilink）の検出

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-basename-collisions.ps1 -VaultRoot "<Vaultパス>" [-OutCsv path]
```

同一basename（拡張子を除くファイル名）を持つ`.md`ファイルをVault全体から検出する。wikilink（`[[名前]]`）はbasenameで解決されるため、同名ファイルが複数フォルダに存在すると、そのbasenameへのリンクがどちらのファイルに解決されるか不定になる（曖昧参照）。典型例は「詳細論考ポータル」「概要と阿波説における重要性」のような、`_詳細/`分割構造で使い回されがちな**汎用的な子ノート名**。全国に複数実在する同名神社（例：忌部神社、鴨神社）のような**正当な重複**も検出されるため、出力は必ず個別に精査し、実際に問題があるもの（同一主題のノートが誤って別フォルダに複製されている等）だけを対処する。

## PowerShell モジュールとして直接使う

全関数が `-Vault <vault名>` を受け付ける（省略時は `$env:OBSIDIAN_VAULT` または既定Vault）。

```powershell
Import-Module '<このスキルのtools>/obsidian-api.psm1'

# 以降このプロセスの既定Vaultを切り替え（$env:OBSIDIAN_VAULTをセットするだけの薄いラッパー）
Set-ObsidianVault -Vault '<vault名>'

# 疎通テスト
Test-ObsidianApi -Vault <vault名>

# 検索
Search-ObsidianVault -Query '検索語' -ContextLength 100 -Vault <vault名>

# 読み取り
Get-ObsidianNote -FilePath 'フォルダ/サブフォルダ/note.md' -Vault <vault名>

# ルート一覧
Get-ObsidianVaultList -Vault <vault名>

# ディレクトリ一覧
Get-ObsidianDirList -DirPath 'フォルダ/サブフォルダ/' -Vault <vault名>

# 追記
Append-ObsidianNote -FilePath '...' -Content '追記内容' -Vault <vault名>

# 完全上書き
Write-ObsidianNote -FilePath '...' -Content '新内容' -Vault <vault名>

# フォルダ新規作成（マーカーファイル書き込みによる合成操作）
New-ObsidianFolder -FolderPath '新フォルダ/サブフォルダ' -Vault <vault名>

# 削除
Remove-ObsidianNote -FilePath '...' -Vault <vault名>

# リネーム/移動（新規作成+旧パス削除の合成）
Move-ObsidianNote -FromPath '旧パス.md' -ToPath '新パス.md' -Vault <vault名>

# 見出し/ブロック相対挿入（frontmatter更新や特定セクションへの差し込み）
# heading の Target は '#' を含めず、ドキュメントルートから対象見出しまでの配列で指定する
# （例: 本文が「# タイトル」>「## 参考文献」なら @('タイトル','参考文献')。単一文字列を渡すとルート直下の見出し扱いになる）
Edit-ObsidianNoteSection -FilePath '...' -TargetType heading -Target @('タイトル', '参考文献') -Operation append -Content '- 追加の参考文献' -Vault <vault名>
# frontmatterの値を更新する場合は -Content ではなく -Value を使う（型付きJSON値）
Edit-ObsidianNoteSection -FilePath '...' -TargetType frontmatter -Target 'status' -Operation replace -Value 'reviewed' -Vault <vault名>
```

> **注意：`heading`+`append`はセクション「末尾」への追記であり、テーブルの最終行やblockquote（`> [!warning]`等）の内側に挿入する機能ではない。** テーブルの行として追加したい／blockquoteの箇条書きとして追加したいのにこれを使うと、セクション末尾に「テーブル外の孤立した1行」「blockquote外の孤立した箇条書き」が挿入され、Markdown構造が壊れる（実際に発生・要Write再修正）。**テーブル内の行追加は`Add-ObsidianTableRow`、blockquote内の追記は`Add-ObsidianCalloutLine`を使うこと**（下記）。

```powershell
# テーブルの最終行の直後に新しい行を安全に追加（全文取得→既存最終行を目印に文字列置換→上書き、を内部で実行）
Add-ObsidianTableRow -FilePath '...' -AnchorRowText '| 既存の最終行 | ... | ... |' -NewRow '| 新しい行 | ... | ... |' -Vault <vault名>

# blockquote/callout（> [!warning] 等）の最終行の直後に新しい箇条書きを安全に追加
# NewLineContentには '>' プレフィックスを付けない（自動で '> ' が付与される）
Add-ObsidianCalloutLine -FilePath '...' -AnchorLineText '> - 既存の最終行' -NewLineContent '追加する箇条書き' -Vault <vault名>
```

いずれも `AnchorRowText`/`AnchorLineText` はファイル内で一意な文字列である必要があり、0件または複数件ヒットした場合はエラーで停止する（サイレントな誤挿入を防ぐ安全策）。

```powershell
# ファイル内の文字列を安全に置換（改行コード自動判定＋一意性チェック付き）
# Old/New 内の改行は \n（LF）で書けばよい。対象ファイルの実際の改行コード（CRLF/LF混在Vaultで
# 都度手動判定するのが手間）に自動変換してから比較・置換する。既定では一致件数が1件でないとエラー
# （0件=気づかず失敗、2件以上=意図しない多重置換、を両方防ぐ）。全箇所に適用したい場合のみ -AllowCount 0
Set-ObsidianNoteText -FilePath '...' -Old "- [[旧リンク]]" -New "- [[新リンク]]" -Vault <vault名>

# 「親ノート＋<親名>_詳細/子ノート」分割構造の統合（親上書き→外部参照元の一括付け替え→子削除、を1呼び出しで）
# ExternalRepoints には、子ノートへの被リンクを vault-search で洗い出した結果を列挙する
# （本関数自体は被リンクの自動検出はしない）。目次・MOC等に親への既存リンクが既にある場合は
# New に空文字を渡して行削除にする（付け替えではなく重複解消）
Merge-ObsidianChildNote -Vault <vault名> `
    -ParentPath '式内社/.../阿波神社.md' -MergedContent $mergedContent `
    -ChildPath '式内社/.../阿波神社_詳細/各論.md' `
    -ExternalRepoints @(
        @{ Path = '式内社/00_式内社_目次.md'; Old = '- [[各論]]'; New = '- [[阿波神社]]' }
    )
```

```powershell

# タグ・frontmatterなどJsonLogic条件での構造化検索
Search-ObsidianVaultAdvanced -Query @{ 'in' = @('検索語', @{'var'='tags'}) } -Vault <vault名>

# 現在Obsidianで開いているノート
Get-ObsidianActiveNote -Vault <vault名>

# 実行可能コマンド一覧 / コマンド実行（例: 検索インデックス再構築）
Get-ObsidianCommandList -Vault <vault名>
Invoke-ObsidianCommand -CommandId 'app:reload' -Vault <vault名>
```

> **ルート一覧は `Get-ObsidianVaultList`、サブフォルダは `Get-ObsidianDirList -DirPath '<相対>/'`。**
> `Get-ObsidianDirList -DirPath ''`（空文字）は `Cannot bind argument ... empty string` でエラーになるため、ルートには必ず `Get-ObsidianVaultList` を使う。

## 既存ツールとの比較

| ツール | 強み | 弱み |
|---|---|---|
| **vault-api（本スキル）** | Obsidian経由で **wikilink解決・タグ検索が正確** / Obsidian再起動不要 | Obsidianアプリ起動必須 |
| **Read/Grep/Glob（標準）** | Obsidian起動不要、高速 | Obsidian独自機能（タグ・dataview等）不可 |

**推奨使い分け**：
- **全文検索でコンテキスト付き結果が欲しい** → `vault-search`
- **大量のファイル走査が必要** → Grep/Glob
- **frontmatter編集・追記** → Edit/Write
- **wikilink構造を理解した検索** → `vault-search`
- **孤立ノート検出** → 本スキルの `tools/vault-orphans.ps1`
- **薄ノート検出** → 本スキルの `tools/vault-thin-notes.ps1`
- **複数ファイルの現状をざっと下調べしたい** → 1件ずつ`vault-read`せず `tools/vault-batch-summary.ps1` でfrontmatter+冒頭だけ一括取得

## API疎通確認

```bash
pwsh -NoProfile -Command "Import-Module '<このスキルのtools>/obsidian-api.psm1'; Test-ObsidianApi -Vault <vault名> | Format-List"
```

正常時：`status: OK`、`authenticated: True`

## 利用可能エンドポイント（Obsidian Local REST API with MCP v5.1.0、markdown-patch 2.x形式）

| HTTP | パス | 内容 | ラッパー関数 |
|---|---|---|---|
| GET | `/` | 状態確認・認証 | `Test-ObsidianApi` |
| GET | `/vault/` | ルートディレクトリ一覧 | `Get-ObsidianVaultList` |
| GET | `/vault/<dir>/` | サブディレクトリ一覧 | `Get-ObsidianDirList` |
| GET | `/vault/<file>` | ファイル内容取得 | `Get-ObsidianNote` |
| PUT | `/vault/<file>` | ファイル作成/上書き | `Write-ObsidianNote` |
| POST | `/vault/<file>` | ファイル末尾追記 | `Append-ObsidianNote` |
| PATCH | `/vault/<file>` | 見出し・ブロック・frontmatterへの相対挿入 | `Edit-ObsidianNoteSection`（テーブル行・blockquote行の追加は`Add-ObsidianTableRow`/`Add-ObsidianCalloutLine`＝GET+PUTの合成を使うこと） |
| DELETE | `/vault/<file>` | ファイル削除 | `Remove-ObsidianNote`（`Move-ObsidianNote`は書き込み+削除の合成） |
| POST | `/search/simple/?query=X` | 全文検索 | `Search-ObsidianVault` |
| POST | `/search/` | JsonLogic検索（タグ・frontmatter条件） | `Search-ObsidianVaultAdvanced` |
| GET | `/active/` | 現在開いているノート | `Get-ObsidianActiveNote` |
| GET | `/commands/` | コマンド一覧 | `Get-ObsidianCommandList` |
| POST | `/commands/<id>/` | コマンド実行（例: `app:reload`） | `Invoke-ObsidianCommand` |

## トラブルシュート

| 症状 | 対処 |
|---|---|
| **全文検索が全クエリで 500 (Internal Server Error)** | 検索インデックスが**改名/移動前の旧パス**を参照したまま。`Invoke-ObsidianApi` は `ENOENT ... open '<旧パス>'` を検知すると原因パスと対処法を含めたエラーメッセージを自動的に投げる → `Invoke-ObsidianCommand -CommandId 'app:reload'` でインデックス再構築。reload後にAPIが戻らない場合はObsidianを手動起動（サンドボックスから起動不可） |
| Bash経由のpwsh出力で日本語が文字化け | ラッパー(`vault-*.ps1`)は先頭で `[Console]::OutputEncoding = UTF8` 済み。`obsidian-api.psm1` を直接 `Import-Module` して自作スクリプトを書く場合は、そのスクリプト先頭でも同行を設定する |
| `Get-ObsidianDirList` で `Cannot bind ... empty string` | ルート一覧は `Get-ObsidianVaultList` を使う（上記参照） |
| `Move-ObsidianNote` 実行後に一部ノートのリンクが切れる | wikilinkはbasename参照のためフォルダ移動・拡張子維持では切れないが、**basename自体を変更した場合**は他ノートの `[[旧basename]]` 参照が残る。`tools/vault-orphans.ps1` で確認し手動修正するか、Grepで `\[\[旧basename` を検索して一括置換する |
| `40101 Authorization required` | `-Vault`で指定したAPIキーが、Obsidianアプリで実際に開いているVaultと一致していない。Obsidianアプリ側で対象Vaultを開いてから、対応する`-Vault`名を指定する |
| `Obsidian config not found for vault 'xxx'` | `_secrets/obsidian.xxx.json` が存在しない。Vault名のスペルを確認するか、そのVault用の設定ファイルを新規作成する |

## メモ

- wikilink は basename（拡張子・パスを除いたファイル名）でマッチする
- 検索が全クエリで500エラーになる場合、検索インデックスが改名/移動前の旧パスを参照している可能性がある。`/commands/app:reload/` をPOSTしてインデックスを再構築する
- Windows PowerShell 5.1はUTF-8ファイルをCP932として誤読することがあるため、pwsh (PowerShell 7) で実行する

## セキュリティ

- **API Key は Vaultごとに `_secrets/obsidian.<vault名>.json` に保管** — `.gitignore` で除外済み
- 接続先は `127.0.0.1:27124` のみ（ローカル限定）
- HTTPS自己署名証明書を使うため、PowerShellは `-SkipCertificateCheck` を使用
- Obsidian起動時のみAPIが動作
- 複数Vault管理時も、同時に応答できるのはObsidianアプリで実際に開いているVault1つのみ。誤ったVaultのAPIキーを指定すると `40101 Authorization required` になる（誤操作防止の安全弁）
