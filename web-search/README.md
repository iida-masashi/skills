# web-search

Web検索とURL取得を行うSkill。**標準ではGemini APIを使い、失敗した場合のみClaudeネイティブのWebSearch/WebFetchにフォールバックする。**

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | 判断フロー（Gemini優先→フォールバック）と留意点 |

実体はこのフォルダ配下の `tools/gemini_websearch.py` / `tools/gemini_webfetch.py` の2スクリプトで、このフォルダ自身が独立した軽量uvプロジェクト（`pyproject.toml`、依存は`google-genai`のみ）になっている。APIキー等の認証情報だけは秘密情報のため、既定で`C:\Users\iidam\gemini\.env`（作者環境のGemini作業ディレクトリ）を参照する。別環境に持ち込む場合は環境変数`GEMINI_SKILL_ENV_PATH`で`.env`の場所を上書きできる。

## Quick Start

初回のみ依存解決:

```bash
cd claude-gemini-skills/web-search && uv sync
```

APIキー/認証は既定で `C:\Users\iidam\gemini\.env` から自動読み込みされる（`GEMINI_SKILL_ENV_PATH`で上書き可）。両スクリプトとも起動時に以下の順で認証情報を解決する。

1. `GEMINI_API_KEY` または `GOOGLE_API_KEY`（`.env`にあれば） → APIキー認証（`vertexai=False`）
2. 上記が無く `GOOGLE_GENAI_USE_VERTEXAI=true` → Vertex AI（ADC認証、`GOOGLE_CLOUD_PROJECT`・`GOOGLE_CLOUD_LOCATION`は既定`us-central1`）
3. どちらもなければ標準エラーにメッセージを出して終了（exit 1）

すでにOS環境変数に同名キーが設定されている場合は`.env`の値で上書きしない。

## 主要コマンド

### Web検索

```bash
cd claude-gemini-skills/web-search && uv run python tools/gemini_websearch.py "検索クエリ"
```

出力: Geminiの回答本文 + `--- 出典 ---` 以下に `[番号] タイトル - URL` 形式の出典一覧（`grounding_chunks`由来）。

### URL取得（WebFetch相当）

```bash
cd claude-gemini-skills/web-search && uv run python tools/gemini_webfetch.py "<URL>" ["追加の指示（省略可）"]
```

追加の指示を省略した場合のデフォルトは「このページの内容を詳しく要約して」。

出力: Geminiの回答本文 + `--- 取得ステータス ---` 以下に `URL_RETRIEVAL_STATUS_SUCCESS` / `FAILED` 等のステータスと実際に取得したURL（`retrieved_url`）。

## Highlights

- **Gemini API優先＋Claude WebSearch/WebFetchフォールバック** — ClaudeのWebSearchはセッション単位の回数上限があり枯渇しやすいが、Geminiは別課金枠で消費しない。ClaudeのWebFetchは証明書エラー等で失敗するサイトがあるが、Geminiの`url_context`ツールはGoogle側の取得経路を使うため成功する場合がある。
- **判断フロー**: (1)まずGemini経由を試す→(2)取得ステータスが`FAILED`、または回答が空・的外れ・情報不足ならClaude側WebSearch/WebFetchで再試行→(3)Claude側もエラー（証明書エラー・予算上限等）ならGeminiの結果を「参考情報」と明示して報告、両方失敗ならその旨を伝える→(4)出典URLを一次資料として記録する必要がある場合は、GeminiのリダイレクトURLをそのまま使わず可能な限りClaude側で実URLを確認する（GeminiのURL取得ステータスに`retrieved_url`として実URLが返っている場合はそれを使ってよい）。
- **モデルはコード内既定** — 両スクリプトとも`gemini-3.6-flash`を関数デフォルト引数としてハードコードしており、CLIから変更する引数は用意されていない。
- **ツールの使い分け** — Web検索は`google_search`（Google Search grounding）、URL取得は`url_context`という別々のGemini APIツールを使う。
- **出典URLの欠点** — Gemini側の出典URLは`vertexaisearch.cloud.google.com/grounding-api-redirect/...`という難読化されたリダイレクトURLになり、実際のページパスが読み取れない。
- **ハルシネーションと鮮度の注意** — Geminiの回答はGoogle Search groundingによるものでも要約段階のハルシネーションリスクはClaude側と同程度にある。また、Geminiが実際にライブでページを取得したのか検索インデックス（キャッシュ）を使ったのかはツール出力からは区別できないため、更新頻度が高いページの最新性を問う場合は注意する。
- **`.env`の秘匿情報に注意** — `.env`には他のAPIキー（Vertex AI関連・Anthropic・xAI等）も同居しているため、このSkillの実装や出力をログ・ノートに残す際にキーの値そのものを含めないこと。

## 実行例

```bash
$ cd claude-gemini-skills/web-search && uv run python tools/gemini_websearch.py "Gemini 3.6 Flash リリース日"
(Geminiによる回答本文)

--- 出典 ---
[1] Example Title - https://vertexaisearch.cloud.google.com/grounding-api-redirect/...
```

```bash
$ cd claude-gemini-skills/web-search && uv run python tools/gemini_webfetch.py "https://example.com/article"
(このページの内容を詳しく要約して、の回答本文)

--- 取得ステータス ---
URL_RETRIEVAL_STATUS_SUCCESS  https://example.com/article
```
