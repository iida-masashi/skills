---
name: vault-thin-notes
description: Obsidian Vault 配下の薄ノート（指定バイト数未満の.md）を検出する。専門ノート群で強化対象のノートを発見する用途。引数でフォルダ名・サイズ閾値を指定可能。
disable-model-invocation: false
---

# vault-thin-notes

Obsidian Vault 配下の **指定バイト数未満の薄ノート** を検出し、強化対象を抽出する。

## 用途

専門ノート群で、**内容が薄く強化候補となるノート** を体系的に発見する。

## 使い方

### 全Vault走査
```
/vault-thin-notes
```
デフォルト：3000バイト未満のノートをサイズ昇順で全Vault走査

### 特定フォルダ・閾値指定
```
/vault-thin-notes 対象フォルダ 5000
```
- 第1引数：検索対象フォルダ名（部分一致）
- 第2引数：サイズ閾値（バイト）

例：
- `/vault-thin-notes プロジェクトA` — プロジェクトA配下の3000B未満
- `/vault-thin-notes プロジェクトB 5000` — プロジェクトB配下の5000B未満

## 実行内容

1. Vault配下の指定フォルダ（または全体）の `.md` を収集
2. `.obsidian/`・`templates/`・`資料/`・`_work/` は除外
3. 指定バイト数未満のファイルを抽出
4. サイズ昇順で出力（最も薄いものから）

## 出力例

```
=== 対象フォルダ (閾値: 3000B) ===
   982B : folder\subfolder\note1.md
  1067B : folder\subfolder2\note2.md
  1198B : folder\subfolder3\note3.md
  ...

合計: 3 件
```

## スクリプト

実装：`<このスキルのtools>/vault-thin-notes.ps1`（Vaultのパスは環境に合わせて設定する）

```powershell
# 引数受け取り
param(
    [string]$folder = '',
    [int]$threshold = 3000,
    [string]$vaultRoot = $env:OBSIDIAN_VAULT_PATH
)

$root = $vaultRoot
if ($folder) {
    $searchPath = Get-ChildItem -LiteralPath $root -Recurse -Directory |
        Where-Object { $_.Name -like "*$folder*" } | Select-Object -First 1 -ExpandProperty FullName
    if (-not $searchPath) { $searchPath = $root }
} else {
    $searchPath = $root
}

$thin = Get-ChildItem -LiteralPath $searchPath -Recurse -File -Filter *.md -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Length -lt $threshold -and
        $_.FullName -notmatch '\\\.obsidian\\' -and
        $_.FullName -notmatch '\\templates\\' -and
        $_.FullName -notmatch '\\資料\\' -and
        $_.FullName -notmatch '\\_work\\'
    } |
    Sort-Object Length
```

## 後続アクション

検出された薄ノートは、既存の標準ノート構造（テンプレートがあれば参照）を参考に強化する。

## 関連

- [[vault-orphan-check]] — リンク健全性検出
