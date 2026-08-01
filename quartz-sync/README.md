# quartz-sync

Obsidian Vault を Quartz サイトの `content/` フォルダへ同期し、ローカルビルドで整合性を確認する（**git commit / push は行わない**）汎用スキル。

## これは何か

`quartz-publish`（sync → build 検証 → commit → push のフル公開パイプライン）から git commit/push を取り除いた、preview 専用のバリアント。ローカルでの表示確認や、push 前の最終チェックに使う。

**特定のVault・リポジトリに紐付かない汎用テンプレート**である。実際の同期スクリプトの場所、Vaultパス、Quartzリポジトリのパスはプロジェクトごとに異なるため、実行前に必ず特定する（設定の特定方法はSKILL.md「0. 設定の特定」に記載）。

## 使う場面（トリガー表現）

以下のような発言があったとき:
- 「ローカルで先に見たい」「同期だけして」
- 「push せずに反映」「プレビューだけ」
- 「/quartz-sync」のように明示的に呼び出されたとき

フル公開したい場合はこのスキルではなく `quartz-publish` を使う。

## 処理フロー（Pipeline）

1. **Sync** — 同期スクリプトを実行（`quartz-publish` と同じ処理）
2. **Build** — `npx quartz build` を実行して整合性を確認
3. **(任意) Serve** — ユーザーがプレビューを見たい場合のみ `npx quartz build --serve` をバックグラウンドで起動し、案内されたURL（例: `http://localhost:8080`）を伝える

git/push 操作は一切行わない。

## 主なオプション

| Flag | 効果 |
|---|---|
| `--skip-build` | Build ステップをスキップし、同期だけ実行 |
| `--serve` | ローカルプレビューサーバーを起動 |
| `--dry-run` | 同期スクリプトの `--dry-run` 相当を実行し、何も変更しない（スクリプトが対応している場合のみ） |

## このスキルがやらないこと

- git commit / git push（それは `quartz-publish` の仕事）
- Vault 側ファイルの編集（同期は Vault → content の一方向）
- watch mode
- 同期スクリプト自体の作成・改修（既存スクリプトの実行のみを担う）

## quartz-publish との違い

**push しない**だけで、それ以外の処理（sync・build検証）は同じ。build まで確認済みであれば、そのまま `/quartz-publish --skip-build` で公開に進める。

## 汎用版（quartz-sync）と専用版（vault-sync）の違い

このリポジトリには、特定のVaultに紐付いた専用版スキル `vault-sync` も別に存在する。用途は同じ（sync + build 検証、push なし）だが、対象が固定されている点が異なる。

| | **quartz-sync**（汎用版） | **vault-sync**（専用版） |
|---|---|---|
| 対象Vault | 未固定。実行時に特定が必要 | `awa`（`D:\Vault\awa`）または `religion`（`D:\Vault\religion`）の2択で固定 |
| 同期スクリプトパス | 未固定。`<vault>/_work/` 等を探索して特定 | `_sync_to_quartz.py` / `_sync_to_quartz_religion.py` にハードコード |
| Quartzリポジトリパス | 未固定。スクリプト内の記述等から特定 | `C:\Users\iidam\quartz` / `C:\Users\iidam\quartz-religion` にハードコード |
| 事前ステップ | 「0. 設定の特定」が必須（Vault/スクリプト/リポジトリパスを毎回もしくは初回に確認） | 不要（ターゲット名 `awa`/`religion` の選択のみ） |
| 対応する公開スキル | `quartz-publish` | `vault-publish` |

どのVaultでも使える指示書が欲しい場合は `quartz-sync`、awa-garden/religion-gardenの2つの固定ターゲットに対して使う場合は `vault-sync` を使う。
