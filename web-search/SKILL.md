---
name: web-search
description: Web検索・URL取得。Gemini API（gemini_websearch.py / gemini_webfetch.py）を既定に、失敗時は Claude の WebSearch/WebFetch へフォールバック。2件以上・多段の調査は gemini_parallel.py で Gemini CLI に並列委譲する。
---

# web-search

Web検索・URL取得を行うスキル。**標準ではGemini APIを使い、うまくいかない場合のみClaudeネイティブのWebSearch/WebFetchにフォールバックする。**

## 目的：Claude側のWebSearch回数上限（クォータ）の節約

このスキルの主目的は**Claude側トークンの節約ではなく**、ClaudeネイティブのWebSearchツールが持つ**セッション単位の呼び出し回数上限**を消費しないことにある。頻繁にWeb検索が必要な作業（複数企業の並行調査、繰り返しの再検索等）でClaude側のクォータが枯渇するのを避けるため、既定では別課金・別枠のGemini APIを経由する。

**注意（誤解しやすい点）**: `gemini_websearch.py`/`gemini_webfetch.py`の出力はBashの標準出力としてそのままこのセッションのコンテキストに読み込まれるため、単発呼び出しではClaude側のトークン消費は出力量の分だけ発生する。**Claude側のトークンを大きく減らすのは`gemini_parallel.py`（Gemini CLIエージェントへの並列委譲）**で、検索結果やページ本文はGemini側で処理され、Claude側には結論の先頭部分だけが載る（下記「Claude側のコンテキスト消費を抑えたい場合」参照）。

なお、ClaudeのWebFetchは自己署名証明書エラー等で失敗するサイトがあるが、Geminiの`url_context`ツールはGoogle側の取得経路を使うため成功することがある、という副次的なメリットもある。

## 標準の使い方（ハルシネーション抑制＋裏付け監査 既定モード）

以下がこのスキルの**既定の動作**です。ハルシネーション（数値捏造・推測補完・時制混同）を減らす方向のガードが既定で適用されますが、**これらはモデルへの指示とコード側の後付き突合であり、独立した事実検証ではありません**。特に「文単位の裏付け監査」は出典への帰属をモデル自身が申告したメタデータの突合に過ぎない点に注意してください。

* **厳格グラウンディング規律**: システムプロンプトで「検索結果／取得ページにない数値・推測補完の厳禁」「記載がない場合は記載なしと回答」「会計年度は必ず決算月付きの『YYYY年M月期』形式に統一（FY25等の単独表記禁止）」「質問文の前提を既定事実とせず一次情報で確認（確認できなければ『前提を確認できず』）」「買収額・財務数値は時点（公表時暫定／完了時確定等）を明記」を指示。`gemini_websearch.py`（Google検索）・`gemini_webfetch.py`（URL取得）の両方に適用。
* **temperature等のサンプリングパラメータは非指定**: Gemini 3.8 / 4 Argon 系では公式にサンプリングパラメータ（`temperature` / `top_p` / `top_k`）が非推奨（Deprecated・無視）となっており、このスキルも両スクリプトとも指定しない。推論の深さは `--thinking-level`、ハルシネーション抑制はグラウンディング規律・裏付け監査側で担う。
* **現在基準日（Anchor Date）注入**: 実行日の日付（例: `2026-11-01`）を注入し、「今期」「最新」等の時制の取り違えを防止（`gemini_websearch.py`のみ）。
* **発行検索クエリの可視化**: Geminiが内部で実際にGoogle検索に投げたクエリ（`web_search_queries`）を表示。**検索クエリが0件・出典が0件の場合は「検索未実行／回答は事前学習知識のみの可能性」の警告を本文の前に表示する**（`gemini_websearch.py`）。
* **文単位の裏付け監査（既定で有効）**: レスポンスの `grounding_supports` を文単位（`。！？`区切り）で突合し、出典への帰属が申告されていない文（モデル自身の推測の疑いがある箇所）を検知して警告。数字を含む文は長さに関わらず必ず監査対象にする。`grounding_supports`自体が空の場合は「監査不能」と表示する（「OK」とは表示しない）。
* **低品質・非一次情報ドメインの自動警告**: 出典URLがSNS・匿名掲示板・個人ブログ・Q&Aサイト・スパム系まとめサイト（`reddit.com`, `note.com`, `ameblo.jp`, `5ch.net`, `*.blog.shinobi.jp`, `warn*.com` 等）である場合、出典一覧に `[WARNING: 低品質・非一次情報ドメイン]`（`gemini_parallel.py`では `[LOW-QUALITY-DOMAIN]`）を自動付与する。
* **取得失敗の明示**: `gemini_webfetch.py`は`URL_RETRIEVAL_STATUS_SUCCESS`以外の場合、要約本文より前に取得ステータスと警告を表示する。
* **高速実URL並列解決**: 302 Location ヘッダーの即時抽出により、巨大PDFや403遮断サイトでも実URLの欠落・タイムアウトなし（最大8並列）。

このスキルディレクトリ自体が独立したuvプロジェクト（依存は`google-genai`および`pydantic`）。初回のみ `uv sync --directory "C:/Users/iidam/claude-gemini-skills/web-search"` で依存解決する。

両スクリプトはAPIキー/Vertex AI設定を既定で `C:\Users\iidam\gemini\.env` から自動読み込みする（環境変数`GEMINI_SKILL_ENV_PATH`でパスを上書き可能）。
- **認証フェイルセーフ**: `GOOGLE_APPLICATION_CREDENTIALS` が存在しないファイルを指している場合は環境変数から自動除外して標準エラー（`stderr`）に警告を出し、`GEMINI_API_KEY` / `GOOGLE_API_KEY` によるAPIキー認証（`vertexai=False`）へ安全にフォールバックする（明示的にVertex AIを優先強制したい場合は `GEMINI_SKILL_FORCE_VERTEX=true` を設定）。

### Web検索（検索クエリを投げて要約・出典・裏付け監査を得る）

```powershell
uv run --project "C:/Users/iidam/claude-gemini-skills/web-search" python "C:/Users/iidam/claude-gemini-skills/web-search/tools/gemini_websearch.py" "検索クエリ"
```

出力: （出典0件の場合は先頭に`[WARNING]`検索未実行警告）+ Geminiによる回答本文 + `--- 検索クエリ ---` + `--- 出典 ---` + `--- 文単位の裏付け監査 (Grounding Audit) ---`（Status: 帰属あり・未検証 / WARNING / 監査不能）。

- `--json`: 回答、出典、発行クエリ、裏付け監査結果をJSON形式で出力する。後続処理（Agent側での自動反復）に使う場合はこちら。
- `--no-audit`: 文単位の裏付け監査表示を省略する（出力をシンプルにしたい場合や極限まで軽量化したい場合）。
- `--model MODEL`: 使用するGeminiモデルを指定する（既定は `gemini-3.8-flash`。最上位フラッグシップの `gemini-4-argon` や軽量な `gemini-3.5-flash-lite` 等に切り替え可能）。
- `--thinking-level {minimal,low,medium,high}`: 思考プロセス（Thinking）の深さを指定する（既定はモデル既定値。`gemini-3.8-flash` / `gemini-4-argon` は既定でMEDIUM）。複雑な論理・数値突合の精度を上げたい場合は`high`を指定する。なお、`minimal` は `gemini-3.5-flash-lite` 向けであり、`gemini-3.8-flash` や `gemini-4-argon` で指定した場合は自動的に `low` へフォールバックする。
- `--no-resolve`: 出典URLのリダイレクト解決（実URLへの逆引き）自体を省略し、さらに軽量化する。
- `--no-sources`: 出典URL一覧（`--- 出典 ---`ブロック）の表示を省略し、件数だけ表示する。一次資料として記録する予定がない一般検索（「◯◯とは」程度の確認）で有効。`--verify-claim`併用時の出典URL内訳表示には影響しない（そちらは検証目的でURLが必要なため）。
- `--max-chars N`: 回答本文をN文字で打ち切って出力する。このスクリプトの標準出力はBash/PowerShellツール経由でそのままClaude側のコンテキストに読み込まれるため、結論だけ分かればよい場面ではこれで流入量を絞れる（出典一覧・判定結果には影響しない）。

### URL取得（特定URLの内容を取得・要約する、WebFetch相当）

```powershell
uv run --project "C:/Users/iidam/claude-gemini-skills/web-search" python "C:/Users/iidam/claude-gemini-skills/web-search/tools/gemini_webfetch.py" "<URL>" ["追加の指示（省略可、既定は要約）"]
```

出力: `--- 取得ステータス ---`（`URL_RETRIEVAL_STATUS_SUCCESS`または`FAILED`等と実際に取得できたURL。取得情報が無い場合もその旨を表示）+ SUCCESS以外の場合は`[WARNING]`取得失敗警告 + Geminiによる回答本文。なお、GoogleのリダイレクトURL（`vertexaisearch...`）が渡された場合も自動で実URLへ逆引き解決してから取得します。

- `--json`: 取得結果を `{url, text, statuses, fetch_ok, fetch_ng_reason}` のJSON形式で出力する。
- `--max-chars N`: 同上（`--check`使用時は元々短い判定結果しか返らないため影響しない）。

**追加の指示は「要約して」ではなく欲しい情報だけを狙って書く。** Gemini側の回答自体が短くなり、標準出力＝Claude側のコンテキスト消費が減る。例:

```powershell
# 悪い例: 全文要約は本文が長くなりがち
uv run --project "C:/Users/iidam/claude-gemini-skills/web-search" python "C:/Users/iidam/claude-gemini-skills/web-search/tools/gemini_webfetch.py" "<URL>" "このページの内容を詳しく要約して"

# 良い例: 欲しい数値・事実だけに絞る
uv run --project "C:/Users/iidam/claude-gemini-skills/web-search" python "C:/Users/iidam/claude-gemini-skills/web-search/tools/gemini_webfetch.py" "<URL>" "このページに記載されている削減時間・対象工場数の数値だけを、原文の表現のまま抜き出して。他の説明は不要"
```

## オプション機能：さらに厳密な検証モード（明示的に指定したときだけ使う）

上記「標準の裏付け監査（Grounding Audit）」はAPIレスポンスのメタデータのみを用いて追加通信なしで検証しますが、以下は**追加のGemini API呼び出しを発生させてより強固に裏取りする機能**です。

- **`gemini_websearch.py "クエリ" --verify-claim`**: 回答本文中でgrounding済み（出典への帰属が申告済み）の文をclaim単位とし、その出典URLごとに1回だけ問い合わせて裏付けを検証する（同じURLに複数claimが帰属している場合もまとめて1回で判定）。判定は構造化出力（JSON Schema）で強制し、「裏付けあり」の場合は原文からの引用（quote）を必須にする（空文字や「なし」「N/A」等のプレースホルダは自動格下げ）。claim単位の最終判定は「1出典でも裏付けあり（quote付き）→裏付けあり／全出典が裏付けなし→裏付けなし／それ以外→不明」に集約する。出典URLへの問い合わせは並列実行（最大4並列）。`grounding_supports`が空（出典への帰属が一切申告されていない）の場合はスキップされ、その旨が表示される。
- **`gemini_websearch.py "クエリ" --refute`**: クエリを「この主張を否定・反証する情報がないか」という反証志向のプロンプトに自動変換してから検索する。「AとBに関係がある」のような一文の真偽を疑うときに使う。
- **`gemini_webfetch.py "<URL>" --check "<主張>"`**: 要約の代わりに、特定の主張1件がこのURLの内容で裏付けられるかを検証する。判定は構造化出力（JSON Schema）で行い、「裏付けあり」の場合は原文引用（quote）を必須にする（quoteが空またはプレースホルダなら自動的に「不明」へ格下げ）。
  - `--json`併用で`{url, items: [{claim, verdict, quote, detail}], statuses, fetch_ok}`を得られる。
  - **取得ステータスがSUCCESSでも、実際に取得できたページの登録ドメイン（組織ドメイン）が要求したURLのドメインと異なる場合は「不明」へ格下げされる**（ログイン壁・別サイトへのリダイレクト等、「何かは取れたが求めたページではない」ケースの対策。同一組織のサブドメイン間リダイレクトや未解決の`grounding-api-redirect`経由は許容）。

これらのオプション機能を多用するタスク（企業事例の事実確認、既存ノートの数値検証など）では、`solution-research`スキルが調査〜検証の手順を体系化しているので、単発の`--check`呼び出しを都度組み立てるより先にそちらを確認する方がよい。

## Claude側のコンテキスト消費を抑えたい場合

このスキルはClaude側の**WebSearch呼び出し回数**は節約するが、Gemini側の回答・取得結果は標準出力としてそのままこのセッションのコンテキストに載る（上記「目的」参照）。**Claude側のトークン消費自体を抑えたい**場合は、以下を組み合わせる：

- **`--max-chars`で回答本文を打ち切る**（軽量な対策、単発のfetch向け）。
- **`--no-audit`で文単位の裏付け監査ブロックを省略する。** 事実確認が目的でない一般検索（「◯◯とは」程度）では、出典一覧と同等かそれ以上の行数になりがちなこのブロックが不要なことが多い。数値・固有名詞の正確性を重視する検索では省略しない。
- **`--no-sources`で出典URL一覧を省略する。** 出典を一次資料として記録する予定がない検索では、URLリスト自体が不要な行数を占める。記録・検証目的の検索では省略しない。
- **要約でなく欲しい情報だけを狙ったクエリ・追加指示を書く。** `--max-chars`は生成された回答を後から切り詰めるだけだが、クエリ自体に「一言で」「表形式で数値だけ」のように出力形式を指定すると、Gemini側の生成段階で回答が短くなる（`gemini_webfetch.py`の追加指示についても同様、上記の例を参照）。
- **複数企業・複数URLにまたがる調査、または1件でも重いページ（PDF・長文記事）の要約は、Claudeのサブエージェント（Agent）ではなく `gemini_parallel.py` でGemini CLIエージェントに並列委譲する。** Claudeのサブエージェントは1体ごとにシステムプロンプト・ツール定義・取得ページ本文がClaudeのトークンとして積み上がるため、Web調査では使わない。`gemini_parallel.py` は各調査を独立したGemini CLI（headless・読み取り専用の`--approval-mode plan`）で実行し、検索・ページ取得・要約をすべてGemini側で完結させる。Claude側に載るのは各調査の先頭N文字とファイルパスだけ。

判断の目安: 1〜2件の軽い単発確認は`gemini_websearch.py`＋`--max-chars`＋`--no-audit`＋`--no-sources`＋絞ったクエリ。2件以上の並行調査・重いページの要約・多段の調べもの（検索→取得→再検索）は`gemini_parallel.py`。Claudeのサブエージェントは、Gemini側が両方失敗した場合の最後の手段に限る。

### 並列Web調査（Gemini CLIエージェントに丸ごと委譲）

```powershell
uv run --project "C:/Users/iidam/claude-gemini-skills/web-search" python "C:/Users/iidam/claude-gemini-skills/web-search/tools/gemini_parallel.py" -o "<scratchpad>/research" "調査1" "調査2" "調査3"
# 調査が多い場合: 1行1調査のファイル（空行・#行は無視）
uv run --project "C:/Users/iidam/claude-gemini-skills/web-search" python "C:/Users/iidam/claude-gemini-skills/web-search/tools/gemini_parallel.py" -o "<scratchpad>/research" -f queries.txt
```

- **パス指定（`--project` 推奨）**: `uv run --project "C:/Users/iidam/claude-gemini-skills/web-search"` を使うことで呼び出し元のカレントディレクトリ（cwd）が維持されるため、`-f` や `-o` に相対パスをそのまま渡せる（`uv run --directory` を使う場合は cwd が移動するため絶対パス指定が必須）。
- 各調査は `<out_dir>/qNN.md` にYAMLフロントマター（`query`, `timestamp`, `model`, `status`, `elapsed_sec`, `dead_links`, `unreachable_links`, `low_quality_links`, `unverified_lines`, `unsupported_lines`, `conclusion_unverified`, `stripped_reasoning_lines`, `quote_mismatch`, `no_quote`, `off_topic_links`）および先頭のサマリバナー（`> [検証サマリ] URL n件 / 生存 a / 404 b / 確認不能 c / 低品質 d / 未検証行 e / 引用不一致 f / 裏付けなし m`、および結論未確認時の2種類の警告バナー：生存URL不足時は `> [警告] 根拠となる生存URLが不足しています。結論は一次資料で未確認として扱ってください。`、引用不一致・両方該当時は `> [警告] 根拠行の多くで、URLが死んでいるか、引用がページに存在しません。結論は一次資料で未確認として扱ってください。`）付きで保存される（stderrは `qNN.stderr.log`）。標準出力は `[qNN] OK/FAIL 秒数 パス`（死んだURLや未検証行がある場合は `[WARN] dead=X unverified=Y`、結論未確認時は `⚠ conclusion-unverified`、引用不一致が1件以上ある場合は `quote-mismatch=n` を付記）と各回答の先頭 `--preview` 文字（既定400、`0`で非表示）だけ。全文が要る調査だけ後から `qNN.md` を読む。
- Gemini CLIが回答先頭に出力することがある内部思考ログ（`💡thought` / `Thought:` / `thinking` ブロックや `CRITICAL INSTRUCTION` / `I will use` 等のメタ独白行）は自動で除去され、除去行数がフロントマターの `stripped_reasoning_lines` に記録される（除去後に空になる場合は安全のため元のテキストを保持し `status: OK(empty-after-strip)` とする）。
- 回答中のGoogle転送URL（`vertexaisearch...grounding-api-redirect`、末尾の `=` パディング含む）は実URLに自動置換される。解決できなかったものは `(出典URL解決失敗)` になる。さらに本文中の生URL（日本語パスを含むURLも自動パーセントエンコードして検査し、表示は可読な日本語のまま保持。助詞密着時は助詞除去URLへ自動フォールバック）に対してもHTTP疎通チェック・SSRF検査・低品質ドメイン判定を行い、404/410には `[DEAD-LINK: 404]`、401/403/429や到達不能には `[UNCHECKED: 403|UNREACHABLE]`、プライベートIPや非http(s)スキームには `[UNCHECKED: BLOCKED]`、SNS・個人ブログ等には `[LOW-QUALITY-DOMAIN]` を付与する（Markdownリンク `[text](url)` の場合は `)` の直後にタグを配置しリンク構文を壊さない）。
- **死んだURLのみの行・裏付けなし行・結論行の自動格下げ**: 箇条書き行または `|` 区切り・Markdown表の事実行に含まれる出典URLがすべて `[DEAD-LINK: 404|410]` の場合、その行の先頭（Markdown表の行は第1セル先頭 `| [UNVERIFIED] ... |`）に自動で `[UNVERIFIED]` を付与する。事実行のうち `[UNVERIFIED]` / `[QUOTE-MISMATCH]` / `[NO-QUOTE]` のいずれかが付いた行を `unsupported_lines`（裏付けなし行、行単位でカウントし `[UNCHECKED: ...]` は対象外）として集計し、①生存・確認不能URLが0件、または②事実行がすべて裏付けなし（`unsupported_lines == fact_lines_with_urls`）の場合は結論行に `[CONCLUSION-UNVERIFIED]` を、③事実行の50%以上が裏付けなし（`unsupported_lines / fact_lines_with_urls >= 0.5`）の場合は `[CONCLUSION-LOW-CONFIDENCE]` を自動付与する。
- オプション: `-j`並列数（既定4）、`-m`モデル、`--max-lines`回答の行数上限の指示（既定10）、`--timeout`1調査の秒数上限（既定300）、`--no-unchecked-tags`（`[UNCHECKED: ...]` タグの抑止）、`--verify-quotes`（生存HTMLページの本文を取得し、各URL列 `i` の直後にある `i+1` 列目の原文引用をNFKC正規化部分一致で突合。不一致に `[QUOTE-MISMATCH]`・空引用に `[NO-QUOTE]` を付与。Shift_JIS / EUC-JP 等の日本語文字コード自動判定対応。PDFは `[UNCHECKED: PDF]`、非HTMLは `[UNCHECKED: TYPE]`、2MB超の巨大ページは `[UNCHECKED: TRUNCATED]`）、`--subject "固有名詞"`（複数指定可。URL・タイトル・本文に主題が含まれない出典に `[OFF-TOPIC]` を付与）。1件でも失敗すると exit 1。
- **調査内容は具体的に書く**（対象・期間・欲しい項目・出力形式）。プロンプトには「事実 | 完全URL | 原文引用（60字以内）」「存在しないURLの推測生成禁止」「会計年度はYYYY年M月期」「前提の一次情報確認・数値の時点明記」の規律が自動で付く。
- 所要時間は1件30〜60秒程度で、並列数の範囲なら件数が増えてもほぼ同じ。2件以上ならバックグラウンド実行（Bashの`run_in_background`）にして待つ間に他の作業をしてよい。
- **Claude側では検証しない**: ノート等に記録する数値・関係性・実在性の主張だけを、`gemini_webfetch.py "<URL>" --check "<主張>"` で個別に裏取りする（これもGemini側で完結）。
- **財務数値・ROIC・会計指標の一次資料原則（C10）**: 決算数値・ROIC・買収額・セグメント利益等の厳密な財務数値を確定させる際は、Web検索の要約テキストをそのまま正とせず、**Web検索は一次資料（有価証券報告書・決算短信・統合報告書・適時開示PDF）のURL特定のみに使い、特定したPDFをローカルに取得して `convmd` 等でMarkdown変換・直接読解して確定させること**。

## 運用ルール（CP グループ調査での実測に基づく）

並列調査（`gemini_parallel.py`）の結果を、そのまま事実として使わない。2026-11-01 の企業調査では、要約の数値が一次資料と食い違った（純利益・有利子負債）、出典に挙げられたページに主張が載っていなかった（検証サマリは「裏付けなし 0」と表示していた）、別グループの記述が混ざった、といった例があった。検証サマリはモデルの自己申告に基づくもので、独立した検証ではない。

1. **Gemini は URL を探す役にする。** 依頼文は「事実 | 完全URL | 原文引用(60字以内)」の形式に限り、結論の文章は使わない。
2. **`--verify-quotes` は既定で有効。** 引用が出典ページに実在するか検証し、不一致は `[QUOTE-MISMATCH]`、引用なしは `[NO-QUOTE]` と表示される。無効にするときだけ `--no-verify-quotes`。PDF・403・巨大ページは `[UNCHECKED: …]` になり、検証されていない扱い。
3. **ノートに入れる事実は一次資料で確認する。** URL を `convmd` で保存して原文を見る（Vault の場合は `rules/02_content_integrity.md`）。取得できなければ `gemini_webfetch.py "<URL>" --check "<主張>"` で個別に裏取りし、「不明」「裏付けなし」は採用しない。
4. **一次資料の URL が分かっているときは Gemini を介さない。** IR ページなどは `convmd` で直接取得する方が確実で安い。
5. **同じ質問の再実行で答えが変わる事項（役員体制など）は、一次資料が取れるまで採用しない。**
6. **出力量に注意。** 単発検索では `--max-chars`・`--no-sources`・`--no-audit` を付ける。出典 URL（Google 転送 URL）が長く、標準出力がそのままコンテキストに入る。

## ソフトウェア開発タスクでの使い分け（依存更新・ライブラリ調査など）

Geminiに任せて得をするのは**Web調査の部分だけ**。実装・検証・最終確認はClaudeが直接行う。

| 作業 | 担当 | 理由 |
|---|---|---|
| リリースノート・移行ガイド・changelogの読み込み（破壊的変更の洗い出し） | Gemini（`gemini_parallel.py`） | 長文の読み込みをGemini側で完結でき、Claude側の検索回数とコンテキストを節約できる |
| 更新を見送った依存の上流状況の定期チェック（例: peer依存の上限、上限ピンの解除待ちissue） | Gemini（`gemini_parallel.py`で一括） | 複数パッケージを並列に調べられる。ただし結果は下段で確定させる |
| issue/PRのopen・closed、最新リリース版、peer依存の範囲など**判断の根拠になる事実**の確定 | Claude（`gh` CLI、`npm view`、`uv`/PyPIの実出力） | Geminiの回答にはキャッシュ由来の古い情報やハルシネーションが混ざりうる。一次ソースを直接見る |
| コード修正（API置き換え・テスト修正など） | Claude | 小規模（目安50行未満）なら指示・レビューの手間の方が大きい。大量・機械的でテストで確かめられる作業のみ agy への委譲を検討 |
| テスト反復実行・E2E・本番確認などの検証 | Claude（シェルコマンド） | コマンドの実行と結果判定だけで、LLMを挟む余地がない。DB分離などの前提を崩す事故のもとになる |

推奨フロー: ①「何が古いか・破壊的変更は何か」をGeminiに並列調査させる → ②結論を`gh`・`npm`/`uv`の実出力で確定する → ③実装と検証はClaudeが行う。

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
