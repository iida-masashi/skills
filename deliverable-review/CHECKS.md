# Checks Catalog — deliverable-review

10 チェッカー × 全カテゴリ × Severity 判定ルールのリファレンス。
実装は `scripts/*.py` を参照。戦略コンサル品質ルール（checker=`strategy`、CLI/Web UI とも既定ON、`--no-strategy` で無効化）は `scripts/strategy_checks.py` と SKILL.md を参照。

**「場所」の単位**: pptx=スライド、pdf=ページ、docx=見出し（Heading/見出し スタイル）で区切ったセクション。見出しが無い docx は 10 段落ごとのブロック。出典判定・単位混在・敬体/常体混在などの「場所ごと」チェックはこの単位で行う。

**リンク先URL**: 表示文字の裏にあるハイパーリンク先（pptx の run/図形リンク、docx のハイパーリンク、pdf のリンク注釈）も URL汚染・URL死活の対象。

## 目次

1. [メタデータ](#1-メタデータ-metadata)
2. [内部コンテンツ](#2-内部コンテンツ-internal-content)
3. [URL汚染](#3-url汚染-url-contamination)
4. [AI生成痕跡](#4-ai生成痕跡-ai-trace)
5. [数値整合性](#5-数値整合性-numeric-integrity)
6. [コンサル作法(文体)](#6-コンサル作法文体-consulting-style)
7. [コンサル作法(体裁)](#7-コンサル作法体裁-consulting-layout)
8. [著作権リスク](#8-著作権リスク-copyright)
9. [URL死活](#9-url死活-url-liveness)
10. [検証要主張](#10-検証要主張-verifiable-claim)

---

## 1. メタデータ (metadata)

**実装**: `scripts/metadata.py`

### 検出カテゴリ

| カテゴリ | Severity | 対象 | 発火条件 |
|---|:---:|---|---|
| `core-author` | HIGH | pptx/docx | core properties の author が非空 |
| `core-last_modified_by` | HIGH | pptx/docx | 同 last_modified_by が非空 |
| `core-comments` | HIGH | pptx/docx | 同 comments が非空 |
| `core-keywords` | MEDIUM | pptx/docx | 同 keywords が非空 |
| `core-category` | MEDIUM | pptx/docx | 同 category が非空 |
| `core-subject` | MEDIUM | pptx/docx | 同 subject が非空 |
| `core-title` | MEDIUM | pptx/docx | 同 title が非空 |
| `app-company` | HIGH | pptx/docx | `docProps/app.xml` の Company が非空 |
| `app-manager` / `app-hyperlinkbase` | MEDIUM | pptx/docx | 同 Manager / HyperlinkBase が非空 |
| `custom-properties` | MEDIUM | pptx/docx | `docProps/custom.xml` にユーザー設定プロパティ（秘密度ラベル `MSIP_Label_*` 以外）がある |
| `docx-comments` | HIGH | docx | `word/comments.xml` が存在 |
| `docx-tracked-changes` | HIGH | docx | 本文/ヘッダ/フッタ/脚注に `<w:ins>` `<w:del>` `<w:moveFrom>` `<w:moveTo>` `<w:rPrChange>` `<w:pPrChange>` |

非表示スライドは内部コンテンツ (`internal-content/hidden-slide`) で1回だけ報告する。
| `pdf-author` / `pdf-lastmodifiedby` / `pdf-company` | HIGH | pdf | PDF /Info の該当フィールド非空 |
| `pdf-creator` / `pdf-producer` / `pdf-title` / `pdf-subject` / `pdf-keywords` | MEDIUM | pdf | 同上、識別性は低いが漏洩源 |

### サニタイズ動作 (`--sanitize`)

- **自動削除**: core properties全て、`docProps/app.xml` の Company/Manager/HyperlinkBase（TotalTime/Revision は 0 に）、`docProps/custom.xml` のユーザー設定プロパティ（`MSIP_Label_*` 秘密度ラベルは保持）、Word の `comments*.xml`/`people.xml`、PowerPoint のコメント（旧形式 `comments/commentN.xml`・新形式 `modernComment_*.xml`・作成者一覧）、PDF /Info と /Metadata (XMP)
- **変更履歴の受け入れ（docx）**: 本文・ヘッダ・フッタ・脚注/文末脚注で `<w:ins>`/`<w:moveTo>` は中身を残して外す、`<w:del>`/`<w:moveFrom>` は中身ごと削除、書式変更履歴（`*PrChange`）は削除。段落記号の削除マーカー（`<w:rPr><w:del/>`）はマーカーのみ削除（段落の結合はしない）、削除行（`<w:trPr><w:del/>`）は行ごと削除
- 削除したパーツを指す relationship と `[Content_Types].xml` の Override も除去する。XML は lxml で編集（正規表現置換はしない）
- **事後検証**: 出力ファイルを再オープンして再検出し、残存があれば `verify: 残存あり → ...` を出す。開けなければエラー終了
- **検出のみ（残す）**: 非表示スライド、スピーカーノート — 意図的に残している可能性があるため

---

## 2. 内部コンテンツ (internal-content)

**実装**: `scripts/internal_content.py`

### 検出カテゴリ

| カテゴリ | 通常 Severity | 要注意ワード含有時 | 危険ワード含有時 | 対象 |
|---|:---:|:---:|:---:|---|
| `speaker-note` | INFO | MEDIUM | **HIGH** | pptx |
| `hidden-slide` | HIGH | HIGH | HIGH | pptx |
| `pptx-comment` | MEDIUM | MEDIUM | **HIGH** | pptx（旧形式・新形式。スライドとの対応はスライドの relationship で解決） |
| `docx-comment` | MEDIUM | MEDIUM | **HIGH** | docx |

### 危険ワード（HIGH昇格、`_DANGER_PATTERNS`）

- **秘匿系**: 「クライアント/顧客/先方/お客様に(は)?(言わない/伝えない/見せない/触れない/共有しない)」「オフレコ」「伏せる」「内輪」「社内/内部(限り/のみ/用/向け/マター)」
- **作業メモ**: `TODO` / `FIXME` / `XXX`
- **機密英語**: `confidential` / `internal only` / `do not share`
- **競合**: 「competitor」「ライバル」「他社/競合...の話/には」

### 要注意ワード（MEDIUM、`_CAUTION_PATTERNS`）

ノートに普通に書かれうる語。「仮説」「仮想」等の一般語を拾わないよう「仮」単独は対象外。

- **作業状態**: 「暫定」「未確定」「検討中」「要確認」「確認中」「仮置き」「仮値」「仮の数字/数値/値」、`NOTE:` / `internal` / `draft`
- **数字の裏事情**: 「値引き」「ディスカウント」「赤字」「原価」「利益率」「マージン」「採算」
- **スルー指示**: 「スルー」「スキップ」

---

## 3. URL汚染 (url-contamination)

**実装**: `scripts/patterns.py` → `checkers.check_url_contamination`

### 検出カテゴリ

| カテゴリ | Severity | パターン例 |
|---|:---:|---|
| `AI-origin-query-param` | HIGH | `?utm_source=chatgpt.com`, `&utm_medium=claude`, `ref=perplexity` 等 |
| `AI-tool-conversation-url` | HIGH | `chat.openai.com/*`, `chatgpt.com/c/*`, `claude.ai/chat/*`, `gemini.google.com/app/*`, `perplexity.ai/search/*`, `copilot.microsoft.com/*`, `poe.com/s/*` |
| `general-tracking-param` | MEDIUM | `fbclid=`, `gclid=`, `msclkid=`, `yclid=`, `_ga=`, `_gl=`, `mc_cid=`, `mc_eid=`, `igshid=`, `hsa_*`, `vero_id=`, `s_cid=` |

### 対象AIツール (AI-origin の検出対象)

ChatGPT/OpenAI, Claude/Anthropic, Perplexity, Gemini/Bard, Copilot/BingChat, Grok, You.com, Phind, Poe, Kimi, Deepseek, Mistral

---

## 4. AI生成痕跡 (ai-trace)

**実装**: `scripts/patterns.py` → `find_ai_traces`

### 検出カテゴリ

| カテゴリ | Severity | 例 |
|---|:---:|---|
| `AI-phrase-ja` | HIGH | 「申し訳ございませんが、AIとして」「AIアシスタントとして」「言語モデルとして」「ご質問ありがとうございます」「以下に〜を示します」「要点をまとめると」「総括すると」「結論/まとめとして」 |
| `AI-phrase-en` | HIGH | `As an AI`, `As a language model`, `I'm an AI`, `I apologize, but`, `I cannot (provide/generate/assist)`, `I don't have (access to/the ability)`, `Certainly!`, `I'd be happy to`, `Here's a (brief/detailed/comprehensive)` |
| `knowledge-cutoff-mention` | MEDIUM | 「2023年4月時点の知識」「私の知識は2023」`as of my last update`, `knowledge cutoff`, `my training data`, `up to March 2024`（「2024年3月時点の売上」のような業務表現は対象外） |
| `markdown-remnant` | LOW | `**bold**`, `` `code` ``, `# heading`, `[text](url)` |
| `markdown-remnant-bullets` | LOW | 同一テキストユニット内に **2行以上** のバレット行 `- X` / `1. X` （単独は誤検知を避けるため除外） |
| `excessive-emoji` | MEDIUM | 1ユニット内に絵文字3個以上 |

### 誤検知対策

- バレット（`- X`）の単独行は除外（PowerPoint のネイティブ箇条書きが「- 」プレフィックスとして露出する場合があるため）
- 段落全体で判定、同一段落内に2行以上ある場合のみフラグ

---

## 5. 数値整合性 (numeric-integrity)

**実装**: `scripts/numeric_integrity.py`

### 検出カテゴリ

| カテゴリ | Severity | 対象 | 発火条件 |
|---|:---:|---|---|
| `pie-sum-not-100` | HIGH | pptx (native chart) | PIE系チャートの値合計が 100±1 にも 1.0±0.01 にもならない |
| `stacked100-sum-not-100` | HIGH | pptx (native chart) | 100% 積上げ系のカテゴリ合計が 100±1 または 1±0.01 から外れる |
| `table-row-total-mismatch` | HIGH | pptx/docx/pdf | 見出し行に「合計/Total」列があり、その値が同じ行の他の数値列の合計と一致しない（構成比・%・YoY 等の比率列は除外）。許容誤差: max(0.5, 0.5%) |
| `table-col-total-mismatch` | HIGH | pptx/docx/pdf | 「合計/Total」行が、上の小計行＋小計に含まれないデータ行の合計と不一致（小計を二重計上しない） |
| `table-subtotal-mismatch` | HIGH | pptx/docx/pdf | 「小計」行が、直前の小計以降のデータ行の合計と不一致 |

表の判定ルール: 1行目は見出し、1列目は行ラベルとして**合算しない**（「2023年」等の年度見出しの混入防止）。合計/小計ラベルはセル全体で判定（「計画策定」「会計」等を合計行と誤認しない）。`▲120` `△120` `−120` `(120)` は負数、全角数字は半角として読む。
| `currency-unit-mixing` | MEDIUM | 全形式 | 同一スライド/ページ内に金額単位2種以上（兆円/億円/百万円/万円/千円/円） |
| `percent-pp-mixing` | MEDIUM | 全形式 | 同一スライド/ページ内に % と pp/ポイント が両方出現 |
| `chart-read-error` | INFO | pptx | python-pptx でチャートデータ読み取り失敗（画像化チャート等） |

---

## 6. コンサル作法(文体) (consulting-style)

**実装**: `scripts/style_checks.py`

### 検出カテゴリ

| カテゴリ | Severity | 発火条件 |
|---|:---:|---|
| `title-noun-ending` | LOW | スライドタイトルが体言止め、かつ除外キーワード（目次/アジェンダ/会社概要/経歴/はじめに/まとめ/Appendix/参考/表紙/ご提案書等）を含まない |
| `term-inconsistency/*` | MEDIUM | 定義された同義語グループ内に2種類以上の表記がファイル内で出現 |
| `term-inconsistency/digit-width` | LOW | 全角数字≧3件 かつ 半角数字≧1件 |
| `term-inconsistency/alpha-width` | LOW | 全角英字≧3件 かつ 半角英字≧1件 |
| `prohibited/keihyo-risk` | MEDIUM | 景表法リスク表現ヒット（後述） |
| `prohibited/vague-overuse` | INFO | 同一スライドに曖昧表現が3件以上 |
| `honorific-plain-mixing` | LOW | 同一スライド内に敬体（〜です/ます）と常体（〜だ/である）が両方出現 |
| `date-format-mixing` | LOW | ファイル内で2種類以上の日付書式が共存 |

### 表記ゆれ検出グループ

| グループ | 変種 |
|---|---|
| `country-us` | 米国 / アメリカ / USA / U.S. |
| `country-uk` | 英国 / イギリス / UK / U.K. |
| `customer` | 顧客 / クライアント / お客様 / お客さま |
| `your-company` | 御社 / 貴社 |
| `our-company` | 当社 / 弊社 / 当方 |
| `server` | サーバー / サーバ |
| `memory` | メモリー / メモリ |
| `user` | ユーザー / ユーザ |
| `computer` | コンピューター / コンピュータ |
| `interface` | インターフェース / インタフェース / インターフェイス |
| `data` | データー / データ |

### 景表法リスク表現

- `No.1` / 業界No.1 / ナンバーワン / トップ
- 世界一・最高・最大・最良・最強・最先端・唯一（世界/日本/国内/業界 接頭辞付き）
- 「絶対/100%確実/安全/成功/保証」
- 「必ず成功/達成/実現/保証/なる」
- 「他社/競合にはない/を圧倒/を凌駕」

### 曖昧表現（3件以上でフラグ）

- 「と思われる」「と考えられる」「のようだ」「かもしれない」
- 「おそらく」「たぶん」「多分」
- 「〜など」「〜等」「〜的な」「〜的に」
- 「様々な」「いろいろな」

### 日付書式

slash-ymd (`2024/3/13`) / hyphen-ymd (`2024-3-13`) / ja-ymd (`2024年3月13日`) / reiwa-ymd (`令和6年3月13日`) / us-mdy (`3/13/2024`) / eng-full (`March 13, 2024`)

---

## 7. コンサル作法(体裁) (consulting-layout)

**実装**: `scripts/layout_checks.py`

### 検出カテゴリ

| カテゴリ | Severity | 発火条件 |
|---|:---:|---|
| `missing-title` | LOW | 表紙(Slide 1)と Section/Cover/Title 系レイアウト以外でタイトルが空 |
| `missing-page-number` | LOW | ファイル内にページ番号付きスライドが存在するが、一部スライド（Slide 2以降）に欠落 |
| `too-many-fonts-slide` | MEDIUM | 1スライド内で **3種類以上** のフォントを使用（テーマ既定 `+mj-lt` 等は除く） |
| `too-many-fonts-file` | LOW | ファイル全体で **5種類以上** のフォント |
| `tiny-font-8pt` | MEDIUM | 8pt未満のテキストが存在（印刷・表示で読めない） |
| `tiny-font-10pt` | LOW | 10pt未満のテキストが存在（可読性警告） |

### ページ番号検出ヒューリスティクス

スライド下端 25% 以内にあり、テキストが `\d+` / `\d+/\d+` / `p.\d+` / `page \d+` にマッチするテキストボックス。

---

## 8. 著作権リスク (copyright)

**実装**: `scripts/checkers.py` → `check_copyright`

### 検出カテゴリ

| カテゴリ | Severity | 発火条件 |
|---|:---:|---|
| `long-text-without-citation` | MEDIUM | スライド/ページ内のテキスト合計が100文字以上、かつ出典マーカー（下記）を一切含まない |
| `image-without-citation` | MEDIUM | スライド/ページに画像あり、かつ出典マーカーなし |
| `table-without-citation` | LOW | スライド/ページに表あり、かつ出典マーカーなし |

### 出典マーカー（正規表現）

- 日本語: 出典 / 出所 / 参考(文献/資料/URL)? / 引用(元)? / 参照 / ソース / 典拠 / 根拠
- 英語: Source(s)? / Reference(s)? / Citation(s)? / See / Ref. / via
- あるいは任意の `http(s)://...` URL
- ©・Copyright 等の著作権表示は出典扱い**しない**（自社テンプレートのフッターに常在し、全スライドの判定を素通りさせるため）

---

## 9. URL死活 (url-liveness)

**実装**: `scripts/checkers.py` → `check_url_liveness`

### 動作

1. 全テキストとハイパーリンク先から URL を抽出（空白・引用符・半角/全角の括弧類・句読点で区切る。`（出典: https://…）` の `）` は含めない）
2. User-Agent `Mozilla/5.0 deliverable-review` で **HEAD** リクエスト（タイムアウト5秒）
3. 4xx/5xx なら **GET** でリトライ（stream=True, 即 close）
4. 並列10スレッド

### 検出カテゴリ

| カテゴリ | Severity | 条件 |
|---|:---:|---|
| `unreachable` | HIGH | DNS失敗/接続タイムアウト/SSLエラー等（`requests.RequestException`） |
| `http-404` / `http-410` | HIGH | 存在しないリソース |
| `http-4XX` / `http-5XX` (上記以外) | MEDIUM | アクセス制限/一時エラー等（Bot対策の403誤検知に注意） |

---

## 10. 検証要主張 (verifiable-claim)

**実装**: `scripts/patterns.py` → `extract_verifiable_claims`

出典記載のない箇所からのみ抽出（出典記載のあるスライド/ページ/docxセクションはスキップ）。

### 検出カテゴリ

| カテゴリ | パターン例 |
|---|---|
| `number` | `15%`, `年率15%`, `3.5倍`, `5pt/5bps`, `1,000,000円`, `3.5兆円`, `95百万円`, `CAGR 12.3%`, `$3 billion` |
| `date` | `2024年3月13日`, `2024/3/13`, `2024年度`, `March 13, 2024`, `Q3 2024`, `第3四半期` |
| `ranking-or-stat` | `世界第2位`, `国内N位`, `シェア25%`, `売上高 3億円`, `時価総額 1兆円`, `従業員数 500人`, `top 10`（具体的な数値を伴う場合のみ） |

### Severity

全て INFO（人間による裏取り用リストとして出力）。

---

## Severity グローバル方針

| Severity | 判断基準 | 運用 |
|---|---|---|
| **HIGH** | 提出物が顧客に渡った瞬間に事故になる（識別情報漏洩、AI痕跡、死亡リンク、計算誤り）| 提出前に必ず修正 |
| **MEDIUM** | 顧客が気付けば質問が来る、信頼を損なう | 提出前に確認・修正推奨 |
| **LOW** | 体裁的な不統一、読みにくさ | 時間があれば対応 |
| **INFO** | 人間の裏取り補助。自動判断できないが確認すべき | 参考情報 |
