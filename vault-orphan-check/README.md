# vault-orphan-check

Obsidian Vault 配下の**孤立ノート**（どこからも `[[wikilink]]` されていない `.md`）を検出する。資料系・テンプレ・`.obsidian` 配下は除外し、サイズ降順で出力する。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | 実行内容・使い方・救済ガイダンスの定義 |

## Quick Start

```
/vault-orphan-check
```

Claude は `<このスキルのtools>/vault-orphan-check.ps1` を実行し、出力ファイルの結果を Read して報告する。実行前に Vault のパスを環境に合わせて指定する。

## 処理内容

1. Vault配下の全 `.md` を再帰収集（`.obsidian/`・`templates/`・`資料/`・`MEMORY.md` を除外）
2. 全 `.md` ファイル本文から `[[X]]` `[[X|alias]]` `[[path/X]]` を抽出し、basename部分（拡張子なし）を取得
3. 自身の basename が他のどこからも参照されていないノートを孤立ノートとして抽出
4. サイズ降順で結果を出力

## 出力例

```
総ノート数（資料系除外）: 1000
全wikilink basename種類数: 4500
孤立ノート数: 3

=== 孤立ノート一覧 ===
   7500B : note1.md
   3600B : folder/note2.md
   ...
```

## Highlights

- **basenameマッチ** — wikilinkはパス・拡張子を除いたファイル名（basename）でマッチする。`[[path/X]]` と `[[X]]` は同一ノートとして扱われる。
- **除外対象** — `.obsidian/`・`templates/`・`資料/`・`MEMORY.md` は孤立判定の対象から除く。
- **救済ガイダンス** — 孤立ノートが見つかった場合の手順を定義：
  1. 孤立ノートの内容を Read で確認
  2. 関連する既存ハブノート（`_目次.md` `ポータル.md` `MOC` 等）を Grep で検索
  3. 適切なハブノート内で `[[孤立ノート名]]` wikilink を追加
  4. または孤立ノート側に「関連ノート」セクションを追加し、相互リンクを構築
- **救済対象から除外すべきノート** — Vault管理用の独立ドキュメント（CSS設計書等、意図的に孤立させているもの）／作業用フォルダ配下のスクリプト・作業メモ／バックアップファイル。
