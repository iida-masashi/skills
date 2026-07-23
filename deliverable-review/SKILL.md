---
name: deliverable-review
description: Use when a management consultant is about to deliver a PowerPoint/Word/PDF to a client and needs a pre-delivery self-check — covering (1) information leakage: file metadata (author/company), hidden slides, speaker notes, tracked changes, PPT/Word comments; (2) AI traces: utm_source=chatgpt URLs, AI boilerplate, knowledge cutoff mentions; (3) accuracy: dead URLs, chart/table total integrity, unit mixing, unverified numeric/date/ranking claims, missing citations; (4) consulting style: title messaging, term consistency, prohibited expressions, layout (fonts/tiny text/page numbers); (5) strategy quality: title length, bullet overload (Miller's 7±2), agenda-vs-sections mismatch, katakana overload, missing assumptions in forecasts, missing executive summary; (6) optional Gemini 3.1 Pro qualitative review covering pyramid principle, MECE, So What? / Why So?, action concreteness, narrative balance, client perspective, logic leaps, framework consistency (3C/4P/PEST/SWOT/Five Forces), feasibility (resources/risks/dependencies/milestones).
---

# deliverable-review

顧客提出前のコンサル資料（.pptx / .docx / .pdf）を **10観点 + AIチェック定性レビュー** でチェックし、Markdownレポート・マーキング付きコピー・サニタイズ済みファイルを生成するスキル。

## When to Use

ユーザーが次のようなことを言ったとき：

- 「資料を顧客に出す前にチェックして」「デリバラブルをレビューして」
- 「`utm_source=chatgpt` が混じってないか見て」「AI臭さをチェックして」
- 「出典が抜けてないか確認して」「表の合計が合っているか見て」
- 「作成者情報を消して」「コメントが残ってないか確認して」
- 「表記ゆれ（顧客/クライアント等）を確認して」「タイトル体言止めをチェック」
- 「ピラミッド原則/MECE/So What? でレビューして」（AIチェック）
- 「`/deliverable-review <ファイル>`」

## Checks (10 checkers)

| # | チェッカー | キー内容 | Severity |
|---|---|---|---|
| 1 | **メタデータ** | 作成者・会社名・最終更新者・題目・キーワード等、Wordコメント、変更履歴、PDF /Info | HIGH/MEDIUM |
| 2 | **内部コンテンツ** | スピーカーノート（危険ワード検出付）、非表示スライド、PPT/Wordコメント | HIGH/MEDIUM/INFO |
| 3 | **URL汚染** | `utm_source=chatgpt.com` 等AI由来クエリ、AIツール会話URL、`fbclid`/`gclid` 等一般トラッキング | HIGH/MEDIUM |
| 4 | **AI生成痕跡** | 日英AI定型句、knowledge cutoff言及、Markdown残骸（複数バレット）、絵文字過多 | HIGH/MEDIUM/LOW |
| 5 | **数値整合性** | 円グラフ合計≠100%、100%積上げ合計、単位混在（億円/百万円）、%/pp混在、表の行・列合計の再計算 | HIGH/MEDIUM |
| 6 | **コンサル作法(文体)** | タイトル体言止め、表記ゆれ、景表法リスク表現、曖昧表現多用、敬体/常体混在、日付書式混在、全半角混在 | MEDIUM/LOW/INFO |
| 7 | **コンサル作法(体裁)** | タイトル/ページ番号欠落、フォント3種以上、10pt/8pt未満の極小文字 | MEDIUM/LOW |
| 8 | **著作権リスク** | 100文字以上の本文で出典記載なし／画像・表で出典記載なし | MEDIUM/LOW |
| 9 | **URL死活** | 全URLをHEAD(→GET fallback)で到達確認（5秒タイムアウト、並列10本） | HIGH/MEDIUM |
| 10 | **検証要主張** | 出典記載のない箇所の数値・日付・ランキング主張を抽出（人間レビュー補助） | INFO |

詳細な検出パターンと Severity 判定ルールは [CHECKS.md](CHECKS.md) を参照。

### AIチェック (定性レビュー、LLMベース)

`--ai-check-json` で構造化JSON（table_of_contents, role分類, body_paragraphs, bullets, tables, notes）を抽出。同時にレビュー手順書（`*_aicheck_prompt.md`）も生成。Claude Code や他のLLMに渡し、以下を定性レビューさせる:

**Tier-1 戦略コンサル MD/Partner 視点・15観点・赤入れ品質**:

1. **pyramid** — ピラミッド原則（タイトル群の論理階層）
2. **mece** — MECE（漏れ・ダブり、「その他」30%超は分類失敗）
3. **so-what** — So What? / Why So?（タイトル=メッセージか、本文がデータ羅列で終わっていないか）
4. **issue-tree** — Issue Tree / Key Question（中心問いの明示と章立てとの整合）
5. **logic-leap** — ロジックの飛躍（Fact→Insight→Implication→Recommendation の連鎖、相関と因果の混同）
6. **data-rigor** — 数値の出所と粒度（母数・為替・年度・税抜税込・桁丸めの一貫性、出典）
7. **framework** — フレームワーク整合（3C/4P/PEST/SWOT/Five Forces/2x2 の要素欠落・粒度・軸定義）
8. **action** — アクションの具体性（誰が／いつまでに／何を／いくらで／成功条件）
9. **feasibility** — 実行可能性（リソース・リスク↔対策ペア・依存関係・Go/No-Go）
10. **balance** — 構成バランス（現状→課題→原因→打ち手→効果→体制/スケジュール/費用）
11. **client-view** — 顧客視点（顧客固有要素の反映、自社紹介過多の有無）
12. **alternatives** — 代替案の提示（複数案比較・採用理由・trade-off）
13. **premise** — 前提・限界の開示（スコープ外、未検証論点、データ制約）
14. **story-line** — Story Line（エグゼクティブサマリーの自立性、サマリと本編の結論一致）
15. **risk-scenario** — リスクシナリオ（ベース／ベスト／ワースト感度、前提崩れ時の対応）

各観点について最低1件の指摘または「該当なし・問題なし」宣言を**必ず**行います（黙ってスキップ不可）。

各指摘は **8フィールド** で出力されます: severity / category / slide / quote（原文引用） / issue（指摘） / why_it_matters（影響） / suggestion（改善方針） / rewrite_example（書き換え例：現状→改善）。

加えて資料全体の **overall_assessment** を出力: key_question（再構成された中心問い）／ answer_clarity ／ story_line_summary ／ top_strengths ／ top_weaknesses ／ client_readiness（提出可/要修正/大幅手直し必要）／ estimated_grade（A〜D）／ partner_one_liner（MDが新人に投げる現場感ある一言）。

Web UI では上記2経路で自動化:

1. **戦略コンサル品質チェック（ローカルルール・既定ON）** — `scripts/strategy_checks.py`
   以下10観点を機械判定。外部送信なし:
   - タイトル長過ぎ / タイトル複数文 / 曖昧・主語なしタイトル
   - バレット過多（Miller's Law: 7±2）
   - 結論スライド欠落 / アジェンダと本編の不整合 / スライド数不足
   - **カタカナ多用** — 1スライドのカタカナ密度20%超＋5語以上ユニーク
   - **前提条件キーワード不在** — 予測・試算を含むスライドで「前提/仮定/試算根拠」の記載がない
   - **エグゼクティブサマリー欠落** — 5枚以上の資料で冒頭4枚以内にサマリーがない
2. **Gemini 3.1 Pro による自動定性レビュー（既定OFF）** — `scripts/llm_review.py`
   サイドバーで有効化すると、AIチェックJSONを Gemini 3.1 Pro (`gemini-3.1-pro-preview`) に送信し、上記**15観点を網羅レビュー**（観点ごとに最低1件の指摘 or 該当なし宣言）。各指摘は8フィールド構造（severity / category / slide / quote / issue / why_it_matters / suggestion / rewrite_example）。資料全体の overall_assessment（評価グレード A〜D、提出可否、Partner一言、強み/弱み Top）も同時に返します。
   - 入力プロンプトは bullets/body/tables/speaker_notes を**切り詰めず全量送信**（appendix系のみ context長対策で圧縮）
   - SYSTEM_PROMPT は `llm_review.py` と Claude Code 内蔵パスで**単一ソース化**されており、両経路でレビュー品質が一致
   - 結果は画面にカテゴリ別表示。APIキーは環境変数 `GOOGLE_API_KEY`（または `GEMINI_API_KEY`）、もしくは `.env` ファイル（カレント／スキル直下／ユーザーホーム、環境変数 `DELIVERABLE_REVIEW_ENV_FILE` で明示指定可）を使用。**スライド本文が Google に送信されるため、機密資料では既定OFFのまま使用すること。**

### 形式別カバレッジ

| チェック | .pptx | .docx | .pdf |
|---|:---:|:---:|:---:|
| メタデータ | ✅ | ✅ | ✅ |
| 内部コンテンツ | ✅ (notes/hidden/comments) | ✅ (commentsのみ) | ✖ |
| URL汚染・AI痕跡・URL死活・著作権・検証要主張 | ✅ | ✅ | ✅ |
| 数値整合性 (チャート) | ✅ | ✖ | ✖ |
| 数値整合性 (表) | ✅ | ✅ | ✅ |
| コンサル作法(文体) | ✅ | ✅ | ✅ |
| コンサル作法(体裁) | ✅ | ✖ | ✖ |
| マーキング付きコピー | ✅ | ✅ (先頭サマリ) | ✖ (レポートのみ) |
| サニタイズ | ✅ | ✅ | ✅ |
| AIチェック JSON | ✅ | ✅ (簡易) | ✅ (簡易) |

## How to Run

### 1. 初回のみ: 依存関係インストール

```bash
pip install -r ~/.claude/skills/deliverable-review/requirements.txt
```

依存: `python-pptx` / `python-docx` / `pdfplumber` / `requests` / `pypdf`

### 2. 実行方法

#### CLI

```bash
python ~/.claude/skills/deliverable-review/scripts/review.py <file>
```

Windowsで `python` が MS Store ランチャにフォールバックする場合は `py` コマンドを使用:

```bash
py ~/.claude/skills/deliverable-review/scripts/review.py <file>
```

#### Web UI (Streamlit)

ブラウザからファイルをドラッグ&ドロップしてチェックしたい場合:

```bash
py -m streamlit run ~/.claude/skills/deliverable-review/webui/app.py
```

→ ブラウザで `http://localhost:8501` が自動で開く。サイドバーでURL死活/サニタイズ/AIチェック JSONをon/offし、アップロード後に結果サマリ・フィルタ付き指摘一覧・各種ダウンロード（レポート/マーキング付き/サニタイズ版/AIチェック JSON）にアクセス可能。**処理はすべてローカル、ファイルは外部に送信されません**。

### 3. CLIオプション

| フラグ | 目的 |
|---|---|
| `--skip-liveness` | URL死活チェックをスキップ（ネット不可時・高速化） |
| `--out-dir DIR` | 出力先ディレクトリ（既定: 入力と同じ） |
| `--sanitize` | `<stem>_sanitized.<ext>` を別途生成（core/app properties、変更履歴、Wordコメント、PDF /Infoを自動削除）。**非表示スライド・スピーカーノートは削除しない** — 意図的な場合があるため検出のみ |
| `--ai-check-json` | `<stem>_aicheck.json`（構造データ）と `<stem>_aicheck_prompt.md`（レビュー手順書）を生成 |

### 4. 出力ファイル

入力ファイルと同じディレクトリ（または `--out-dir`）に生成：

| ファイル | 内容 | 常時 |
|---|---|:---:|
| `<stem>_review.md` | Markdownレポート（サマリ表＋指摘詳細）| ✅ |
| `<stem>_marked.pptx` | 各スライド右上に指摘サマリボックス | .pptx時 |
| `<stem>_marked.docx` | 文書先頭に指摘サマリ | .docx時 |
| `<stem>_sanitized.<ext>` | メタデータ削除済みコピー | `--sanitize` 時 |
| `<stem>_aicheck.json` | スライド構造データ | `--ai-check-json` 時 |
| `<stem>_aicheck_prompt.md` | 定性レビュー手順書 | `--ai-check-json` 時 |

## Claude's Workflow

**このスキルが Claude Code 内から呼ばれた場合、LLM API（Gemini / 外部サービス）は使用しない。Claude 自身が `_aicheck.json` を読み、`_aicheck_prompt.md` の指示に従って定性レビューを行う。APIキーは不要。**

ユーザーから資料のパスを受け取ったら:

1. **依存関係の確認** — 初回実行なら `pip install -r requirements.txt` を案内
2. **基本チェック＋AIチェック構造抽出を同時実行** — `py scripts/review.py <path> --ai-check-json` を起動。
   これで `<stem>_review.md`（機械判定レポート）と `<stem>_aicheck.json` / `<stem>_aicheck_prompt.md`（Claude が読む定性レビュー用データ）が生成される。
3. **機械判定の報告** — HIGH/MEDIUM 件数を強調、生成ファイルパスを提示。
4. **Claude による定性レビュー実施** — `Read` ツールで `<stem>_aicheck.json` と `<stem>_aicheck_prompt.md` を読み込み、手順書の **15観点**（pyramid / mece / so-what / issue-tree / logic-leap / data-rigor / framework / action / feasibility / balance / client-view / alternatives / premise / story-line / risk-scenario）を**網羅レビュー**（観点ごとに最低1件の指摘または「該当なし」宣言、黙ってスキップ不可）。各指摘は8フィールド（severity / category / slide / quote / issue / why_it_matters / suggestion / rewrite_example）。`overall_assessment`（A〜D評価、提出可否、Partner一言、強み/弱み）も書き出す。
   - 必要に応じて `<stem>_aicheck_review.md` として保存
   - 指摘は必ずスライド番号を添える
   - 外部APIは呼ばない（Gemini / Claude API 等を使う `llm_review.py` は **使用しない**）
5. **HIGH指摘がある場合** — 提出前の修正を促し、`--sanitize` を提案。
6. **最終サマリ** — 機械判定 + 自分が書いた定性レビュー を統合して、優先度付きアクションリストをユーザーに返す。

### Web UI との違い

`webui/app.py` のサイドバーには「Gemini 3.1 Pro 定性レビュー」チェックボックスがあるが、それは **Web UI をブラウザから直接使う人向けのオプション**。Claude Code から Skill として起動する場合は、Claude 自身がレビュアーなので Gemini を呼ぶ必要がない。ユーザーが明示的に「Geminiで」と指示した場合のみ `llm_review.py` 経由で実行すること。

## Severity Guide

| 重要度 | 意味 | 典型例 |
|---|---|---|
| **HIGH** | 提出前に必ず修正 | 作成者メタデータ、`utm_source=chatgpt.com`、死亡URL、AI定型句、危険ワード入りスピーカーノート、円グラフ合計≠100% |
| **MEDIUM** | 要確認 | 一般トラッキング、knowledge cutoff言及、出典欠如、表記ゆれ、極小文字(8pt未満)、フォント3種以上 |
| **LOW** | 軽微 | Markdown残骸、タイトル体言止め、日付書式混在、敬体/常体混在、小さい文字(10pt未満) |
| **INFO** | 参考 | 検証要主張リスト、曖昧表現多用（裏取り補助） |

## Directory Layout

```
deliverable-review/
  SKILL.md              # このファイル
  CHECKS.md             # 10チェッカーの詳細カタログ
  ARCHITECTURE.md       # 内部アーキテクチャと拡張ガイド
  requirements.txt      # Python依存
  scripts/
    review.py           # CLIエントリ、レポート生成、パイプライン制御
    extractors.py       # pptx/docx/pdf → TextUnit/Document
    patterns.py         # 正規表現パターン一覧
    checkers.py         # 基本5チェッカー + Finding型 + run_all()
    numeric_integrity.py # 数値整合性チェック
    metadata.py         # メタデータ検出＋サニタイズ
    internal_content.py # ノート/非表示/コメント抽出
    style_checks.py     # Phase 1 コンサル作法(文体)
    layout_checks.py    # Phase 2 コンサル作法(体裁)
    strategy_checks.py  # 戦略コンサル品質ルール (案A: ローカル機械判定)
    ai_check_extract.py # AIチェック 構造JSON抽出
    llm_review.py       # Gemini 3.1 Pro 定性レビュー (案B)
    markers.py          # pptx/docxにマーキング
  webui/
    app.py              # Streamlit Web UI (アップロード → レビュー → DL)
  tests/
    test_smoke.py       # pytest スモーク (外部API不要)
```

## Notes / Limitations

- **著作権チェック**は「長文＋出典欠如」という状況証拠ベース。盗用検出そのものは行わない。
- **検証要主張**は抽出のみ。裏取りは人間作業。
- **画像化された資料**（スライドが全画像）は `extractors` がテキストを拾えず、ほとんどのチェックが機能しない。OCR拡張は未実装。
- **PDF** はマーキング非対応（レポートのみ）。
- `python-pptx` にはネイティブコメント機能がないため、注釈はテキストボックスで追加。元ファイルは変更せず `_marked.pptx` コピーを生成。
- **URL死活** は HEAD → 失敗時 GET フォールバック。Bot対策で 403 を返すサイトは誤検知する場合あり。
- **AIチェック JSON 生成** 自体は外部API送信なし。Claude Code や他のLLMが JSON を読む前提。
- **Gemini 3.1 Pro レビュー（Web UI 案B、既定OFF）** を有効にした場合のみ、スライド本文が Google Gemini API に送信される。機密資料では既定OFFのまま使用すること。
- **フォント統一チェック** は python-pptx の `run.font.name` に依存。テーマ継承で `None` になる場合、カウント外。
