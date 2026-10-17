---
name: context-compression-skill
description: Use before builds, test suites, installs, long logs, files over ~300 lines/20KB, notebooks, SQL/DataFrame/MCP output or wide searches, to filter output before it enters context without losing exit codes or failure evidence. 大量出力の圧縮。
---

# Context Compression Skill

ツール出力をコンテキストに入れる**前**に絞る詳細リファレンス（常時適用の要約は `~/.claude/CLAUDE.md` / `~/.gemini/GEMINI.md`）。
**大原則**: 圧縮は成功パスの最適化。終了コード・失敗の証拠・判断に必要な文脈は削らない（§7）。単一ツール出力は原則 **100行以内**。

| 汎用概念 | Gemini CLI / Antigravity | Claude Code |
|---|---|---|
| 検索 / 一覧 | `grep_search` / `glob` / `find_by_name` | `Grep`（`output_mode`, `-C`, `head_limit`） / `Glob` |
| 部分読み込み | `read_file` / `view_file`（`StartLine`/`EndLine`） | `Read`（`offset` / `limit`） |
| 末尾抽出 | `Select-Object -Last 30`（PowerShell） | ログ経由 `tail -30`（Bash、§2の正規形） |

> **Bash の落とし穴**: `cmd | tail -30` は tail の終了コードを返し失敗が exit 0 に見える。必ず §2 の正規形を使う（PowerShell は `$LASTEXITCODE` が保持される）。

## 1. コマンドの静音化とロックファイル

*   **Install / 一覧**: `npm install --quiet --no-progress`, `uv pip install -q`。`pip list` / `npm ls` 全件は避けパッケージ名で絞る。
*   **ロックファイル（`uv.lock` / `package-lock.json` / `poetry.lock` / `yarn.lock` 等）**: 丸ごと Read / `cat` 禁止。`uv tree --depth 1` / `uv pip list --outdated` / `npm ls <pkg>`、特定パッケージは `grep -A3 '^name = "pkg"' uv.lock` で絞る。
*   **Git**: `git status -s`, `git log --oneline -n 5`（引数なし `git log` 禁止）。
*   **テスト・リンター**: `pytest -q --tb=short --maxfail=3`（大量失敗時の爆発防止。失敗一覧は `-rf`）。リンター（`ruff`, `eslint`, `tsc`）は `--statistics` や `--quiet` を先行。

## 2. ログの蒸留（終了コードを保つ正規形）

ビルド・テスト・docker build 等の長いコマンドは一時ファイルへリダイレクトし、終了コードと末尾・エラー周辺だけ取る。
```bash
# Bash（1コマンド内で完結） / パイプ時は set -o pipefail 必須
LOG=<scratchpad>/build.log; npm run build > "$LOG" 2>&1; ec=$?; tail -30 "$LOG"; echo "exit=$ec"
set -o pipefail; pytest -q --maxfail=3 2>&1 | tail -30; echo "exit=$?"
```
```powershell
# PowerShell
npm run build *> $LOG; "exit=$LASTEXITCODE"; Get-Content $LOG -Tail 30
```
*   失敗時は検索ツールで `Error` / `Exception` / `FAILED` 周辺を context 付きで抽出。root cause は**最初の**エラーにあるが多いため必要に応じログ先頭側も検索する。

## 3. 段階的開示（大きいファイル・特殊ファイル）

*   **300行以下 かつ 20KB以下（1行最大500文字目安）**: 一発で全体を読む（細切れ往復の方が高コスト）。
*   **300行超 または 20KB超**: ①行数・サイズ把握 → ②検索ツールで `def ` / `class ` / `function ` / 見出し等のシグネチャ抽出 → ③対象を**関数・クラス単位で丸ごと**部分読み込み（数行の断片で止めない）。
*   **直接 Read 禁止**:
    *   **Minified / Map（`*.min.js`, `*.min.css`, `*.map`, 巨大 `*.svg`）**: 1行が数万文字になるため Read しない。
    *   **Notebook（`.ipynb`）**: Base64画像等の出力セルを避けコードセルのみ抽出（`jq '.cells[] | select(.cell_type=="code") | .source' nb.ipynb`）。
*   **再読防止**: 同じファイルを再読しない。3ファイル超の調査メモ（パス・行番号・関数名）は `<scratchpad>/notes.md` に退避して参照する。

## 4. 差分・ディレクトリ・検索の絞り込み

*   **Git 差分**: `git diff --stat` / `--name-only` で全体像を掴んでからファイル単位で見る。`-U0` は俯瞰専用。
*   **一覧・走査**: `ls -R` や除外なしの `Get-ChildItem -Recurse` は禁止。専用ツールまたは `.gitignore` を尊重する `rg --files` / `git ls-files` を使う。PowerShell 走査時は `-Depth` 指定、または `.venv`, `node_modules`, `.git`, `__pycache__`, `dist`, `.next` の除外が必須。
*   **検索**: 件数不明なら `output_mode: count` / `files_with_matches` で規模を見てから本文を出す（Claude Code `Grep` は必要に応じ `head_limit` を絞る）。

## 5. 構造化出力・DataFrame・MCP/API

*   **CLI / SQL**: 罫線表や `SELECT *` を避け、必要列＋`LIMIT` を高密度形式（インデントなし JSON / CSV）で取る（`gh pr list --json number,title -q '.[]'`, `jq -c`）。行ダンプ前に `COUNT(*)` 等の集計を検討。
*   **DataFrame**: `print(df)` 禁止。Polars は `df.schema`, `df.head(3)`, `df.tail(3)`（pandas は `dtypes`, `info()`, `head(3)`）。多列・ネスト列は先に `select` で絞ってから `glimpse()`。
*   **MCP / 外部 API**: 初回取得は必ず `limit` / `per_page` を最小限（5〜10件）に絞る。

## 6. サブエージェント委譲＋検証・Web 調査

*   **広域探索**: 1サブエージェント1タスクで出力形式・長さを指定して委譲し結論だけ受け取る（指示・返答は英語可、固有名詞・パス・引用・書き込み文面は原文維持、ユーザー報告は日本語）。
*   **未検証扱い**: サブエージェントが返したパス・行番号・ID・関数名は Edit 前に必ず実在確認する。レビュー・監査の**判定**は委譲せず自分で対象を通読する。
*   **Web 調査**: 固有名詞・年・単位を含め一発で検索し、一次資料1〜2件のみ `prompt` で必要事実だけ射影して Fetch する（出典 URL と確度タグ `[一次]`/`[要検証]` は残す）。複数ページ調査は委譲（Claude Code では `web-search` スキルの `gemini_parallel.py` を使う）。

## 7. 圧縮しない場面と安全弁

*   **圧縮しない場面（丸ごと読む）**: ①コードレビュー・監査・バグ原因特定（対象の関数・クラス・ファイルを通読）、②Edit の置換文字列作成（前後を実際に読む）、③事実・仕様の検証（根拠箇所を文脈込みで読む）。
*   **安全弁**: 終了コードと失敗シグナルは落とさない（§2）。失敗時は次の1回はフィルタを緩めて再観測してよいが、同一エラーの無思考リトライでログを重複蓄積しない（2回連続失敗したら実行を止めて原因分析に切り替える）。
