# Galaxy Orchestrator

Gemini 3 系列（3.1 Pro / 3.6 Flash / 3.5 Flash-Lite）の呼び出しを一本化するオーケストレーター。利用可能なモデルを動的に偵察してタスクの複雑度に応じたモデルを選び、リトライ・フォールバック・スキルルーティング・MCP経由のツール呼び出しループをまとめて実行する。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | スキルの説明とワークフロー定義 |
| [mcp_servers.json](mcp_servers.json) | 起動するMCPサーバー群の定義 |
| [assets/gemini.md_fragment](assets/gemini.md_fragment) | プロジェクト設定への組み込み断片 |

## Quick Start

```bash
pip install -r requirements.txt
```

`.env` に `GOOGLE_API_KEY`（または `GEMINI_API_KEY`）を設定する。MCPサーバーは `npx`/`uvx` 経由でサブプロセス起動されるため、Node.js（npx）と `uv`（uvx）がインストールされている必要がある。

## Commands

```bash
python scripts/orchestrator.py [--json] [--grounding] [--auto-run] [--yes] [--max-turns N] [--cache-file <path>] "プロンプト"

python scripts/scout.py [keyword]
```

- `--json`: レスポンスをJSON出力に強制する（`response_mime_type=application/json`）。
- `--grounding`: Google Search Grounding ツール（`google_search`）を有効化する。
- `--auto-run`: ルーティングで推奨されたスキルを実行するコマンドをGeminiに生成させる。実行前に確認を求める（対話環境で `y` 応答が必要。非対話環境では `--yes` 無しだと実行を拒否する）。
- `--yes`: `--auto-run` の確認プロンプトを無条件でスキップする。
- `--max-turns N`: エージェントループ（ツール呼び出し→結果反映→再送信）の最大反復回数（既定8）。到達すると最終回答なしで終了する。
- `--cache-file <path>`: 指定ファイルをアップロードし、Context Caching API でキャッシュ（TTL 300秒）を作成してから本処理に使う。
- `scout.py [keyword]`: 利用可能なモデル一覧をカテゴリ分類（Specialist/Primary/Utility）してMarkdownテーブルで表示する。keyword指定時は名前・表示名でフィルタする。

## Highlights

- **動的モデル偵察** — `scout.py` の `get_best_available_models()` が `client.models.list()` を呼び、モデル名に含まれる文字列でSpecialist（3.1-pro系）/Primary（3.6-flash系優先、3.1-flash系へフォールバック）/Utility（3.5-flash-lite系優先、3.1-flash-lite系へフォールバック）に分類する。取得できない場合は `gemini-3.1-pro-preview` / `gemini-3.6-flash` / `gemini-3.5-flash-lite` のハードコードされたデフォルトにフォールバックする。
- **複雑度キーワードによるモデル選択** — プロンプトに `数学`, `統計`, `最適化`, `PSI`, `推論`, `a^2`, `アルゴリズム`, `予測` のいずれかが含まれるとSpecialistモデル（`thinking_level="high"`）を、それ以外はPrimaryモデル（`thinking_level="minimal"`）を使う。`gemini-3` を含むモデル名にはthinking_configを付与する（フォールバック応答時は付与しない）。
- **リトライとフォールバック** — `tenacity` で指数バックオフ・最大3回リトライ。それでも失敗した場合はPrimaryモデルに切り替え、履歴を使わない単発プロンプトで再試行する。
- **トークン使用量とコストを記録する** — レスポンスの `usage_metadata` からトークン数を取得し、`COST_PER_1M_TOKENS` のレート表（モデル名の部分一致で選択、キー文字列が長い順に評価して最も具体的な一致を優先、どれにも一致しなければ `in=0.10 / out=0.40` のデフォルト）でコストを算出し、標準出力と `usage_log.jsonl` に書き出す。圧縮・ルーティング・コマンド生成・エージェントループの各ターンを含むリクエスト全体の呼び出しごとにコストを記録し、合計額も表示する。
- **プロンプトが5000文字を超えると事前圧縮する** — 本処理の前にUtilityモデルへ要約を依頼し、要約結果と元プロンプトの抜粋（先頭500文字＋末尾1000文字）を結合したものを本処理に渡す（`--cache-file` 指定時はスキップ）。
- **スキルルーティング** — Utilityモデルに `SkillRouting`（Pydanticモデル）の構造化出力で、`darts-forecast-skill` / `opendata-skill` / `consultant-toolkit` / `python-safe-coding` / `none` のいずれかを選ばせる。
- **Agentic Chaining（`--auto-run`）** — 上記ルーティング結果を使い、実行コマンドをGeminiにテキスト生成させる。実行前に確認ステップを挟む（`--yes`でスキップ可能、非対話環境では`--yes`必須）。確認を通過したコマンドは `shell=True` で実行する。
- **MCPツール連携** — `mcp_manager.py` の `MCPManager` が `mcp_servers.json` 記載のサーバー（sequential-thinking / puppeteer / reddit / fetch / memory / anaplan）をサブプロセスとして起動し、`list_tools()` で取得したツールをGeminiの `function_declarations` に変換する。Geminiが `function_calls` を返す限り、ツール実行→結果をhistoryに追加→再送信のループを継続する。`--max-turns` で反復回数の上限を設定できる（既定8、上限に達すると最終回答なしで終了）。
- **Context Caching** — `--cache-file` でファイルをアップロードし、`client.caches.create(..., ttl="300s")` でキャッシュを作成、`cached_content` として本処理のconfigに渡す。

## 実行例

```bash
# 標準実行（MCP自動連携込み）
python scripts/orchestrator.py "この関数のバグを直して"

# JSON出力を強制
python scripts/orchestrator.py --json "在庫データをJSONで整形して"

# Google Search Groundingを使う
python scripts/orchestrator.py --grounding "最新のニュースを教えて"

# ルーティング結果のコマンドを自動実行（確認あり）
python scripts/orchestrator.py --auto-run "トヨタの財務状況を分析して"

# 確認をスキップして自動実行（CI等の非対話環境向け）
python scripts/orchestrator.py --auto-run --yes "トヨタの財務状況を分析して"

# エージェントループの上限を増やす
python scripts/orchestrator.py --max-turns 15 "複数ツールを跨ぐ複雑な調査をして"

# ファイルをContext Cachingしてから要約
python scripts/orchestrator.py --cache-file "C:\path\to\doc.txt" "このドキュメントを要約して"

# モデル偵察
python scripts/scout.py
python scripts/scout.py flash
```

## 既知の留保事項

- **料金表は未一次検証** — `COST_PER_1M_TOKENS` の単価は2026-08-01時点でWebFetch要約経由で調査した値。特に `gemini-3.6-flash` は旧flashレートの約20倍という異例の値のため、コストが重要な判断材料になる場合は [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) を直接確認すること。
- **3.6/3.5系のthinking_config対応は実機未検証** — `gemini-3.6-flash`・`gemini-3.5-flash-lite` がThinking対応であることは確認済みだが、`thinking_level` パラメータの受理可否は実際のAPI呼び出しで未確認。エラーになった場合はフォールバック（thinking_configなしのPrimaryモデル）に自動で切り替わる。
