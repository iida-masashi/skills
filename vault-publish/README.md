# vault-publish

Obsidian Vault（阿波説デジタルガーデン awa-garden / 宗教研究デジタルガーデン religion-garden）を Quartz サイトの `content/` に同期し、ローカル build で検証した上で commit・push して GitHub Pages に公開する、sync→build→commit→push を一括実行するスキル。

| Document | Purpose |
|---|---|
| [SKILL.md](SKILL.md) | 対象定義・パイプライン手順・引数・トラブルシューティング |

## 使い方

以下のような表現で呼び出される:
- 「Vaultを公開して」「デジタルガーデンを更新」「Quartzをデプロイ」
- 「awa-garden に push」「religion-garden に push」「変更を反映したい」
- `/vault-publish` / `/vault-publish religion` のように明示的に呼び出す

対象Vaultが曖昧なとき（単に「公開して」など）は、黙って awa を既定にせず必ずユーザーに確認する。誤ったリポジトリへの push は取り消しにくいため。

「同期だけして」「ローカルで先に見たい」「push せずに反映」等、pushを伴わない用途は `--sync-only` を使う（後述）。

主な引数:

| Flag | 効果 |
|---|---|
| `awa` / `religion` | 対象ターゲットを明示指定（位置引数） |
| `--skip-build` | build検証をスキップして push を優先 |
| `--sync-only` | commit/pushを行わずsync+buildまでで停止（push前のローカル確認・プレビュー用） |
| `--serve` | `--sync-only` と併用。build後にプレビューサーバーを起動 |
| `--message "..."` | commit message を上書き |
| `--dry-run` | sync スクリプトを `--dry-run` で実行し、commit/push は行わない |

## 処理フロー

1. **Sync** — 対象Vault専用の同期スクリプトを実行し、Vault のサブツリーを Quartz リポジトリの `content/` にミラーする。frontmatter の YAML 不正修正・dewikify（壊れた wikilink の外部URL/プレーンテキスト化）も適用される。
2. **Build verify**（既定でON、`--skip-build` で省略可） — `npx quartz build` を実行。YAML エラー等が出た場合は halt してエラー詳細を表示する（Vault側の修正が必要）。
3. `--sync-only` の場合はここで停止（任意で `--serve` によるローカルプレビュー）。
4. **Commit** — sync 結果のサマリから自動でコミットメッセージを生成（`--message` で上書き可）。変更がなければ push せずに終了。
5. **Push** — `git push`。ネットワークエラー（`Connection was reset` 等）の場合は `http.postBuffer` を設定して1回だけ retry する。

成功時は公開URLとGitHub Actionsの実行状況確認コマンドを案内する（デプロイはGitHub Actions経由で自動、所要1〜2分）。

## 対象Vault(awa-garden/religion-garden)の設定特定手順

このスキルは2つの対象専用に、Vaultパス・同期スクリプト・Quartzリポジトリ・GitHub repo・公開URLがSKILL.md内にあらかじめ表で定義されている。

| ターゲット | Vault | Syncスクリプト | Quartzリポジトリ | GitHub repo | 公開URL |
|---|---|---|---|---|---|
| **awa**（既定） | `D:\Vault\awa` | `D:\Vault\awa\_work\_sync_to_quartz.py` | `<quartz-repo>` | `iida-masashi/awa-garden` | `https://iida-masashi.github.io/awa-garden/` |
| **religion** | `D:\Vault\religion` | `D:\Vault\religion\_work\_sync_to_quartz_religion.py` | `<quartz-religion-repo>` | `iida-masashi/religion-garden` | `https://iida-masashi.github.io/religion-garden/` |

ターゲットの決め方:
1. ユーザーが `religion`／`宗教`／`religion-garden` 等を明示、または直前の会話が `D:\Vault\religion` 配下のVault操作なら religion。
2. ユーザーが `阿波`／`awa`／`awa-garden` 等を明示、または直前の会話が `D:\Vault\awa` 配下のVault操作なら awa。
3. どちらとも判断できない場合は、黙って推測せずユーザーへ確認する。

## Highlights

- **対象固定・設定探索なし** — Vaultパス・スクリプト・リポジトリを毎回探索/確認する必要がない。awa/religionの2ターゲットのみをSKILL.md内の表で直接解決する。
- **ターゲット取り違え防止を最優先** — 曖昧な指示では既定値に倒さず必ず確認する運用をSKILL.md内で複数回明記。誤ったリポジトリへのpushは取り消しにくいため。
- **build失敗はVault側の責任として halt** — YAMLエラー等が出たら自動修復せず、ユーザーがVaultを直すよう詳細を表示して停止する。
- **Mermaid `%%` の罠を既知のトラブルシューティングとして記録** — Quartzの OFM transformer が `%%…%%` をObsidianブロックコメントとして間を全削除するため、mermaidフェンス内の `%%` は全廃が必要（build成功はクライアント側描画の保証にならない）。sync時に `_check_mermaid_comments.py` で warn-only 検出するが、これは awa のみ対応（religion側の対応は未確認、とSKILL.mdに明記）。
- **ネットワークエラーは1回だけ自動retry** — `http.postBuffer` 拡張後に再push、それでも失敗したらhaltしてユーザーに委ねる。
- **2ターゲットを跨いだ同時操作は行わない** — 1回の呼び出しにつき1ターゲットのみ。

## vault-sync との統合について

以前は commit/push を行わないプレビュー専用スキル `vault-sync` を別スキルとして分けていたが、単独で使うユースケースがほとんどなかったため本スキルの `--sync-only` フラグに統合した（2026-08-06）。push前にローカル確認したいだけの場合は `/vault-publish <target> --sync-only`（プレビューサーバーも見たければ `--serve` を追加）を使う。sync/buildが既に成功済みの状態から公開する場合は `--sync-only` を外し `--skip-sync --skip-build` を付けて再実行すれば二度手間にならない。
