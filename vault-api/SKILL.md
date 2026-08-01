---
name: vault-api
description: Obsidian Local REST API経由でObsidian Vaultを直接操作する。MCPの代替で、Bash経由のPowerShellスクリプト群（vault-search/vault-read/vault-list/vault-append/vault-move/vault-delete）。全文検索・構造化検索・読み取り・一覧・追記・見出し相対挿入・リネーム・削除をBashツールで実行可能。
disable-model-invocation: false
---

# vault-api — Obsidian Local REST API ラッパー

Obsidian Vault を Obsidian Local REST API v4.1.2 経由で操作する PowerShell スクリプト群。
MCPサーバーを登録できない・使いたくない環境向けの代替実装。

## 構成

| ファイル | 役割 |
|---|---|
| `_secrets/obsidian.json` | API Key・接続情報（gitignore済み） |
| `tools/obsidian-api.psm1` | 共通モジュール（関数群） |
| `tools/vault-search.ps1` | Vault全文検索 |
| `tools/vault-read.ps1` | ファイル読み取り |
| `tools/vault-list.ps1` | ディレクトリ一覧 |
| `tools/vault-append.ps1` | ファイル末尾追記 |
| `tools/vault-move.ps1` | ファイルのリネーム/移動 |
| `tools/vault-delete.ps1` | ファイル削除 |
| `tools/maintenance/` | Vault整備ツール群（vault-orphans/vault-links/vault-gps等19本。Local REST APIではなくファイルシステム直接操作。詳細は`tools/maintenance/README.md`） |

## 使い方（Bash経由）

### 全文検索

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-search.ps1 -Query "検索語" -Limit 20
```

例：「検索語」を検索 → コンテキスト付きで結果を表示

### ファイル読み取り

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-read.ps1 -Path "フォルダ/サブフォルダ/note.md"
```

オプション `-Lines N` で先頭N行のみ取得。

### ディレクトリ一覧

```bash
# ルート一覧
pwsh -NoProfile -File <このスキルのtools>/vault-list.ps1

# 特定フォルダ
pwsh -NoProfile -File <このスキルのtools>/vault-list.ps1 -Path "フォルダ/"
```

### 追記

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-append.ps1 -Path "..." -Content "追記内容"
# または
pwsh -NoProfile -File <このスキルのtools>/vault-append.ps1 -Path "..." -ContentFile "/tmp/addition.md"
```

### リネーム/移動

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-move.ps1 -From "旧フォルダ/note.md" -To "新フォルダ/note.md"
```

内部的には「新パスへ書き込み→旧パス削除」の合成操作（Local REST APIに専用のrename/moveエンドポイントがないため）。

### 削除

```bash
pwsh -NoProfile -File <このスキルのtools>/vault-delete.ps1 -Path "フォルダ/note.md"
```

## PowerShell モジュールとして直接使う

```powershell
Import-Module '<このスキルのtools>/obsidian-api.psm1'

# 疎通テスト
Test-ObsidianApi

# 検索
Search-ObsidianVault -Query '検索語' -ContextLength 100

# 読み取り
Get-ObsidianNote -FilePath 'フォルダ/サブフォルダ/note.md'

# ルート一覧
Get-ObsidianVaultList

# ディレクトリ一覧
Get-ObsidianDirList -DirPath 'フォルダ/サブフォルダ/'

# 追記
Append-ObsidianNote -FilePath '...' -Content '追記内容'

# 完全上書き
Write-ObsidianNote -FilePath '...' -Content '新内容'

# 削除
Remove-ObsidianNote -FilePath '...'

# リネーム/移動（新規作成+旧パス削除の合成）
Move-ObsidianNote -FromPath '旧パス.md' -ToPath '新パス.md'

# 見出し/ブロック相対挿入（frontmatter更新や特定セクションへの差し込み）
Edit-ObsidianNoteSection -FilePath '...' -TargetType heading -Target '## 参考文献' -Operation append -Content '- 追加の参考文献'

# タグ・frontmatterなどJsonLogic条件での構造化検索
Search-ObsidianVaultAdvanced -Query @{ 'in' = @('検索語', @{'var'='tags'}) }

# 現在Obsidianで開いているノート
Get-ObsidianActiveNote

# 実行可能コマンド一覧 / コマンド実行（例: 検索インデックス再構築）
Get-ObsidianCommandList
Invoke-ObsidianCommand -CommandId 'app:reload'
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
- **孤立ノート検出・薄ノート検出など専用の修繕タスク** → [[vault-orphan-check]] / [[vault-thin-notes]] など専用スキルを使う（使い捨てスクリプトを量産しない）

## API疎通確認

```bash
pwsh -NoProfile -Command "Import-Module '<このスキルのtools>/obsidian-api.psm1'; Test-ObsidianApi | Format-List"
```

正常時：`Status: OK`、`Authenticated: True`

## 利用可能エンドポイント（Obsidian Local REST API v4.1.2）

| HTTP | パス | 内容 | ラッパー関数 |
|---|---|---|---|
| GET | `/` | 状態確認・認証 | `Test-ObsidianApi` |
| GET | `/vault/` | ルートディレクトリ一覧 | `Get-ObsidianVaultList` |
| GET | `/vault/<dir>/` | サブディレクトリ一覧 | `Get-ObsidianDirList` |
| GET | `/vault/<file>` | ファイル内容取得 | `Get-ObsidianNote` |
| PUT | `/vault/<file>` | ファイル作成/上書き | `Write-ObsidianNote` |
| POST | `/vault/<file>` | ファイル末尾追記 | `Append-ObsidianNote` |
| PATCH | `/vault/<file>` | 見出し・ブロック・frontmatterへの相対挿入 | `Edit-ObsidianNoteSection` |
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
| `Move-ObsidianNote` 実行後に一部ノートのリンクが切れる | wikilinkはbasename参照のためフォルダ移動・拡張子維持では切れないが、**basename自体を変更した場合**は他ノートの `[[旧basename]]` 参照が残る。[[vault-orphan-check]] で確認し手動修正するか、Grepで `\[\[旧basename` を検索して一括置換する |

## 関連

- [[vault-orphan-check]] — 孤立ノート検出
- [[vault-thin-notes]] — 薄ノート検出

## メモ

- wikilink は basename（拡張子・パスを除いたファイル名）でマッチする
- 検索が全クエリで500エラーになる場合、検索インデックスが改名/移動前の旧パスを参照している可能性がある。`/commands/app:reload/` をPOSTしてインデックスを再構築する
- Windows PowerShell 5.1はUTF-8ファイルをCP932として誤読することがあるため、pwsh (PowerShell 7) で実行する

## セキュリティ

- **API Key は `_secrets/obsidian.json` に保管** — `.gitignore` で除外済み
- 接続先は `127.0.0.1:27124` のみ（ローカル限定）
- HTTPS自己署名証明書を使うため、PowerShellは `-SkipCertificateCheck` を使用
- Obsidian起動時のみAPIが動作
