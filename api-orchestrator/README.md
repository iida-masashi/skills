# API Orchestrator

Gemini API と Grok (xAI) API の呼び出しを一本化するオーケストレーター。利用可能なモデルを動的に偵察してタスクの複雑度に応じたモデルを選び、リトライ・プロバイダ間フォールバック・スキルルーティング・Web検索・MCP経由のツール呼び出しループをまとめて実行する。

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | スキルの説明とワークフロー定義 |
| [mcp_servers.json](mcp_servers.json) | 起動するMCPサーバー群の定義 |
| [assets/gemini.md_fragment](assets/gemini.md_fragment) | プロジェクト設定への組み込み断片 |

## Quick Start

```bash
pip install -r requirements.txt
```

`.env` に `GOOGLE_API_KEY`（または `GEMINI_API_KEY`）と `XAI_API_KEY` を設定する。片方だけでも動くが、その場合はプロバイダ間フォールバックが無効になる。MCPサーバーは `npx`/`uvx` 経由でサブプロセス起動されるため、Node.js（npx）と `uv`（uvx）がインストールされている必要がある。

## Commands

```bash
python scripts/orchestrator.py [--provider gemini|grok] [--json] [--grounding] [--auto-run] [--yes] [--max-turns N] [--cache-file <path>] "プロンプト"

python scripts/scout.py [keyword]
```

- `--provider`: 使うプロバイダ（既定 `gemini`）。全滅した場合はもう一方のプロバイダの Primary に切り替える。
- `--json`: レスポンスをJSON出力に強制する（Gemini: `response_mime_type=application/json`、Grok: `text.format={"type": "json_object"}`）。
- `--grounding`: Web検索を有効化する（Gemini: `google_search`、Grok: `web_search`）。
- `--auto-run`: ルーティングで推奨されたスキルを実行するコマンドをモデルに生成させる。実行前に確認を求める（対話環境で `y` 応答が必要。非対話環境では `--yes` 無しだと実行を拒否する）。
- `--yes`: `--auto-run` の確認プロンプトを無条件でスキップする。
- `--max-turns N`: エージェントループ（ツール呼び出し→結果反映→再送信）の最大反復回数（既定8）。到達すると失敗として扱い、フォールバックに進む。
- `--cache-file <path>`: Gemini では指定ファイルをアップロードし、Context Caching API でキャッシュ（TTL 300秒）を作成してから本処理に使う。Grok ではファイル本文をプロンプトに埋め込む。
- `scout.py [keyword]`: 利用可能なモデル一覧をカテゴリ分類（Specialist/Primary/Utility）してMarkdownテーブルで表示する。`XAI_API_KEY` があれば Grok のモデルと料金も表示する。keyword指定時は名前でフィルタする。

## Highlights

- **動的モデル偵察** — `scout.py` がモデル一覧を取得し、各ティアの最新モデルを選ぶ。
  - Gemini: `gemini-<版>-<pro|flash|flash-lite>[-preview]` に完全一致する名前だけを候補にし、版数が最も大きいもの（同じ版ならGA優先）を選ぶ。TTS・Live・画像などの派生モデルは候補にならない。取得できない場合は `gemini-3.1-pro-preview` / `gemini-3.8-flash` / `gemini-3.5-flash-lite` を使う。
  - Grok: `/v1/language-models` から、Specialist＝最新（`created` 順）の汎用モデル、Primary＝出力単価が最も安い汎用モデル、Utility＝最新の non-reasoning モデルを選ぶ。xAI の版番号は発売順と一致しない（"4.20" の後に "4.3"）ため、版番号では比較しない。取得できない場合は `grok-4.7` / `grok-4.3` / `grok-4.20-0309-non-reasoning` を使う。
- **複雑度キーワードによるモデル選択** — プロンプトに `数学`, `統計`, `最適化`, `PSI`, `推論`, `a^2`, `アルゴリズム`, `予測` のいずれかが含まれるとSpecialistモデルを、それ以外はPrimaryモデルを使う。Gemini 3系には thinking_config を付与する（Specialist は `high`、Primary は `low`。`gemini-3.8-flash` は `minimal` を400で拒否する）。
- **リトライとフォールバック** — `tenacity` で指数バックオフ・最大3回リトライ。メインモデルが失敗する（空の回答・`--max-turns` 到達を含む）と、同じプロバイダのPrimaryで履歴を使わない単発プロンプトを試し、それも失敗するともう一方のプロバイダのPrimaryに切り替える。
- **トークン使用量とコストを記録する** — Gemini は `COST_PER_1M_TOKENS` のレート表（モデル名の部分一致、キー文字列が長い順に評価）で、思考トークンも出力単価で計算する。Grok は起動時に `/v1/language-models` から取得した料金で計算する。どちらにも一致しなければ `in=0.10 / out=0.40` のデフォルト。圧縮・ルーティング・コマンド生成・エージェントループの各ターンを含め、呼び出しごとに標準出力と `usage_log.jsonl` に書き出し、合計額も表示する。
- **プロンプトが5000文字を超えると事前圧縮する** — 本処理の前にUtilityモデルへ要約を依頼し、要約結果と元プロンプトの抜粋（先頭500文字＋末尾1000文字）を結合したものを本処理に渡す（Gemini で `--cache-file` 指定時はスキップ）。
- **スキルルーティング** — Utilityモデルに `SkillRouting`（Pydanticモデル）の構造化出力で、`darts-forecast-skill` / `opendata-skill` / `consultant-toolkit` / `python-safe-coding` / `none` のいずれかを選ばせる。
- **Agentic Chaining（`--auto-run`）** — 上記ルーティング結果を使い、実行コマンドをモデルにテキスト生成させる。実行前に確認ステップを挟む（`--yes`でスキップ可能、非対話環境では`--yes`必須）。確認を通過したコマンドは `shell=True` で実行する。
- **MCPツール連携** — `mcp_manager.py` の `MCPManager` が `mcp_servers.json` 記載のサーバー（sequential-thinking / puppeteer / reddit / fetch / memory / anaplan）をサブプロセスとして起動し、`list_tools()` で取得したツールを Gemini の `function_declarations`（`parameters_json_schema`）または Grok の function ツールに変換する。モデルがツール呼び出しを返す限り、ツール実行→結果を履歴に追加→再送信のループを継続する。Gemini で Web検索と併用するときは `include_server_side_tool_invocations` を付ける。
- **Context Caching** — Gemini では `--cache-file` でファイルをアップロードし、`client.caches.create(..., ttl="300s")` でキャッシュを作成、`cached_content` として本処理のconfigに渡す。

## 実行例

```bash
# 標準実行（Gemini、MCP自動連携込み）
python scripts/orchestrator.py "この関数のバグを直して"

# Grokで実行
python scripts/orchestrator.py --provider grok "この関数のバグを直して"

# JSON出力を強制
python scripts/orchestrator.py --json "在庫データをJSONで整形して"

# Web検索を使う
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

- **Gemini Flash の料金は 2027-01-01 に倍増する** — `COST_PER_1M_TOKENS` の Gemini 単価は 2026-10-04 に [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) を WebFetch で2回取得し、値が一致したもの。`gemini-3.6/3.7/3.8-flash` の `in=0.75 / out=3.75` は 2026-12-31 までの価格で、2027-01-01 から `in=1.50 / out=7.50` になる。それまでに表を更新しないとコストが半分に見積もられる。
- **Gemini で `--grounding --json` を併用すると不安定** — `gemini-3.8-flash` に Web検索・JSONモード・MCPツールを同時に渡すと、検索を数十回繰り返して `TOO_MANY_TOOL_CALLS` で本文なしに終わる、またはMCPツールを呼び続けて `--max-turns` に達することがある（2026-10-04 実測、JSONモードを外すと正常）。どちらもフォールバック（ツールなしの単発プロンプト→Grok）で救済されるが、ターン上限まで回る分のコストと時間がかかるため、この組み合わせは最初から `--provider grok` を使う方がよい。
- **Grok には Context Caching API が無い** — `--cache-file` はファイル本文をプロンプトに埋め込むだけになる。
- **一部の MCP サーバーが動かない** — `@modelcontextprotocol/server-puppeteer` は npm で非推奨化済み（起動はする）。`reddit-no-auth-mcp-server` は uvx の実行環境で `httpx` が見つからず起動に失敗する（2026-10-04 時点）。`anaplan` は `<path-to-anaplan-mcp>` を実パスに書き換えるまで失敗する。いずれも接続失敗は警告だけで処理は続く。
