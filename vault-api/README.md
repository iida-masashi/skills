# vault-api Skill

Obsidian Local REST API（v4.1.2）経由でObsidian Vaultを直接操作する、MCPサーバーの代替実装。Bashから呼び出すPowerShellラッパー群と、直接importできるPowerShellモジュールを提供する。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | 構成・使い方・エンドポイント一覧・トラブルシュート |

> `tools/`配下のラッパー8本（Local REST API経由の6本＋ファイルシステム直接操作の孤立ノート/薄ノート検出2本）と共通モジュール`obsidian-api.psm1`はこのリポジトリに含まれる。APIキーを保管する`_secrets/obsidian.json`は`.gitignore`対象でリポジトリには含まれず、自分で作成する。`tools/maintenance/`（個人研究Vault専用の詳細版整備ツール群）は個人研究Vault専用の生データ・個人絶対パスを含むため、このリポジトリでは`.gitignore`で除外している。

## Quick Start

前提: Obsidian本体が起動中で、Local REST APIプラグインが有効になっていること。PowerShell 7（`pwsh`）が必要（Windows PowerShell 5.1はUTF-8をCP932と誤読するため不可）。

`obsidian-api.psm1`の設定ファイルパス（`$script:configPath`）は`Join-Path $PSScriptRoot '..\_secrets\obsidian.json'`、各`vault-*.ps1`の`Import-Module`行は`Join-Path $PSScriptRoot 'obsidian-api.psm1'`で、いずれもスクリプト自身の位置からの相対パス解決になっている。クローン先を変えてもパスの書き換えは不要。

1. `vault-api/_secrets/obsidian.json`を作成し、API Key・接続情報（`scheme`/`host`/`port`/`apiKey`）を設定する。
2. 疎通確認。

```bash
pwsh -NoProfile -Command "Import-Module '<このスキルのtools>/obsidian-api.psm1'; Test-ObsidianApi | Format-List"
```

正常時: `Status: OK`、`Authenticated: True`

## Commands

Bash経由で呼び出すラッパースクリプト（`tools/`配下）。

```bash
# 全文検索（コンテキスト付き）
pwsh -NoProfile -File <このスキルのtools>/vault-search.ps1 -Query "検索語" [-Limit 20] [-ContextLength 100]

# ファイル読み取り
pwsh -NoProfile -File <このスキルのtools>/vault-read.ps1 -Path "フォルダ/note.md" [-Lines N]

# ディレクトリ一覧（-Path省略でルート）
pwsh -NoProfile -File <このスキルのtools>/vault-list.ps1 [-Path "フォルダ/"]

# ファイル末尾追記（Content文字列指定 or ファイルから読み込み）
pwsh -NoProfile -File <このスキルのtools>/vault-append.ps1 -Path "フォルダ/note.md" -Content "追記内容"
pwsh -NoProfile -File <このスキルのtools>/vault-append.ps1 -Path "フォルダ/note.md" -ContentFile "追記内容ファイルパス"

# リネーム/移動（内部的には新パス書き込み→旧パス削除の合成）
pwsh -NoProfile -File <このスキルのtools>/vault-move.ps1 -From "旧フォルダ/note.md" -To "新フォルダ/note.md"

# 削除
pwsh -NoProfile -File <このスキルのtools>/vault-delete.ps1 -Path "フォルダ/note.md"

# 孤立ノート検出（どこからもwikilinkされていないノート）
pwsh -NoProfile -File <このスキルのtools>/vault-orphans.ps1 -VaultRoot "<Vaultパス>" [-SubPath "フォルダ"] [-OutCsv path]

# 薄ノート検出（指定バイト数未満のノート）
pwsh -NoProfile -File <このスキルのtools>/vault-thin-notes.ps1 -VaultRoot "<Vaultパス>" [-Folder "部分一致名"] [-Threshold 3000]
```

`obsidian-api.psm1` を直接importして使う場合の主な関数（ラッパースクリプトが内部で呼んでいるもの）。

```powershell
Import-Module '<このスキルのtools>/obsidian-api.psm1'

Test-ObsidianApi                                                     # 疎通テスト
Search-ObsidianVault -Query '検索語' -ContextLength 100 [-Limit N]    # 全文検索
Search-ObsidianVaultAdvanced -Query @{ 'in' = @('検索語', @{'var'='tags'}) }  # JsonLogic構造化検索
Get-ObsidianNote -FilePath 'フォルダ/note.md'                         # 読み取り
Get-ObsidianVaultList                                                 # ルート一覧
Get-ObsidianDirList -DirPath 'フォルダ/'                              # サブフォルダ一覧
Append-ObsidianNote -FilePath '...' -Content '追記内容'               # 末尾追記
Write-ObsidianNote -FilePath '...' -Content '新内容'                  # 完全上書き/新規作成
Remove-ObsidianNote -FilePath '...'                                   # 削除
Move-ObsidianNote -FromPath '旧パス.md' -ToPath '新パス.md'           # リネーム/移動（write+delete合成）
Edit-ObsidianNoteSection -FilePath '...' -TargetType heading -Target '## 参考文献' -Operation append -Content '追加内容'  # 見出し/ブロック/frontmatterへの相対挿入
Get-ObsidianActiveNote                                                # Obsidianで現在開いているノート
Get-ObsidianCommandList                                               # 実行可能コマンド一覧
Invoke-ObsidianCommand -CommandId 'app:reload'                        # コマンド実行（検索インデックス再構築など）
```

## Highlights

- **MCPサーバーを登録できない/使いたくない環境向けの代替** — Local REST APIを直接叩くPowerShellラッパーとして実装。
- **`Move`はAPIの合成操作** — Local REST APIに専用のrename/moveエンドポイントは無いため、`Move-ObsidianNote`は「新パスへ書き込み→旧パス削除」を内部で行う。
- **ルート一覧とサブフォルダ一覧は別関数** — `Get-ObsidianDirList -DirPath ''`（空文字）はエラーになるため、ルートには`Get-ObsidianVaultList`を使う必要がある。
- **wikilinkはbasename参照** — フォルダ移動や拡張子維持のリネームではリンクは切れないが、basename自体を変更すると他ノートの`[[旧basename]]`参照は手動修正が必要（`vault-move.ps1`は実行後にその旨を注意メッセージとして表示する）。
- **検索全滅は旧パス参照が原因** — 全文検索が全クエリで500エラーになる場合、検索インデックスが改名/移動前の旧パスを参照している。`Invoke-ObsidianApi`は`ENOENT ... open '<旧パス>'`を検知すると原因と対処法（`Invoke-ObsidianCommand -CommandId 'app:reload'`）を含めたエラーメッセージを自動生成する。
- **UTF-8対策はラッパーによって差がある** — `vault-search.ps1`/`vault-read.ps1`/`vault-list.ps1`/`vault-move.ps1`/`vault-delete.ps1`は先頭で`[Console]::OutputEncoding`をUTF-8に設定しているが、`vault-append.ps1`にはこの設定がない。`obsidian-api.psm1`を直接importして自作スクリプトを書く場合も、スクリプト側で同様の設定が必要。
- **接続はローカル限定** — 接続先は`127.0.0.1:27124`のみ。HTTPS自己署名証明書のため`-SkipCertificateCheck`を使用。Obsidian起動時のみAPIが動作する。

## 実行例（出力フォーマット）

`_secrets/obsidian.json`未設定のため実行結果は未検証。以下は各スクリプトの`Write-Output`呼び出しから確認できる出力フォーマット（プレースホルダ値）。

`vault-search.ps1`:
```
検索: '検索語'
ヒット数: N

── ファイル名.md
    （コンテキスト文字列、200文字超は...で切り詰め）

... 残り N 件は省略
```

`vault-read.ps1`（`-Lines`指定時）:
```
（先頭N行の内容）

--- N / M 行表示 ---
```

`vault-move.ps1`:
```
移動完了: 旧パス.md -> 新パス.md (N 文字)
注意: wikilinkはbasename参照のため、拡張子のみ変更やフォルダ移動ではリンクは切れない。basename自体を変えた場合は他ノートの参照を手動で確認すること。
```

## 既存ツールとの比較

SKILL.mdより。

| ツール | 強み | 弱み |
|---|---|---|
| **vault-api（本スキル）** | Obsidian経由でwikilink解決・タグ検索が正確、Obsidian再起動不要 | Obsidianアプリ起動必須 |
| **Read/Grep/Glob（標準）** | Obsidian起動不要、高速 | Obsidian独自機能（タグ・dataview等）不可 |

使い分けの推奨（SKILL.mdより）: 全文検索でコンテキスト付き結果が欲しい→`vault-search`／大量のファイル走査が必要→Grep/Glob／frontmatter編集・追記→Edit/Write／wikilink構造を理解した検索→`vault-search`／孤立ノート検出→本スキルの`tools/vault-orphans.ps1`／薄ノート検出→本スキルの`tools/vault-thin-notes.ps1`。

## セキュリティ

- API KeyはローカルのAPI設定ファイル（`_secrets/obsidian.json`）に保管する。
- 接続先は`127.0.0.1:27124`のみ（ローカル限定）。
- HTTPS自己署名証明書を使うため、PowerShellは`-SkipCertificateCheck`を使用。
- Obsidian起動時のみAPIが動作する。
