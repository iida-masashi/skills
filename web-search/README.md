# web-search

Web検索とURL取得を行うSkill。**標準ではGemini APIを使い、失敗した場合のみClaudeネイティブのWebSearch/WebFetchにフォールバックする。**

| Document | Purpose |
|----------|---------|
| [SKILL.md](SKILL.md) | 判断フロー（Gemini優先→フォールバック）と留意点 |

実体はこのフォルダ配下の `tools/gemini_websearch.py` / `tools/gemini_webfetch.py` の2スクリプトで、このフォルダ自身が独立した軽量uvプロジェクト（`pyproject.toml`、依存は`google-genai`のみ）になっている。APIキー等の認証情報だけは秘密情報のため、既定で`<gemini-workdir>\.env`（作者環境のGemini作業ディレクトリ）を参照する。別環境に持ち込む場合は環境変数`GEMINI_SKILL_ENV_PATH`で`.env`の場所を上書きできる。

## Quick Start

初回のみ依存解決:

```bash
cd claude-gemini-skills/web-search && uv sync
```

APIキー/認証は既定で `<gemini-workdir>\.env` から自動読み込みされる（`GEMINI_SKILL_ENV_PATH`で上書き可）。両スクリプトとも起動時に以下の順で認証情報を解決する。

1. `GEMINI_API_KEY` または `GOOGLE_API_KEY`（`.env`にあれば） → APIキー認証（`vertexai=False`）
2. 上記が無く `GOOGLE_GENAI_USE_VERTEXAI=true` → Vertex AI（ADC認証、`GOOGLE_CLOUD_PROJECT`・`GOOGLE_CLOUD_LOCATION`は既定`us-central1`）
3. どちらもなければ標準エラーにメッセージを出して終了（exit 1）

すでにOS環境変数に同名キーが設定されている場合は`.env`の値で上書きしない。

## 主要コマンド

### Web検索

```bash
cd claude-gemini-skills/web-search && uv run python tools/gemini_websearch.py "検索クエリ"
```

出力: Geminiの回答本文 + `--- 検索クエリ ---`（Geminiが実際にGoogle検索した語句） + `--- 出典 ---`（実URL解決済み） + `--- 文単位の裏付け監査 (Grounding Audit) ---`（Status: OK または ⚠️未裏付け文警告）。

追加フラグ:
- `--json` — 回答、出典、検索クエリ、裏付け監査結果をJSONで出力する（`--verify-claim`併用時は`claim_checks`キーが追加される）。Agent側で出典を反復処理したい場合に使う。
- `--no-audit` — 文単位の裏付け監査（`grounding_supports`突合）の出力を省略する（軽量化したい場合）。
- `--thinking` / `--thinking-budget N` — 思考プロセス（Thinking）を有効化して、複雑な論理や複数数値の突合精度を高める（既定バジェット 1024）。
- `--no-resolve` — 出典URLのリダイレクト実URL逆引き解決を無効化する。
- `--verify-claim` — 回答本文の主張を**事実の最小単位ごとに箇条書きへ分解**し、各出典ページで裏付けられるかを項目単位でクロスチェックする（内部的には`gemini_webfetch.check_claim_raw`を全出典に対し並列実行）。判定は各出典・各項目ごとに「裏付けあり/裏付けなし/不明」＋根拠。並列実行（最大4並列）のため、出典が複数あっても待ち時間は概ね1回分で収まる。
- `--refute` — クエリを「この主張を否定・反証する情報がないか」という反証志向のプロンプトに自動変換してから検索する。「AとBに関係がある」のような一文の真偽を疑うときに使う。
- `--model MODEL` — 使用するGeminiモデルを指定する（既定: `gemini-3.8-flash`）。`--verify-claim`の裏付けチェックにも同じモデルが使われる。

### URL取得（WebFetch相当）

```bash
cd claude-gemini-skills/web-search && uv run python tools/gemini_webfetch.py "<URL>" ["追加の指示（省略可）"]
```

追加の指示を省略した場合のデフォルトは「このページの内容を詳しく要約して」。
※GoogleのリダイレクトURL（`vertexaisearch.cloud.google.com/grounding-api-redirect/...`）が渡された場合も自動で実URLへ逆引き解決してから取得します。

出力: Geminiの回答本文 + `--- 取得ステータス ---` 以下に `URL_RETRIEVAL_STATUS_SUCCESS` / `FAILED` 等のステータスと実際に取得したURL（`retrieved_url`）。

追加フラグ:
- `--check "<主張>"` — 要約の代わりに、この1URLの内容が指定した主張を裏付けるかを検証する。主張は項目単位に分解された上で判定される。特定の1ページに対して単発で「本当にそう書いてあるか」を確認したいときに使う（`gemini_websearch.py --verify-claim`は複数出典を横断する場合向け）。自由記述の追加指示とは同時指定不可。
- `--json` — `--check`使用時、結果を`{url, items: [{claim, verdict, detail}], statuses}`のJSONで出力する。
- `--model MODEL` — 使用するGeminiモデルを指定する（既定: `gemini-3.8-flash`）。

## Highlights

- **常時ハルシネーション抑制アーキテクチャ** — (1)検索結果外の推測補完を厳禁とするシステム指示、(2)生成ゆらぎを排除する `temperature=0.0`、(3)時制の混乱を防ぐ現在基準日（Anchor Date）の動的注入、(4)発行された検索クエリ（`web_search_queries`）の可視化が標準で機能します。
- **文単位の裏付け監査（既定で有効）** — Gemini APIの `grounding_supports` メタデータを自動突合。回答本文のどの文がどのWeb出典に基づくかを追跡し、Web出典の根拠がない文章（モデルの推測・事前学習記憶の疑いがある箇所）を自動検知して警告（Status: WARNING）します。
- **高速実URL並列解決** — 出典URL（`vertexaisearch...`）は302 FoundのLocationヘッダーのみをキャプチャし、相手先サーバーの403ブロックや巨大PDFダウンロードによるタイムアウトを回避。重複排除＋ThreadPoolExecutor（最大8スレッド）により0.1〜0.2秒で全件の実URLを確定します。
- **Gemini API優先＋Claude WebSearch/WebFetchフォールバック** — ClaudeのWebSearchはセッション単位の回数上限があり枯渇しやすいが、Geminiは別課金枠で消費しない。ClaudeのWebFetchは証明書エラー等で失敗するサイトがあるが、Geminiの`url_context`ツールはGoogle側の取得経路を使うため成功する場合がある。
- **判断フロー**: (1)まずGemini経由を試す→(2)取得ステータスが`FAILED`、または回答が空・的外れ・情報不足ならClaude側WebSearch/WebFetchで再試行→(3)Claude側もエラー（証明書エラー・予算上限等）ならGeminiの結果を「参考情報」と明示して報告、両方失敗ならその旨を伝える→(4)出典URLを一次資料として記録する場合、自動解決された実URLはそのまま使ってよい。`(解決失敗、リダイレクトURLのまま)`と表示された場合のみClaude側WebSearch/WebFetchで実URLを確認する。
- **モデルは`--model`で変更可能** — 両スクリプトとも既定値は`gemini-3.8-flash`だが、`--model gemini-3.1-pro-preview`のように指定すれば他モデルに切り替えられる。`--thinking` を付与することで思考バジェットを活用可能。
- **ツールの使い分け** — Web検索は`google_search`（Google Search grounding）、URL取得は`url_context`という別々のGemini APIツールを使う。
- **前提そのものがハルシネーションのことがある** — 個別事実（日付・数値等）だけでなく、「AとBに関係がある」「Xという施設・法人格が実在する」という**関係性・実在性の主張自体**が誤りであるケースが複数回確認されている（似た名称の別法人・別企業との混同、風評の取り違え等）。こうした主張は`--verify-claim`（出典との裏付けクロスチェック）または`--refute`（反証志向の再検索）で積極的に疑う。
- **裏付けチェックは項目単位・並列実行** — `--verify-claim`（websearch）・`--check`（webfetch）はいずれも、主張をそのまま1文で問い合わせるのではなく「否定できない事実の最小単位」に分解してから各出典に判定させる。複数の事実が混ざった複合的な主張（例:「住所＋電話番号＋関連施設名」）を一括りに検証すると、一部だけ裏付けられない場合に全体が「不明」判定になりがちなため、項目分解によって「どの部分が裏付けられ、どの部分が裏付けられないか」を明確にする。`--verify-claim`は複数出典への問い合わせを`ThreadPoolExecutor`で並列実行（最大4並列）するため、出典が増えても待ち時間は概ね1回分で収まる。
- **法人番号検索は個別URLが有効** — gBizINFO・国税庁法人番号公表サイトは法人"名"検索がJS駆動でWebFetch・Gemini `url_context`とも失敗しやすいが、法人番号が判明していれば `https://info.gbiz.go.jp/hojin/ichiran?hojinBango=<13桁>` の個別URLはWebFetchで直接取得できる。法人番号不明時はまずGemini websearchで番号と実URLを特定してから切り替える。
- **`.env`の秘匿情報に注意** — `.env`には他のAPIキー（Vertex AI関連・Anthropic・xAI等）も同居しているため、このSkillの実装や出力をログ・ノートに残す際にキーの値そのものを含めないこと。

## 実行例

```bash
$ cd claude-gemini-skills/web-search && uv run python tools/gemini_websearch.py "Gemini 3.6 Flash リリース日"
(Geminiによる回答本文)

--- 検索クエリ (web_search_queries) ---
- Gemini 3.6 Flash release date
- Gemini 3.6 Flash リリース日

--- 出典 ---
[1] Example Title - https://example.com/actual-article-path

--- 文単位の裏付け監査 (Grounding Audit) ---
Status: OK (すべての主要文章がWeb出典に基づいています)
```


```bash
$ cd claude-gemini-skills/web-search && uv run python tools/gemini_webfetch.py "https://example.com/article"
(このページの内容を詳しく要約して、の回答本文)

--- 取得ステータス ---
URL_RETRIEVAL_STATUS_SUCCESS  https://example.com/article
```

```bash
$ cd claude-gemini-skills/web-search && uv run python tools/gemini_websearch.py "A社の創業者はB財団の理事を務めている" --refute
(反証志向のプロンプトに変換されて実行される。肯定情報より否定・矛盾する情報を優先的に探し、
 混同の背景〈似た名前の別法人、社名の連想等〉まで報告する)
```

```bash
$ cd claude-gemini-skills/web-search && uv run python tools/gemini_websearch.py "架空商事株式会社の本社所在地" --verify-claim
(回答本文の後に、出典・項目単位の裏付け判定が付く。全出典への問い合わせは並列実行される)

--- 出典の裏付けチェック（--verify-claim、主張を項目単位に分解して判定） ---
[1] example.co.jp - https://example.co.jp/company/access.html
    裏付けあり  架空商事株式会社の本社住所は〒100-0001 東京都千代田区千代田1-1である。
      ページ下部に住所・電話番号が明記されている。
    不明  架空商事株式会社の最寄り駅は東京駅である。
      ページ内に最寄り駅の記載がないため確認できない。
```

```bash
$ cd claude-gemini-skills/web-search && uv run python tools/gemini_webfetch.py "https://ja.wikipedia.org/wiki/架空商事" --check "架空商事の本社は東京都千代田区にある"
(1URL単発での主張検証。項目単位に分解して判定される)

[1] 裏付けあり  架空商事の本社は東京都にある
    記事冒頭やインフォボックスに本社の所在地が東京都であると記載されているため。
[2] 裏付けあり  架空商事の本社は千代田区にある
    記事冒頭やインフォボックスに本社の所在地が千代田区であると記載されているため。
```
