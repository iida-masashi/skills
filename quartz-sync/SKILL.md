---
name: quartz-sync
description: Sync an Obsidian Vault to a Quartz site's content/ folder and verify a local build, WITHOUT committing or pushing. Use for local preview before publishing, or to inspect what would change before invoking quartz-publish. For full publish (sync+build+commit+push), use quartz-publish instead.
---

# quartz-sync: Vault → Quartz ローカル同期(push なし)

`quartz-publish` から git commit/push を取り除いた preview 用のバリアント。
ローカルでの表示確認や、push 前の最終チェックに使う。

**このスキルはVault→Quartz同期の一般的なパイプラインの型を示すテンプレートである。実際の同期スクリプト・Vaultパス・Quartzリポジトリパスはプロジェクトごとに異なるため、実行前に必ず特定すること（下記「0. 設定の特定」参照）。**

## When to use

ユーザーが以下のような表現をしたとき:
- 「ローカルで先に見たい」「同期だけして」
- 「push せずに反映」「プレビューだけ」
- 「/quartz-sync」のように明示的に呼び出されたとき

**フル公開したいなら `quartz-publish` を使う。**

## 0. 設定の特定(初回・不明時は必須)

このスキルは以下3つの情報がないと実行できない。会話の過去の文脈やメモリで既に判明していればそれを使い、不明ならユーザーに確認する。

| 項目 | 特定方法 |
|---|---|
| **Vaultパス** | ユーザーの発言・過去の会話・メモリから推定。不明なら質問する |
| **同期スクリプトの場所** | 慣例上 `<vault>/_work/` 配下や `<vault>/scripts/` 配下に置かれることが多い。`sync`, `quartz`, `publish` 等の名前でGlob検索して探す |
| **Quartzリポジトリのパス** | 同期スクリプト内にハードコードされている場合が多い(例: 変数 `CONTENT = Path(...)`)。スクリプトを一度読んで確認する。スクリプトが引数化されている場合はそちらを優先する |

同期スクリプトが見つからない・存在しない場合は、このスキルを適用せずユーザーに相談する(スキルは既存の同期スクリプトの実行を前提としており、ゼロから同期の仕組みを作る用途ではない)。

## Pipeline

1. **Sync**: 同期スクリプトを実行(`quartz-publish` と同じ)
2. **Build**: `npx quartz build` を実行して整合性を確認
3. **(任意) Serve**: ユーザーがプレビューを見たい場合のみ、`npx quartz build --serve` をバックグラウンドで起動してURLを案内

git/push 操作は一切行わない。

## Steps to execute

### 1. Run sync

```bash
cd <vault>/<sync-script-dir> && uv run python <sync_script_name>.py [--dry-run]
```

（`uv`環境でない場合は素の`python`。スクリプトの実行方法は事前にREADME等で確認する。）

失敗時(exit non-zero)は **halt して stderr を表示**。

### 2. Build verify

```bash
cd <quartz-repo> && npx quartz build
```

YAML エラー等で失敗時は詳細表示して halt(ユーザーは Vault 側を直す必要がある)。

### 3. (Optional) Local preview server

ユーザーが `--serve` を渡した、または「プレビューしたい」と明示した場合:

```bash
cd <quartz-repo> && npx quartz build --serve
```

これはバックグラウンド実行し、`Started a Quartz server listening at http://localhost:8080` のようなログ行を検出してユーザーに案内する（ポート番号は出力を確認する）。

(parse に数分かかることがあるので、Bash `run_in_background` + `until grep "Started" ...; do sleep 5; done` 構成で待つ)

### 4. Report

成功時、ユーザーに以下を伝える:
- 同期が完了したこと
- (build した場合) build 成功 / 出力ファイル数
- (serve した場合) 案内されたURLで確認できること
- **公開するなら `/quartz-publish` を実行する**ことを案内

## Arguments

| Flag | Effect |
|---|---|
| `--skip-build` | Step 2 をスキップ。同期だけ実行 |
| `--serve` | Step 3 を実行して preview server を立てる |
| `--dry-run` | 同期スクリプトの `--dry-run` 相当を実行し、何も変更しない(スクリプトが対応している場合のみ) |

## What this skill does NOT do

- git commit / git push を一切しない(それは `quartz-publish` の仕事)
- Vault 側のファイルを編集(同期は片方向)
- watch mode
- 同期スクリプト自体の作成・改修(既存スクリプトの実行のみを担う)

## Notes

- `quartz-publish` との違い: **push しない**だけ。それ以外は同じ
- ファイル変更内容を確認したい場合は、このスキル実行後に `cd <quartz-repo> && git diff --stat` で確認可能
- 問題なければそのまま `cd <quartz-repo> && git add -A && git commit -m "..." && git push` か、より楽に `/quartz-publish --skip-build`(build は既に検証済みなのでスキップ可)
- 同期スクリプトが `content/` を「Vaultからの一方向ミラー」として扱っている場合、`content/` 側の直接編集は次回同期で上書きされる。この前提を壊す変更（同期対象外ファイルの追加等）を検討する際はユーザーに確認する
