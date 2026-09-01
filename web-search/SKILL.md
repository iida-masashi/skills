---
name: web-search
description: Search the web or fetch a specific URL's content. Use whenever the user asks to search/検索して/調べて the web, look something up online, or fetch/取得して the contents of a URL. Defaults to Gemini API (tools/gemini_websearch.py / tools/gemini_webfetch.py in this skill directory), falling back to Claude's native WebSearch/WebFetch tools when Gemini fails or its output is insufficient.
---

# web-search

Web検索・URL取得を行うスキル。**標準ではGemini APIを使い、うまくいかない場合のみClaudeネイティブのWebSearch/WebFetchにフォールバックする。**

## 目的：Claude側のWebSearch回数上限（クォータ）の節約

このスキルの主目的は**Claude側トークンの節約ではなく**、ClaudeネイティブのWebSearchツールが持つ**セッション単位の呼び出し回数上限**を消費しないことにある。頻繁にWeb検索が必要な作業（複数企業の並行調査、繰り返しの再検索等）でClaude側のクォータが枯渇するのを避けるため、既定では別課金・別枠のGemini APIを経由する。

**注意（誤解しやすい点）**: Gemini経由で取得した検索結果・URL本文の要約は、Bashツールの標準出力として通常通りこのセッションのコンテキストに読み込まれる。つまり**Claude側のトークン消費自体はこのスキルを使っても減らない**——減るのはWebSearchツールの呼び出し回数（クォータ）だけである。「トークンを節約したいから」という理由でこのスキルを選ぶのは目的の誤解であり、正しい動機は「WebSearchツールの残り回数を温存したいから」である。

なお、ClaudeのWebFetchは自己署名証明書エラー等で失敗するサイトがあるが、Geminiの`url_context`ツールはGoogle側の取得経路を使うため成功することがある、という副次的なメリットもある。

## 標準の使い方（軽量モード）

以下がこのスキルの**既定の動作**であり、追加フラグなしで実行する場合は速度・トークン量ともに最小限で、精度検証（ハルシネーション対策）は行わない。素朴な情報収集や、厳密な裏取りを必要としない調査にはこれで十分。

このスキルディレクトリ自体が独立したuvプロジェクト（依存は`google-genai`のみ）。初回のみ `cd` して `uv sync` で依存解決する。

両スクリプトはAPIキー/Vertex AI設定を既定で `C:\Users\iidam\gemini\.env` から自動読み込みする（環境変数`GEMINI_SKILL_ENV_PATH`でパスを上書き可能）。

### Web検索（検索クエリを投げて要約と出典を得る）

```bash
cd "C:/Users/iidam/claude-gemini-skills/web-search" && uv run python tools/gemini_websearch.py "検索クエリ"
```

出力: Geminiによる回答本文 + `--- 出典 ---`以下に出典タイトルと解決済み実URL一覧（解決失敗時のみリダイレクトURL）。

- `--json`: 回答・出典を`{text, sources: [{title, url, resolved}]}`のJSONで出力する。後続処理（Agent側での自動反復）に使う場合はこちら。
- `--no-resolve`: 出典URLのリダイレクト解決（`vertexaisearch.cloud.google.com/grounding-api-redirect/...`を実URLへ1回追跡する処理）自体を省略し、さらに軽量化する。実URLが即座に必要ない場合はこちらで速度を優先できる。
- `--max-chars N`: 回答本文をN文字で打ち切って出力する。このスクリプトの標準出力はBashツール経由でそのままClaude側のコンテキストに読み込まれるため、結論だけ分かればよい場面ではこれで流入量を絞れる（出典一覧・`--verify-claim`の判定結果には影響しない）。

### URL取得（特定URLの内容を取得・要約する、WebFetch相当）

```bash
cd "C:/Users/iidam/claude-gemini-skills/web-search" && uv run python tools/gemini_webfetch.py "<URL>" ["追加の指示（省略可、既定は要約）"]
```

出力: Geminiによる回答本文 + `--- 取得ステータス ---`以下に`URL_RETRIEVAL_STATUS_SUCCESS`または`FAILED`と実際に取得できたURL。

- `--max-chars N`: 同上（`--check`使用時は元々短い判定結果しか返らないため影響しない）。

**追加の指示は「要約して」ではなく欲しい情報だけを狙って書く。** Gemini側の回答自体が短くなり、Bash出力＝Claude側のコンテキスト消費が減る。例:

```bash
# 悪い例: 全文要約は本文が長くなりがち
uv run python tools/gemini_webfetch.py "<URL>" "このページの内容を詳しく要約して"

# 良い例: 欲しい数値・事実だけに絞る
uv run python tools/gemini_webfetch.py "<URL>" "このページに記載されている削減時間・対象工場数の数値だけを、原文の表現のまま抜き出して。他の説明は不要"
```

## オプション機能：精度重視モード（明示的に指定したときだけ使う）

以下は**すべてデフォルトでは動かない**追加フラグで、指定すると裏取りのために追加のGemini API呼び出しが発生し、実行時間とコンテキスト消費が増える。「事実として確定させたい」「ノートやレポートに載せる前に検証したい」など、**速度より正確性を優先すべき場面でのみ明示的に使う**（このセッションで実際にハルシネーション実例が複数見つかっており、重要な数値・固有名詞をそのまま採用する前にはこれらの使用を検討する価値がある）。

- **`gemini_websearch.py "クエリ" --verify-claim`**: 回答本文の主張を**否定できない事実の最小単位ごとに箇条書きへ分解**し、各出典ページで裏付けられるかを`gemini_webfetch.py`の`--check`相当のロジックで項目単位に判定する。判定は各出典・各項目ごとに「裏付けあり／裏付けなし／不明」。全出典への問い合わせは並列実行（最大4並列）するため、出典数が増えても待ち時間は概ね1回分で収まる。「関係性がある」「実在する」等の複合的な主張を検証したいときに使う。
- **`gemini_websearch.py "クエリ" --refute`**: クエリを「この主張を否定・反証する情報がないか」という反証志向のプロンプトに自動変換してから検索する。「AとBに関係がある」のような一文の真偽を疑うときに使う。
- **`gemini_webfetch.py "<URL>" --check "<主張>"`**: 要約の代わりに、特定の主張1件がこのURLの内容で裏付けられるかを検証する。主張は項目単位に分解された上で判定される。「この公式サイトに、言われている通りのことが本当に書かれているか」を単発で確認したいときに使う（`--verify-claim`は複数出典を横断する場合向け、こちらは1URL単発の確認向け）。`--check`と自由記述の追加指示は同時指定できない。
  - `--json`併用で`{url, items: [{claim, verdict, detail}], statuses}`を得られる。
  - **取得ステータスがSUCCESS以外の場合、判定結果（裏付けあり/なしを含む）はコード側で自動的に「不明」へ格下げされる**（キャッシュ・検索インデックスから答えてしまうGemini自身のハルシネーション対策。detail欄に格下げ理由が付記される）。

これらのオプション機能を多用するタスク（企業事例の事実確認、既存ノートの数値検証など）では、`solution-research`スキルが調査〜検証の手順を体系化しているので、単発の`--check`呼び出しを都度組み立てるより先にそちらを確認する方がよい。

## Claude側のコンテキスト消費を抑えたい場合

このスキルはClaude側の**WebSearch呼び出し回数**は節約するが、Gemini側の回答・取得結果はBashの標準出力としてそのままこのセッションのコンテキストに載る（上記「目的」参照）。**Claude側のトークン消費自体を抑えたい**場合は、以下を使う：

- **上記の`--max-chars`と、要約でなく欲しい情報だけを狙った追加指示**（軽量な対策、単発のfetch向け）
- **複数企業・複数URLにまたがる調査は、自分で1件ずつBashを叩くのではなくAgent（`subagent_type: "fork"`または`general-purpose`）に委譲する。** サブエージェントに投げたfetch結果・検索結果はサブエージェント側のコンテキストに閉じ、メインセッションにはサブエージェントがまとめた結論だけが返る。3件以上のURL・企業を並行して調べる場合はこちらを優先する（cf. `solution-research`スキルの並列verify-agentパターン）。

判断の目安: 1〜2件の単発確認は`--max-chars`＋絞った追加指示で十分。3件以上の並行調査、または結果を後で全文参照する必要がない調査はAgent委譲に切り替える。

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
