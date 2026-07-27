---
name: vault-sync
description: Sync an Obsidian Vault (awa-garden or religion-garden) to its Quartz repo's content/ WITHOUT committing or pushing. Use for local preview before publishing, or when you want to inspect what would change before invoking vault-publish. For full publish (sync+build+commit+push), use vault-publish instead.
---

# vault-sync: Vault → Quartz ローカル同期(push なし)

`vault-publish` から git commit/push を取り除いた preview 用のバリアント。
ローカルでの表示確認や、push 前の最終チェックに使う。**2つの対象（ターゲット）を扱える**: 阿波説デジタルガーデン(awa)と宗教研究デジタルガーデン(religion)。

## ターゲット定義

| ターゲット | Vault | Syncスクリプト | Quartzリポジトリ |
|---|---|---|---|
| **awa**（既定） | `D:\Vault` | `D:\Vault\_work\_sync_to_quartz.py` | `C:\Users\iidam\quartz` |
| **religion** | `D:\religion` | `D:\religion\_work\_sync_to_quartz_religion.py` | `C:\Users\iidam\quartz-religion` |

以降、選択したターゲットの行を `<vault>` `<sync-script>` `<quartz-repo>` として読み替える。ターゲットの決め方は`vault-publish`と共通（曖昧なら確認する。黙って awa を既定にしない）。

## When to use

ユーザーが以下のような表現をしたとき:
- 「ローカルで先に見たい」「同期だけして」
- 「push せずに反映」「プレビューだけ」
- 「/vault-sync」「/vault-sync religion」のように明示的に呼び出されたとき

**フル公開したいなら `vault-publish` を使う。**

## Pipeline

1. **Sync**: `<sync-script>` を実行(`vault-publish` と同じ)
2. **Build**: `npx quartz build` を実行して整合性を確認
3. **(任意) Serve**: ユーザーがプレビューを見たい場合のみ、`npx quartz build --serve` をバックグラウンドで起動して `http://localhost:8080` を案内

git/push 操作は一切行わない。

## Steps to execute

### 1. Run sync

awaターゲット:
```bash
cd "D:/Vault/_work" && uv run python _sync_to_quartz.py
```

religionターゲット:
```bash
cd "D:/religion/_work" && uv run python _sync_to_quartz_religion.py
```

失敗時(exit non-zero)は **halt して stderr を表示**。

### 2. Build verify

```bash
cd <quartz-repo> && npx quartz build
```

（awaなら `C:/Users/iidam/quartz`、religionなら `C:/Users/iidam/quartz-religion`）

YAML エラー等で失敗時は詳細表示して halt(ユーザーは Vault 側を直す必要がある)。

### 3. (Optional) Local preview server

ユーザーが `--serve` を渡した、または「プレビューしたい」と明示した場合:

```bash
cd <quartz-repo> && npx quartz build --serve
```

これはバックグラウンド実行し、`Started a Quartz server listening at http://localhost:8080` のログ行を検出してユーザーに案内する。

(parse に約 4 分かかるので、Bash `run_in_background` + `until grep "Started" ...; do sleep 5; done` 構成で待つ)

複数ターゲットのserverを同時に立てるとポート衝突する可能性があるため、既に片方が起動中なら停止するか別ポート案内を検討する。

### 4. Report

成功時、ユーザーに以下を伝える:
- どちらのターゲット（awa/religion）を同期したか
- 同期が完了したこと
- (build した場合) build 成功 / 出力ファイル数
- (serve した場合) http://localhost:8080 で確認できること
- **公開するなら `/vault-publish`（同じターゲットを指定して）を実行する**ことを案内

## Arguments

| Flag | Effect |
|---|---|
| `awa` / `religion` | 対象ターゲットを明示指定（位置引数、例: `/vault-sync religion`） |
| `--skip-build` | Step 2 をスキップ。同期だけ実行 |
| `--serve` | Step 3 を実行して preview server を立てる |
| `--dry-run` | sync スクリプトを `--dry-run` 付きで実行し、何も変更しない |

## What this skill does NOT do

- git commit / git push を一切しない(それは `vault-publish` の仕事)
- Vault 側のファイルを編集(同期は片方向)
- watch mode
- 2つのターゲットを跨いだ同期(1回の呼び出しにつき1ターゲット)

## Notes

- `vault-publish` との違い: **push しない**だけ。それ以外は同じ
- ファイル変更内容を確認したい場合は、このスキル実行後に `cd <quartz-repo> && git diff --stat` で確認可能
- 問題なければそのまま `cd <quartz-repo> && git add -A && git commit -m "..." && git push` か、より楽に `/vault-publish <target> --skip-build`(build は既に検証済みなのでスキップ可)
- ターゲットを取り違えると無関係なVaultの内容でbuildしてしまう。曖昧な指示の場合は必ず確認してから実行する。
