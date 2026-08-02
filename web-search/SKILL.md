---
name: web-search
description: Search the web or fetch a specific URL's content. Use whenever the user asks to search/検索して/調べて the web, look something up online, or fetch/取得して the contents of a URL. Defaults to Gemini API (tools/gemini_websearch.py / tools/gemini_webfetch.py in this skill directory), falling back to Claude's native WebSearch/WebFetch tools when Gemini fails or its output is insufficient.
---

# web-search

Web検索・URL取得を行うスキル。**標準ではGemini APIを使い、うまくいかない場合のみClaudeネイティブのWebSearch/WebFetchにフォールバックする。**

## なぜGeminiを標準にするか

- ClaudeのWebSearchはセッション単位で回数上限があり、頻繁に使うと枯渇する（`CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`で調整可能だが既定値は低い）。Geminiは別課金・別枠なのでClaude側の予算を消費しない。
- ClaudeのWebFetchは自己署名証明書エラー等で失敗するサイトがあるが、Geminiの`url_context`ツールはGoogle側の取得経路を使うため成功することがある。
- Gemini側の欠点は、出典URLが`vertexaisearch.cloud.google.com/grounding-api-redirect/...`という難読化されたリダイレクトURLで返ってくること。`gemini_websearch.py`は既定でこのリダイレクトを1回追跡し、実URL（`resp.geturl()`）に解決してから表示する。サイト側がbot判定でリダイレクト追跡自体を拒否する場合（403等、Mediumで確認済み）は解決に失敗し、その場合のみ元のリダイレクトURLをそのまま表示する（`(解決失敗、リダイレクトURLのまま)`と明記）。`--no-resolve`で解決処理自体を無効化できる（動作確認用途）。

## 実行方法

このスキルディレクトリ自体が独立したuvプロジェクト（依存は`google-genai`のみ）。初回のみ `cd` して `uv sync` で依存解決する。

両スクリプトはAPIキー/Vertex AI設定を既定で `C:\Users\iidam\gemini\.env` から自動読み込みする（環境変数`GEMINI_SKILL_ENV_PATH`でパスを上書き可能）。

### Web検索（検索クエリを投げて要約と出典を得る）

```bash
cd "C:/Users/iidam/claude-gemini-skills/web-search" && uv run python tools/gemini_websearch.py "検索クエリ"
```

出力: Geminiによる回答本文 + `--- 出典 ---`以下に出典タイトルと解決済み実URL一覧（解決失敗時のみリダイレクトURL）。

### URL取得（特定URLの内容を取得・要約する、WebFetch相当）

```bash
cd "C:/Users/iidam/claude-gemini-skills/web-search" && uv run python tools/gemini_webfetch.py "<URL>" ["追加の指示（省略可、既定は要約）"]
```

出力: Geminiによる回答本文 + `--- 取得ステータス ---`以下に`URL_RETRIEVAL_STATUS_SUCCESS`または`FAILED`と実際に取得できたURL。

## 判断フロー

1. まずGemini経由（上記コマンド）を試す。
2. 取得ステータスが`FAILED`、または回答が空・的外れ・情報不足の場合 → ClaudeネイティブのWebSearch/WebFetchツールで再試行する。
3. Claude側もエラー（証明書エラー、予算上限到達等）になった場合 → Gemini側の結果を「参考情報」として明示した上でユーザーに報告する。両方失敗した場合は素直にその旨を伝える。
4. 出典URLを一次資料としてノート等に記録する場合、`gemini_websearch.py`が自動解決した実URLはそのまま使ってよい。ただし出典表示に`(解決失敗、リダイレクトURLのまま)`と付いている場合は、リダイレクトURLを一次資料として記録せず、Claude側のWebFetch/WebSearchで実URLを確認するか、そのドメイン名（タイトル欄）を手がかりに直接検索する。

## 留意点

- Geminiの回答はGoogle Search groundingによるものであり、要約段階でのハルシネーションのリスクはClaude側と同程度にある。確度が必要な情報（法人番号、日付、固有名詞等）は、可能であれば一次資料URLへの直接アクセスで裏取りする。Geminiの回答が提示した「主出典」を実際にWebFetchで開いて該当記述の有無を確認するだけで、Gemini側の誤情報（他事例との混同等）を検出できることがある。
- Geminiが実際にライブでページを取得したのか、Google側の検索インデックス（キャッシュ）から情報を引いているのかは、ツールの出力からは区別できない。更新頻度が高いページの最新性を問う場合は注意する。
- gBizINFO・国税庁法人番号公表サイト等の法人検索は、法人"名"での検索（JS駆動の検索UI）はWebFetch・Gemini `url_context`のいずれでも失敗しやすい。法人番号が判明している場合は `https://info.gbiz.go.jp/hojin/ichiran?hojinBango=<13桁>` の個別URLを直接WebFetchすれば取得できる。法人番号が不明なら、まずGemini websearchで「法人番号 + gBizINFO」を検索しGemini回答内の実URLを抽出してから、この直接アクセスに切り替える。
- `.env`には他のAPIキー（Vertex AI関連、Anthropic、xAI等）も同居しているため、このスキルの実装や出力をログ・ノートに残す際にキーの値そのものを含めないこと。
