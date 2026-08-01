# Galaxy Orchestrator

Gemini 3 系列（3.1 Pro / 3.6 Flash / 3.5 Flash-Lite）の呼び出しを一本化するオーケストレーター。利用可能なモデルを動的に偵察してタスクの複雑度に応じたモデルを選び、リトライ・フォールバック・スキルルーティング・MCP経由のツール呼び出しループをまとめて実行する。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | スキルの説明とワークフロー定義 |
| [mcp_servers.json](mcp_servers.json) | 起動するMCPサーバー群の定義 |
| [assets/gemini.md_fragment](assets/gemini.md_fragment) | プロジェクト設定への組み込み断片 |

## Quick Start

```bash
pip install google-genai python-dotenv pydantic tenacity mcp
```

`.env` に `GOOGLE_API_KEY`（または `GEMINI_API_KEY`）を設定する。MCPサーバーは `npx`/`uvx` 経由でサブプロセス起動されるため、Node.js（npx）と `uv`（uvx）がインストールされている必要がある。

## Commands

```bash
python scripts/orchestrator.py [--json] [--grounding] [--auto-run] [--cache-file <path>] "プロンプト"

python scripts/scout.py [keyword]
```

- `--json`: レスポンスをJSON出力に強制する（`response_mime_type=application/json`）。
- `--grounding`: Google Search Grounding ツール（`google_search`）を有効化する。
- `--auto-run`: ルーティングで推奨されたスキルを実行するコマンドをGeminiに生成させ、`subprocess.run(..., shell=True)` で実行してその標準出力/エラーをプロンプトに追記する。
- `--cache-file <path>`: 指定ファイルをアップロードし、Context Caching API でキャッシュ（TTL 300秒）を作成してから本処理に使う。
- `scout.py [keyword]`: 利用可能なモデル一覧をカテゴリ分類（Specialist/Primary/Utility）してMarkdownテーブルで表示する。keyword指定時は名前・表示名でフィルタする。

## Highlights

- **動的モデル偵察** — `scout.py` の `get_best_available_models()` が `client.models.list()` を呼び、モデル名に含まれる文字列（`3.1-pro`, `3.1-flash-lite`, `3.1-flash` など）でSpecialist/Primary/Utilityに分類する。取得できない場合は `gemini-3.1-pro-preview` / `gemini-2.0-flash` / `gemini-3.1-flash-lite-preview` のハードコードされたデフォルトにフォールバックする。
- **複雑度キーワードによるモデル選択** — プロンプトに `数学`, `統計`, `最適化`, `PSI`, `推論`, `a^2`, `アルゴリズム`, `予測` のいずれかが含まれるとSpecialistモデル（`thinking_level="high"`）を、それ以外はPrimaryモデル（`thinking_level="minimal"`）を使う。
- **リトライとフォールバック** — `tenacity` で指数バックオフ・最大3回リトライ。それでも失敗した場合はPrimaryモデルに切り替え、履歴を使わない単発プロンプトで再試行する。
- **トークン使用量とコストを記録する** — レスポンスの `usage_metadata` からトークン数を取得し、`COST_PER_1M_TOKENS` のレート表（モデル名の部分一致で選択、一致しなければ `in=0.10 / out=0.40` のデフォルト）でコストを算出し、標準出力と `usage_log.jsonl` に書き出す。
- **プロンプトが5000文字を超えると事前圧縮する** — 本処理の前にUtilityモデルへ要約を依頼し、要約結果と元プロンプトの先頭1000文字を結合したものを本処理に渡す（`--cache-file` 指定時はスキップ）。
- **スキルルーティング** — Utilityモデルに `SkillRouting`（Pydanticモデル）の構造化出力で、`darts-forecast-skill` / `opendata-skill` / `consultant-toolkit` / `python-safe-coding` / `none` のいずれかを選ばせる。
- **Agentic Chaining（`--auto-run`）** — 上記ルーティング結果を使い、実行コマンドをGeminiにテキスト生成させて `shell=True` でそのまま実行する。生成されたコマンドの安全性はコード側で検証していない。
- **MCPツール連携** — `mcp_manager.py` の `MCPManager` が `mcp_servers.json` 記載のサーバー（sequential-thinking / puppeteer / reddit / fetch / memory / anaplan）をサブプロセスとして起動し、`list_tools()` で取得したツールをGeminiの `function_declarations` に変換する。Geminiが `function_calls` を返す限り、ツール実行→結果をhistoryに追加→再送信のループ（終了条件はfunction_callsが空になったときのみ）を継続する。
- **Context Caching** — `--cache-file` でファイルをアップロードし、`client.caches.create(..., ttl="300s")` でキャッシュを作成、`cached_content` として本処理のconfigに渡す。

## 実行例

```bash
# 標準実行（MCP自動連携込み）
python scripts/orchestrator.py "この関数のバグを直して"

# JSON出力を強制
python scripts/orchestrator.py --json "在庫データをJSONで整形して"

# Google Search Groundingを使う
python scripts/orchestrator.py --grounding "最新のニュースを教えて"

# ルーティング結果のコマンドを自動実行
python scripts/orchestrator.py --auto-run "トヨタの財務状況を分析して"

# ファイルをContext Cachingしてから要約
python scripts/orchestrator.py --cache-file "C:\path\to\doc.txt" "このドキュメントを要約して"

# モデル偵察
python scripts/scout.py
python scripts/scout.py flash
```
