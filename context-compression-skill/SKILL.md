---
name: context-compression-skill
description: Use when a tool call is likely to produce large output — builds, test suites, package installs, long logs, files over ~300 lines, DataFrames/SQL results, wide repo searches, or multi-page web research — to filter it before it enters the context window without losing exit codes or failure evidence. 大量出力（ビルド・テスト・ログ・巨大ファイル・表データ・広域検索・Web調査）をコンテキストに入れる前に圧縮したいとき。
---

# Context Compression Skill

ツール出力をコンテキストに入れる**前**に絞り、トークン消費とノイズを減らすための詳細リファレンス（rtk-ai/rtk の発想を踏襲）。
常時守る中核ルールはグローバル指示（`~/.claude/CLAUDE.md` / `~/.gemini/GEMINI.md` の「コンテキスト圧縮」節）に置いてあり、本書はその詳細版。

**大原則**: 圧縮は成功パスの最適化。終了コード・失敗の証拠・判断に必要な文脈は削らない（末尾「圧縮しない場面」「安全弁」参照）。

## ツール語彙の対応表

本文は汎用語彙で書く。実ツール名は環境ごとに読み替える。

| 汎用概念 | Gemini CLI | Claude Code |
|---|---|---|
| 検索ツール | `grep_search` | `Grep`（`output_mode`, `-C`, `head_limit`） |
| 部分読み込み | `read_file` の `start_line` / `end_line` | `Read` の `offset` / `limit` |
| ファイル一覧 | `glob` / `list_directory` | `Glob` |
| 末尾抽出 | `Select-Object -Last 30`（PowerShell） | ログファイル経由の `tail -30`（Bash、§2の正規形） |

> **Bash の落とし穴**: `cmd | tail -30` は tail の終了コードを返すため、失敗しても exit 0 に見える。Bash では必ず §2 の正規形を使う。PowerShell は `| Select-Object -Last 30` 後も `$LASTEXITCODE` が保持される。

## 1. コマンドの静音化

プログレスバーや冗長ログはフラグで出さない。
*   パッケージ管理: `npm install --quiet --no-progress`, `uv pip install -q`
*   Git: `git status -s`, `git log --oneline -n 5`
*   テスト: `pytest -q --tb=short`（失敗一覧が欲しければ `-rf`）

## 2. ログの蒸留（終了コードを保つ正規形）

長くなりうるコマンドは一時ファイルへリダイレクトし、終了コードを必ず表示してから必要部分だけ取り出す。

```bash
# Bash（シェル状態は呼び出し間で持ち越されないので1コマンド内で完結させる）
LOG=<scratchpad>/build.log; npm run build > "$LOG" 2>&1; ec=$?; tail -30 "$LOG"; echo "exit=$ec"
# パイプを使うなら pipefail を同じ行で
set -o pipefail; pytest -q 2>&1 | tail -30; echo "exit=$?"
```
```powershell
# PowerShell
npm run build *> $LOG; "exit=$LASTEXITCODE"; Get-Content $LOG -Tail 30
```
*   失敗時は検索ツールでログ内の `Error` / `Exception` / `FAILED` 周辺だけを context 付きで抽出する。
*   root cause は**最初の**エラーにあることが多い。末尾窓の外に落ちている疑いがあればログ先頭側も検索する。

## 3. 段階的開示（大きいファイルの読み方）

*   **300行以下のファイルは一発で全体を読む**。段階的に3往復する方が合計トークンが高い。
*   300行超のファイルのみ次の段階を踏む:
    1. ファイル名・行数を把握
    2. 検索ツールで `def ` / `class ` / `function ` / 見出し等のシグネチャだけ抽出して骨組みを掴む
    3. 骨組みから行番号を特定し、対象を**関数・クラス単位で丸ごと**部分読み込みする（数行の断片で止めない）
*   同じファイルを繰り返し読まない。既に読んだ内容・自分が書いた内容は再取得しない。

## 4. 差分ベースの観測

*   状態確認は全再読み込みではなく `git diff --name-only` / `git diff --stat` で全体像を掴み、ファイル単位で個別に差分を見る。
*   `git diff -U0` は「どこが変わったか」の俯瞰専用。レビュー・Edit 用の置換文字列作成では通常の文脈付き diff か、該当関数の全体を読む。

## 5. 構造化出力の射影と高密度形式

人間向けのリッチ表示をパースせず、最初から必要フィールドだけを機械可読形式で取る。
*   CLI: `gh pr list --json number,title -q '.[]'`、`jq -c '.items[] | {id, status}'`
*   SQL/DuckDB: `SELECT *` を避け、必要列 + `LIMIT`。行ダンプより先に `COUNT(*)` や集計で答えられないか検討する。
*   出力形式: インデントなし JSON、CSV/TSV。罫線付きテキスト表や桁揃えの空白は避ける（Markdown 表も CSV/TSV よりは冗長）。

## 6. データフレーム

生データの `print(df)` は避け、「型と構造＋最小サンプル」に絞る。
*   Polars: `df.schema`, `df.glimpse()`, `df.head(3)`, `df.tail(3)`
*   pandas: `df.dtypes`, `df.info()`, `df.head(3)`, `df.tail(3)`
*   列数が多い・ネスト列（List/Struct 等）がある場合は `glimpse` 自体が長くなるので、先に `select` で列を絞る。

## 7. サブエージェント委譲（最大の圧縮手段）＋受け取り後の検証

広域探索はメイン文脈で出力を削っても積み上がるため、サブエージェントに委譲して結論だけを受け取る。
*   1サブエージェント1タスク。「何を・どの形式で・どの程度の長さで返すか」を指定して投げる。
*   サブエージェントへの指示と返答の形式は英語でよい。ただし固有名詞・引用・ファイルパス・ファイルに書き込む文面は原文の言語のまま扱う。ユーザーへの報告は日本語。
*   **受け取った固有名詞は未検証扱い**: サブエージェントが返したファイルパス・行番号・ID・テーブル名・関数名は、使う前に自分で検索ツールか部分読み込みで実在を確認する。存在しない名前を返すことがある。
*   探索（どこにあるか）は委譲してよいが、**レビュー・監査の判定**を断片しか読まない探索用エージェントに任せない。判定は自分で対象を通読して行う。

## 8. Web 検索・Web 取得

*   クエリは固有名詞・年・単位まで含めて一発で絞る。再検索は新情報が要る時だけ。
*   検索結果から一次資料らしい1〜2件だけを Fetch する。ヒットした URL を全件 Fetch しない。
*   WebFetch は `prompt` で「必要な事実（数値・日付・主体）だけ抽出」と射影する。
*   複数ページにまたがる調査は委譲し、事実・出典・確度タグだけを受け取る（§7 の検証ルールも適用）。Claude Code では Claude のサブエージェントではなく `web-search` スキルの `gemini_parallel.py`（Gemini CLI エージェントへの並列委譲）を使う。Claude のサブエージェントは1体ごとにシステムプロンプト・ツール定義・取得ページ本文が積み上がり、Web 調査では最も高くつく。
*   圧縮しても出典 URL と確度タグ（[一次]/[要検証] 等）は必ず残す。

## 9. 数値基準（既定値）

*   単一ツール出力は原則 **100行以内**を目標。超えそうなコマンドは §2 の正規形でファイル経由にする。
*   検索ツールは件数が読めないうちは `output_mode: count` か `files_with_matches` で規模を見てから内容を出す。Claude Code の `Grep` は `head_limit` 既定250なので、必要に応じて明示的に小さく指定する。
*   ディレクトリ把握は再帰一覧ではなく、深さ制限かファイル名パターンで限定する。

## 10. アンチパターン変換表

| アンチパターン | 代替 |
|---|---|
| `cat <大ファイル>` / 300行超の全行読み込み | 骨組み抽出 → 関数単位の部分読み込み（§3） |
| `ls -R` / 再帰フル一覧 | パターン指定のファイル検索、深さ制限 |
| `cmd \| tail -30`（Bash、pipefail なし） | ログファイル経由 + `echo "exit=$ec"`（§2） |
| `npm install`（素のまま） | `npm install --quiet --no-progress` |
| `pip list` / `npm ls` 全件 | 対象パッケージ名で絞り込み |
| ロックファイル（`uv.lock` / `package-lock.json` / `poetry.lock`）を `cat` して版を調べる | `uv pip list --outdated` / `uv tree --outdated --depth 1` / `npm outdated`。特定パッケージは `grep -A3 '^name = "pkg"' uv.lock` で絞り込む（`uv.lock` はハッシュ行だけで数千行になる） |
| `git log`（引数なし） | `git log --oneline -n 5` |
| `git diff`（いきなり全体） | `git diff --stat` → ファイル単位（§4） |
| verbose な docker build ログ全文 | リダイレクト → 失敗時のみ末尾・エラー周辺を抽出（§2） |
| DataFrame の `print(df)` | schema/dtypes + head/tail（§6） |
| サブエージェントの返したパスをそのまま Edit | 実在確認してから使う（§7） |
| ヒットした URL を全部 Fetch | 一次資料らしい1〜2件に絞り `prompt` で射影（§8） |
| 広範なリサーチをメイン文脈で回す | サブエージェントに委譲し結論だけ受け取る（§7, §8） |

## 圧縮しない場面

以下では「必要な単位を丸ごと読む」を優先する。断片読みは誤読の主因になる。
*   **コードレビュー・監査・バグ原因の特定**: 対象の関数・クラス・ファイルを通読する。`-U0` diff や数行の grep ヒットだけで判定しない。
*   **Edit の置換文字列を作るとき**: 置換対象の前後を実際に読んで正確な文字列を得る。
*   **事実の検証**（数値・設定値・仕様の確認）: 根拠箇所を文脈込みで読む。

## 安全弁

*   終了コードと失敗のシグナルは観測から落とさない（§2 の正規形）。
*   コマンドが失敗したら、次の1回はフィルタを緩めて再観測してよい（末尾行数を増やす・context を広げる・フルログをファイルで保全）。圧縮より原因特定を優先する。
*   迷ったら自問する：「この出力はすべて必要か。ただし、削ることで判断に必要な証拠まで失っていないか。」
