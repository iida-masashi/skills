---
name: awa-sync
description: Sync the Obsidian Vault at <vault> to <quartz-repo>/content/ for the 阿波説デジタルガーデン WITHOUT committing or pushing. Use for local preview before publishing, or when you want to inspect what would change before invoking awa-publish. For full publish (sync+build+commit+push), use awa-publish instead.
---

# awa-sync: Vault → Quartz ローカル同期(push なし)

`awa-publish` から git commit/push を取り除いた preview 用のバリアント。
ローカルでの表示確認や、push 前の最終チェックに使う。

## When to use

ユーザーが以下のような表現をしたとき:
- 「ローカルで先に見たい」「同期だけして」
- 「push せずに反映」「プレビューだけ」
- 「/awa-sync」のように明示的に呼び出されたとき

**フル公開したいなら `awa-publish` を使う。**

## Pipeline

1. **Sync**: `<vault>/_work/_sync_to_quartz.py` を実行(`awa-publish` と同じ)
2. **Build**: `npx quartz build` を実行して整合性を確認
3. **(任意) Serve**: ユーザーがプレビューを見たい場合のみ、`npx quartz build --serve` をバックグラウンドで起動して `http://localhost:8080` を案内

git/push 操作は一切行わない。

## Steps to execute

### 1. Run sync

```bash
cd <vault>/_work && uv run python _sync_to_quartz.py
```

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

これはバックグラウンド実行し、`Started a Quartz server listening at http://localhost:8080` のログ行を検出してユーザーに案内する。

(parse に約 4 分かかるので、Bash `run_in_background` + `until grep "Started" ...; do sleep 5; done` 構成で待つ)

### 4. Report

成功時、ユーザーに以下を伝える:
- 同期が完了したこと
- (build した場合) build 成功 / 出力ファイル数
- (serve した場合) http://localhost:8080 で確認できること
- **公開するなら `/awa-publish` を実行する**ことを案内

## Arguments

| Flag | Effect |
|---|---|
| `--skip-build` | Step 2 をスキップ。同期だけ実行 |
| `--serve` | Step 3 を実行して preview server を立てる |
| `--dry-run` | `_sync_to_quartz.py --dry-run` を実行し、何も変更しない |

## What this skill does NOT do

- git commit / git push を一切しない(それは `awa-publish` の仕事)
- Vault 側のファイルを編集(同期は片方向)
- watch mode

## Notes

- `awa-publish` との違い: **push しない**だけ。それ以外は同じ
- ファイル変更内容を確認したい場合は、このスキル実行後に `cd <quartz-repo> && git diff --stat` で確認可能
- 問題なければそのまま `cd <quartz-repo> && git add -A && git commit -m "..." && git push` か、より楽に `/awa-publish --skip-build`(build は既に検証済みなのでスキップ可)
