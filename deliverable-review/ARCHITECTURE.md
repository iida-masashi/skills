# Architecture — deliverable-review

内部構造、データフロー、モジュール責務、および拡張手順を記述する。

## データフロー

```
入力ファイル (.pptx / .docx / .pdf)
         │
         ▼
┌──────────────────────┐
│ extractors.extract() │    形式を判定して適切な実装に分岐
└──────────┬───────────┘
           │
           ▼
     Document オブジェクト
       ├── units: List[TextUnit]   (shape/paragraph 単位のテキスト)
       ├── location_text: dict      (場所idx → テキスト集計)
       ├── location_flags: dict     (場所idx → has_image/has_table/label)
       └── raw: Presentation/Document (python-pptx等のオブジェクト)
           │
           ▼
┌─────────────────────────┐
│ checkers.run_all(doc)   │   10 チェッカーを順次実行
└──────────┬──────────────┘
           │
           ▼
     List[Finding]
       ├── checker: 識別子
       ├── severity: HIGH/MEDIUM/LOW/INFO
       ├── category: サブ分類
       ├── location_label: "Slide 3" 等
       ├── location_index: 数値
       ├── evidence: マッチ文字列
       ├── note: 指摘コメント
       └── source_handle: 元のshape/cellへのポインタ
           │
     ┌─────┴─────┬─────────┬──────────┐
     ▼           ▼         ▼          ▼
  レポート    マーキング  サニタイズ  AIチェック JSON
  review.md   _marked     _sanitized  _aicheck.json
              .pptx/docx  .pptx/docx/
                          pdf
```

## モジュール責務

### `review.py` — CLIエントリ

- 引数解析 (`argparse`)
- 拡張子判定
- 各フェーズの呼び出し順序制御
- Markdownレポート生成（サマリ表、チェッカー別詳細）
- コンソールサマリ表示

### `extractors.py` — テキスト抽出

| 関数 | 責務 |
|---|---|
| `extract(path)` | 拡張子でディスパッチ |
| `extract_pptx(path)` | python-pptx で shape → TextUnit |
| `extract_docx(path)` | python-docx で paragraph → TextUnit |
| `extract_pdf(path)` | pdfplumber で page → TextUnit |

**重要な不変条件**:
- `Document.location_flags[idx]` は必ず `has_image`/`has_table`/`label` キーを持つ
- `TextUnit.has_image_on_page`/`has_table_on_page` は extract時にlocation_flagsから転写される
- PowerPointのグループ化されたシェイプは `extractors.iter_shapes_recursive` 経由で**再帰展開済み**。ネストしたGroupShape内のテキスト・表・チャート・画像も全チェッカーが走査できる

### `patterns.py` — 正規表現集約

全チェッカーが参照する正規表現とパターン群。変更時はここだけ触る。

公開 API:
- `find_url_contamination(text)` → `[(category, match), ...]`
- `extract_all_urls(text)` → `[url, ...]`
- `find_ai_traces(text)` → `[(category, match), ...]`
- `has_citation(text)` → `bool`
- `extract_verifiable_claims(text)` → `[(category, match), ...]`
- `LONG_TEXT_THRESHOLD = 100`

### `checkers.py` — 基本5チェッカー + 統合

- `Finding` dataclass（全チェッカー共通の結果型）
- Severity 定数 (`SEVERITY_HIGH` 等)
- `check_url_contamination`, `check_ai_traces`, `check_copyright`, `check_url_liveness`, `check_verifiable_claims`
- `run_all(doc, skip_liveness)` — 10 チェッカーを順次呼ぶ

### `numeric_integrity.py` — 数値整合性

- 単位混在（通貨単位、%/pp）検出
- pptx ネイティブチャートの読み取り（python-pptx の chart API）と合計検証
- 表の行/列合計の再計算（pptx/docx/pdfテーブル）

### `metadata.py` — メタデータ

- **検出** (`check_metadata`): pptx/docx は core properties、pptx は hidden slide、docx は `word/comments.xml` と tracked changes、pdf は pdfplumber の metadata
- **サニタイズ** (`sanitize`):
  - python-pptx/docx で core properties をクリア
  - zipfile を手動で開いて `docProps/app.xml` の Company/Manager/HyperlinkBase を空に、TotalTime/Revision を 0 に
  - docx は `word/comments*.xml`/`people.xml` を削除、`document.xml` の `<w:ins>/<w:del>` を accept、relationships と ContentTypes から comments 参照を除去
  - pdf は pypdf で /Info を空に、/Metadata を削除

### `internal_content.py` — 内部コンテンツ

- PPTスピーカーノート、非表示スライド、PPT/Wordコメント
- 危険ワード（`_DANGER_PATTERNS`）ヒット時は Severity を HIGH に昇格
- PPTコメントは zipfile で `ppt/comments/commentN.xml` を直接パース（python-pptx未対応）

### `style_checks.py` — コンサル作法(文体) Phase 1

- `check_title_messaging_pptx`: タイトル体言止め検出（除外キーワードリストあり）
- `check_term_inconsistency`: 表記ゆれグループ判定、全半角混在
- `check_prohibited_expressions`: 景表法リスク、曖昧表現多用
- `check_honorific_mixing`: 敬体/常体混在
- `check_date_format_mixing`: 日付書式混在

### `layout_checks.py` — コンサル作法(体裁) Phase 2

- `check_title_page_number_integrity`: タイトル/ページ番号欠落
- `check_font_uniformity`: フォント3種以上/5種以上
- `check_tiny_font`: 8pt/10pt未満検出

### `ai_check_extract.py` — AIチェック 構造抽出

- 各スライドを role 分類（cover/agenda/company-profile/team-profile/problem/solution/benefit/schedule/team/pricing/appendix/content）
- body_paragraphs / bullets / tables / has_image / has_chart / speaker_notes を JSON 化
- `write_prompt_hint`: Claude Code 向けレビュー手順書を出力

### `markers.py` — レビュー用コピー生成

- pptx: 各スライド右上に注釈テキストボックス追加、最悪severity色で枠線
- docx: 文書先頭に指摘サマリを挿入
- pdf: 非対応（レポートのみ）

## 型定義

### `extractors.TextUnit`

```python
@dataclass
class TextUnit:
    kind: str               # "text" | "table-cell" | ...
    text: str
    location_label: str     # "Slide 3", "Page 2", "Para 12"
    location_index: int     # slide idx / page idx / doc-level 1
    has_image_on_page: bool
    has_table_on_page: bool
    source_handle: Optional[Any]  # shape/cell/paragraph等への参照
```

### `extractors.Document`

```python
@dataclass
class Document:
    path: str
    ext: str                  # ".pptx" / ".docx" / ".pdf"
    units: List[TextUnit]
    location_text: dict       # idx -> "集計テキスト"
    location_flags: dict      # idx -> {"has_image": bool, "has_table": bool, "label": str}
    raw: Any                  # Presentation / DocxDocument / None
```

### `checkers.Finding`

```python
@dataclass
class Finding:
    checker: str              # "url-contamination" 等
    severity: str             # "HIGH" / "MEDIUM" / "LOW" / "INFO"
    category: str             # サブ分類
    location_label: str
    location_index: int
    evidence: str             # マッチ文字列（短く）
    note: str                 # 人間向け説明
    source_handle: Optional[Any]
```

## 拡張の仕方

### 新しい検出パターンを追加

1. **チェッカーを既存カテゴリに足す**:
   - `patterns.py` に正規表現を追加
   - 対応する `find_*` や `check_*` 関数に組み込む
   - Severity と category 名を決める
   - `CHECKS.md` に1行追加

2. **新しいチェッカーを追加**:
   - 新ファイル `scripts/my_check.py` を作成、`run_my_check(doc) -> List[Finding]` を実装
   - `checkers.run_all` に `findings.extend(my_check.run_my_check(doc))` を追加
   - `review.py` の `CHECKER_LABEL` と `CHECKER_ORDER` に追加
   - `SKILL.md` の Checks 表、`CHECKS.md` にセクション追加

### 新しい形式を追加（例: Excel .xlsx）

1. `extractors.py` に `extract_xlsx(path)` を実装し、`Document` を返す
2. `extractors.extract(path)` の拡張子ディスパッチに追加
3. `markers.py`, `metadata.py`, `numeric_integrity.py` など、形式依存チェッカーに分岐を追加
4. `SKILL.md` の「形式別カバレッジ」表を更新

### Severity の判定基準を変更

- `SKILL.md` → `## Severity Guide`
- `CHECKS.md` → 各チェッカーの表
- 該当チェッカー内の分岐で `SEVERITY_*` を変更
- 3箇所の整合を保つ

### 誤検知を減らす

1. **再現**: 小さなサンプル（smokeテスト）で誤検知パターンを固定
2. **原因特定**: どの正規表現/条件が拾いすぎているか
3. **修正方針**:
   - パターンを厳格化（lookahead/lookbehind 追加、最小/最大量指定）
   - 閾値を上げる（count ≥ 2 等）
   - コンテキスト判定を足す（段落単位、同一ユニット内複数発火のみ 等）
4. **回帰確認**: 修正前後の件数差を実ファイルで比較

## パフォーマンス特性

| 処理 | 計算量 | 典型所要時間（70-90スライド） |
|---|---|---|
| extract_pptx | O(shapes) | 0.5〜2秒 |
| 基本チェッカー（URL/AI/コピ/主張/数値/メタ/内部/作法） | O(n × パターン数) | 1〜3秒 |
| URL死活 | O(URL数 / 並列度) | URL数次第、10本並列で5秒程度/20URL |
| レポート生成 | O(findings) | 瞬時 |
| マーキング書き込み | O(slides) | 0.5〜2秒 |
| AIチェック JSON | O(shapes) | 0.5〜2秒 |

ボトルネックは **URL死活**。スキップには `--skip-liveness` を使う。

## 依存関係

| ライブラリ | 用途 | バージョン |
|---|---|---|
| `python-pptx` | .pptx 読み書き | ≥ 0.6.23 |
| `python-docx` | .docx 読み書き | ≥ 1.1.0 |
| `pdfplumber` | .pdf テキスト/表抽出 | ≥ 0.10.0 |
| `requests` | URL 死活チェック | ≥ 2.31.0 |
| `pypdf` | PDF サニタイズ（/Info 削除）| ≥ 4.0.0 |

Tesseract / OCR は **未導入**（画像化資料の扱いは別フェーズの検討事項）。

## テスト戦略

`scripts/_smoke_make_sample.py` が各チェッカーを発火させるサンプル pptx を生成する。

```bash
py scripts/_smoke_make_sample.py /tmp/sample.pptx
py scripts/review.py /tmp/sample.pptx --sanitize --ai-check-json
```

回帰テストは実際の提案書ファイルでの件数差分を追う（結果は保存しないが、大きな件数変動があればパターン修正の副作用を疑う）。
