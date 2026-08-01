# vault-thin-notes Skill

Obsidian Vault 配下の **指定バイト数未満の薄ノート（`.md`）** を検出し、専門ノート群における強化対象を発見するスキル。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | 検出ロジックと使い方の定義 |

## Quick Start

Vault のルートパスを環境変数 `OBSIDIAN_VAULT_PATH` に設定する（スクリプトはこの変数からルートを取得する）。

```powershell
$env:OBSIDIAN_VAULT_PATH = "<Vaultのルートパス>"
```

## 使い方

Claude Code / Gemini CLI 上でスラッシュコマンドとして呼び出す。

```
/vault-thin-notes
```
デフォルト：3000バイト未満のノートをサイズ昇順で全Vault走査。

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

## 出力例（SKILL.md 記載）

```
=== 対象フォルダ (閾値: 3000B) ===
   982B : folder\subfolder\note1.md
  1067B : folder\subfolder2\note2.md
  1198B : folder\subfolder3\note3.md
  ...

合計: 3 件
```

## Highlights

- **フォルダ指定は部分一致・最初の1件のみ** — `$folder` はディレクトリ名への部分一致で検索し、`Select-Object -First 1` により最初にマッチした1件のみを対象にする。
- **未マッチ時はVault全体にフォールバック** — 指定フォルダ名に一致するディレクトリが見つからない場合、`$searchPath` はVaultルート全体にフォールバックする（タイプミスで全走査になる点に注意）。
- **固定除外パス** — `.obsidian\`・`templates\`・`資料\`・`_work\` を含むパスは常に除外される（コード内に固定、引数での変更不可）。
- **後続アクション** — 検出された薄ノートは、既存の標準ノート構造（テンプレートがあれば参照）を参考に強化する運用を想定。
- スクリプト本体は `SKILL.md` 内に PowerShell スニペットとして記載されている（`.ps1` ファイルは本フォルダに同梱していない）。

## 関連

- [vault-orphan-check](../vault-orphan-check/) — リンク健全性検出（孤立ノート検出）
