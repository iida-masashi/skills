---
name: web-search
description: Search the web or fetch a specific URL's content. Use whenever the user asks to search/検索して/調べて the web, look something up online, or fetch/取得して the contents of a URL. Defaults to Gemini API (tools/gemini_websearch.py / tools/gemini_webfetch.py in this skill directory), falling back to Claude's native WebSearch/WebFetch tools when Gemini fails or its output is insufficient. For multi-query / multi-page research (2+ topics, heavy pages, search→fetch→re-search), use tools/gemini_parallel.py to delegate each topic to a headless Gemini CLI agent in parallel instead of spawning Claude subagents (saves Claude tokens).
---

# web-search

Web検索・URL取得を行うスキル。**標準ではGemini APIを使い、うまくいかない場合のみClaudeネイティブのWebSearch/WebFetchにフォールバックする。**

## 目的：Claude側のWebSearch回数上限（クォータ）の節約

このスキルの主目的は**Claude側トークンの節約ではなく**、ClaudeネイティブのWebSearchツールが持つ**セッション単位の呼び出し回数上限**を消費しないことにある。頻繁にWeb検索が必要な作業（複数企業の並行調査、繰り返しの再検索等）でClaude側のクォータが枯渇するのを避けるため、既定では別課金・別枠のGemini APIを経由する。

**注意（誤解しやすい点）**: `gemini_websearch.py`/`gemini_webfetch.py`の出力はBashの標準出力としてそのままこのセッションのコンテキストに読み込まれるため、単発呼び出しではClaude側のトークン消費は出力量の分だけ発生する。**Claude側のトークンを大きく減らすのは`gemini_parallel.py`（Gemini CLIエージェントへの並列委譲）**で、検索結果やページ本文はGemini側で処理され、Claude側には結論の先頭部分だけが載る（下記「Claude側のコンテキスト消費を抑えたい場合」参照）。

なお、ClaudeのWebFetchは自己署名証明書エラー等で失敗するサイトがあるが、Geminiの`url_context`ツールはGoogle側の取得経路を使うため成功することがある、という副次的なメリットもある。

## 標準の使い方（ハルシネーション抑制＋裏付け監査 既定モード）

以下がこのスキルの**既定の動作**です。ハルシネーション（数値捏造・推測補完・時制混同）を減らす方向のガードが既定で適用されますが、**これらはモデルへの指示とコード側の後付き突合であり、独立した事実検証ではありません**。特に「文単位の裏付け監査」は出典への帰属をモデル自身が申告したメタデータの突合に過ぎない点に注意してください。

* **厳格グラウンディング規律**: システムプロンプトで「検索結果／取得ページにない数値・推測補完の厳禁」「記載がない場合は記載なしと回答」を指示。`gemini_websearch.py`（Google検索）・`gemini_webfetch.py`（URL取得）の両方に適用。
* **temperatureは既定値のまま**: Gemini 3系は公式に「temperatureを既定値1.0から下げるとループ・推論劣化の恐れがある」と明記されており、このスキルも両スクリプトともtemperatureを指定しない（モデル既定に従う）。ハルシネーション抑制はグラウンディング規律・裏付け監査側で担う。
* **現在基準日（Anchor Date）注入**: 実行日の日付（例: `2026-09-10`）を注入し、「今期」「最新」等の時制の取り違えを防止（`gemini_websearch.py`のみ）。
* **発行検索クエリの可視化**: Geminiが内部で実際にGoogle検索に投げたクエリ（`web_search_queries`）を表示。**検索クエリが0件・出典が0件の場合は「検索未実行／回答は事前学習知識のみの可能性」の警告を本文の前に表示する**（`gemini_websearch.py`）。
* **文単位の裏付け監査（既定で有効）**: レスポンスの `grounding_supports` を文単位（`。！？`区切り）で突合し、出典への帰属が申告されていない文（モデル自身の推測の疑いがある箇所）を検知して警告。数字を含む文は長さに関わらず必ず監査対象にする。`grounding_supports`自体が空の場合は「監査不能」と表示する（「OK」とは表示しない）。
* **取得失敗の明示**: `gemini_webfetch.py`は`URL_RETRIEVAL_STATUS_SUCCESS`以外の場合、要約本文より前に取得ステータスと警告を表示する。
* **高速実URL並列解決**: 302 Location ヘッダーの即時抽出により、巨大PDFや403遮断サイトでも実URLの欠落・タイムアウトなし（最大8並列）。

このスキルディレクトリ自体が独立したuvプロジェクト（依存は`google-genai`のみ）。初回のみ `cd` して `uv sync` で依存解決する。

両スクリプトはAPIキー/Vertex AI設定を既定で `C:\Users\iidam\gemini\.env` から自動読み込みする（環境変数`GEMINI_SKILL_ENV_PATH`でパスを上書き可能）。

### Web検索（検索クエリを投げて要約・出典・裏付け監査を得る）

```bash
cd "C:/Users/iidam/claude-gemini-skills/web-search" && uv run python tools/gemini_websearch.py "検索クエリ"
```

出力: （出典0件の場合は先頭に⚠️検索未実行警告）+ Geminiによる回答本文 + `--- 検索クエリ ---` + `--- 出典 ---` + `--- 文単位の裏付け監査 (Grounding Audit) ---`（Status: 帰属あり・未検証 / WARNING / 監査不能）。

- `--json`: 回答、出典、発行クエリ、裏付け監査結果をJSON形式で出力する。後続処理（Agent側での自動反復）に使う場合はこちら。
- `--no-audit`: 文単位の裏付け監査表示を省略する（出力をシンプルにしたい場合や極限まで軽量化したい場合）。
- `--thinking-level {minimal,low,medium,high}`: 思考プロセス（Thinking）の深さを指定する（既定はモデル既定値。`gemini-3.8-flash`は既定でMEDIUM）。複雑な論理・数値突合の精度を上げたい場合は`high`を指定する。legacyな`thinking_budget`パラメータとは同時指定不可のため、このスキルは`thinking_level`のみを使う。
- `--no-resolve`: 出典URLのリダイレクト解決（実URLへの逆引き）自体を省略し、さらに軽量化する。
- `--no-sources`: 出典URL一覧（`--- 出典 ---`ブロック）の表示を省略し、件数だけ表示する。一次資料として記録する予定がない一般検索（「◯◯とは」程度の確認）で有効。`--verify-claim`併用時の出典URL内訳表示には影響しない（そちらは検証目的でURLが必要なため）。
- `--max-chars N`: 回答本文をN文字で打ち切って出力する。このスクリプトの標準出力はBashツール経由でそのままClaude側のコンテキストに読み込まれるため、結論だけ分かればよい場面ではこれで流入量を絞れる（出典一覧・判定結果には影響しない）。

### URL取得（特定URLの内容を取得・要約する、WebFetch相当）

```bash
cd "C:/Users/iidam/claude-gemini-skills/web-search" && uv run python tools/gemini_webfetch.py "<URL>" ["追加の指示（省略可、既定は要約）"]
```

出力: `--- 取得ステータス ---`（`URL_RETRIEVAL_STATUS_SUCCESS`または`FAILED`等と実際に取得できたURL。取得情報が無い場合もその旨を表示）+ SUCCESS以外の場合は⚠️取得失敗警告 + Geminiによる回答本文。なお、GoogleのリダイレクトURL（`vertexaisearch...`）が渡された場合も自動で実URLへ逆引き解決してから取得します。

- `--max-chars N`: 同上（`--check`使用時は元々短い判定結果しか返らないため影響しない）。

**追加の指示は「要約して」ではなく欲しい情報だけを狙って書く。** Gemini側の回答自体が短くなり、Bash出力＝Claude側のコンテキスト消費が減る。例:

```bash
# 悪い例: 全文要約は本文が長くなりがち
uv run python tools/gemini_webfetch.py "<URL>" "このページの内容を詳しく要約して"

# 良い例: 欲しい数値・事実だけに絞る
uv run python tools/gemini_webfetch.py "<URL>" "このページに記載されている削減時間・対象工場数の数値だけを、原文の表現のまま抜き出して。他の説明は不要"
```

## オプション機能：さらに厳密な検証モード（明示的に指定したときだけ使う）

上記「標準の裏付け監査（Grounding Audit）」はAPIレスポンスのメタデータのみを用いて追加通信なしで検証しますが、以下は**追加のGemini API呼び出しを発生させてより強固に裏取りする機能**です。

- **`gemini_websearch.py "クエリ" --verify-claim`**: 回答本文中でgrounding済み（出典への帰属が申告済み）の文をclaim単位とし、その出典URLごとに1回だけ問い合わせて裏付けを検証する（同じURLに複数claimが帰属している場合もまとめて1回で判定）。判定は構造化出力（JSON Schema）で強制し、「裏付けあり」の場合は原文からの引用（quote）を必須にする。claim単位の最終判定は「1出典でも裏付けあり（quote付き）→裏付けあり／全出典が裏付けなし→裏付けなし／それ以外→不明」に集約する。出典URLへの問い合わせは並列実行（最大4並列）。`grounding_supports`が空（出典への帰属が一切申告されていない）の場合はスキップされ、その旨が表示される。
- **`gemini_websearch.py "クエリ" --refute`**: クエリを「この主張を否定・反証する情報がないか」という反証志向のプロンプトに自動変換してから検索する。「AとBに関係がある」のような一文の真偽を疑うときに使う。
- **`gemini_webfetch.py "<URL>" --check "<主張>"`**: 要約の代わりに、特定の主張1件がこのURLの内容で裏付けられるかを検証する。判定は構造化出力（JSON Schema）で行い、「裏付けあり」の場合は原文引用（quote）を必須にする（quoteが空なら自動的に「不明」へ格下げ）。
  - `--json`併用で`{url, items: [{claim, verdict, quote, detail}], statuses, fetch_ok}`を得られる。
  - **取得ステータスがSUCCESSでも、実際に取得できたページのホストが要求したURLのホストと異なる場合は「不明」へ格下げされる**（ログイン壁・別ページへのリダイレクト等、「何かは取れたが求めたページではない」ケースの対策）。

これらのオプション機能を多用するタスク（企業事例の事実確認、既存ノートの数値検証など）では、`solution-research`スキルが調査〜検証の手順を体系化しているので、単発の`--check`呼び出しを都度組み立てるより先にそちらを確認する方がよい。

## Claude側のコンテキスト消費を抑えたい場合

このスキルはClaude側の**WebSearch呼び出し回数**は節約するが、Gemini側の回答・取得結果はBashの標準出力としてそのままこのセッションのコンテキストに載る（上記「目的」参照）。**Claude側のトークン消費自体を抑えたい**場合は、以下を組み合わせる：

- **`--max-chars`で回答本文を打ち切る**（軽量な対策、単発のfetch向け）。
- **`--no-audit`で文単位の裏付け監査ブロックを省略する。** 事実確認が目的でない一般検索（「◯◯とは」程度）では、出典一覧と同等かそれ以上の行数になりがちなこのブロックが不要なことが多い。数値・固有名詞の正確性を重視する検索では省略しない。
- **`--no-sources`で出典URL一覧を省略する。** 出典を一次資料として記録する予定がない検索では、URLリスト自体が不要な行数を占める。記録・検証目的の検索では省略しない。
- **要約でなく欲しい情報だけを狙ったクエリ・追加指示を書く。** `--max-chars`は生成された回答を後から切り詰めるだけだが、クエリ自体に「一言で」「表形式で数値だけ」のように出力形式を指定すると、Gemini側の生成段階で回答が短くなる（`gemini_webfetch.py`の追加指示についても同様、下記の例を参照）。
- **複数企業・複数URLにまたがる調査、または1件でも重いページ（PDF・長文記事）の要約は、Claudeのサブエージェント（Agent）ではなく `gemini_parallel.py` でGemini CLIエージェントに並列委譲する。** Claudeのサブエージェントは1体ごとにシステムプロンプト・ツール定義・取得ページ本文がClaudeのトークンとして積み上がるため、Web調査では使わない。`gemini_parallel.py` は各調査を独立したGemini CLI（headless・読み取り専用の`--approval-mode plan`）で実行し、検索・ページ取得・要約をすべてGemini側で完結させる。Claude側に載るのは各調査の先頭N文字とファイルパスだけ。

判断の目安: 1〜2件の軽い単発確認は`gemini_websearch.py`＋`--max-chars`＋`--no-audit`＋`--no-sources`＋絞ったクエリ。2件以上の並行調査・重いページの要約・多段の調べもの（検索→取得→再検索）は`gemini_parallel.py`。Claudeのサブエージェントは、Gemini側が両方失敗した場合の最後の手段に限る。

### 並列Web調査（Gemini CLIエージェントに丸ごと委譲）

```bash
cd "C:/Users/iidam/claude-gemini-skills/web-search" && uv run python tools/gemini_parallel.py -o "<scratchpad>/research" "調査1" "調査2" "調査3"
# 調査が多い場合: 1行1調査のファイル（空行・#行は無視）
uv run python tools/gemini_parallel.py -o "<scratchpad>/research" -f queries.txt
```

- 各調査は `<out_dir>/qNN.md` に保存される（stderrは `qNN.stderr.log`）。標準出力は `[qNN] OK/FAIL 秒数 パス` と各回答の先頭 `--preview` 文字（既定400、`0`で非表示）だけ。全文が要る調査だけ後から `qNN.md` を読む。
- 回答中のGoogle転送URL（`vertexaisearch...grounding-api-redirect`）は実URLに自動置換される。解決できなかったものは `(出典URL解決失敗)` になる。
- オプション: `-j`並列数（既定4）、`-m`モデル、`--max-lines`回答の行数上限の指示（既定10）、`--timeout`1調査の秒数上限（既定300）。1件でも失敗すると exit 1。
- **調査内容は具体的に書く**（対象・期間・欲しい項目・出力形式）。プロンプトには「出典にない事実の推測禁止・記載なしは記載なし・完全URL付き・今日の日付」の規律が自動で付く。
- 所要時間は1件30〜60秒程度で、並列数の範囲なら件数が増えてもほぼ同じ。2件以上ならバックグラウンド実行（Bashの`run_in_background`）にして待つ間に他の作業をしてよい。
- **Claude側では検証しない**: ノート等に記録する数値・関係性・実在性の主張だけを、`gemini_webfetch.py "<URL>" --check "<主張>"` で個別に裏取りする（これもGemini側で完結）。

## 判断フロー

1. まずGemini経由（標準の軽量モード）を試す。
2. 取得ステータスが`FAILED`、または回答が空・的外れ・情報不足の場合 → ClaudeネイティブのWebSearch/WebFetchツールで再試行する。
3. Claude側もエラー（証明書エラー、予算上限到達等）になった場合 → Gemini側の結果を「参考情報」として明示した上でユーザーに報告する。両方失敗した場合は素直にその旨を伝える。
4. 出典URLを一次資料としてノート等に記録する場合、`gemini_websearch.py`が自動解決した実URLはそのまま使ってよい。ただし出典表示に`(解決失敗、リダイレクトURLのまま)`と付いている場合は、リダイレクトURLを一次資料として記録せず、Claude側のWebFetch/WebSearchで実URLを確認するか、そのドメイン名（タイトル欄）を手がかりに直接検索する。
5. 検索結果が「AとBに関係がある」「Xという施設・法人格が実在する」といった**関係性・実在性の主張**を含み、それをそのまま重要な事実として扱う場合は、上記オプション機能（`--verify-claim`または`--refute`）での裏取りを検討する（2026-08-02に複数回の誤情報実例あり）。ただし、この裏取りはコストがかかるオプションであり、全ての検索に自動的に適用するものではない——ユーザーが正確性を必要としている文脈かどうかで判断する。

## 留意点

- Geminiの回答はGoogle Search groundingによるものであり、要約段階でのハルシネーションのリスクはClaude側と同程度にある。標準の軽量モードで得た情報を重要な判断・記録に使う場合は、上記オプション機能での検証を検討する。
- Geminiが実際にライブでページを取得したのか、Google側の検索インデックス（キャッシュ）から情報を引いているのかは、`--check`を使わない限り取得ステータスからしか推測できない。更新頻度が高いページの最新性を問う場合は注意する。
- gBizINFO・国税庁法人番号公表サイト等の法人検索は、法人"名"での検索（JS駆動の検索UI）はWebFetch・Gemini `url_context`のいずれでも失敗しやすい。法人番号が判明している場合は `https://info.gbiz.go.jp/hojin/ichiran?hojinBango=<13桁>` の個別URLを直接WebFetchすれば取得できる。法人番号が不明なら、まずGemini websearchで「法人番号 + gBizINFO」を検索しGemini回答内の実URLを抽出してから、この直接アクセスに切り替える。
- `.env`には他のAPIキー（Vertex AI関連、Anthropic、xAI等）も同居しているため、このスキルの実装や出力をログ・ノートに残す際にキーの値そのものを含めないこと。
