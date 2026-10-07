---
aliases: [mermaid-hygiene, mermaid-validator, マーメイド検証スキル, Mermaid視認性・構文チェックスキル]
name: mermaid-hygiene
description: Mermaidダイアグラムの構文エラー防止、Mermaid 11 レキサー互換性（subgraph ID記号排除、双方向ラベル等）、および背景色と文字色のコントラスト比・視認性（暗い背景ノードは白文字・白に近い背景や fill 未指定のノードは黒文字＋淡色fill明示、Quartzダーク/ライトテーマ両立）を検査・担保・自動検証するための専門スキル。
---

# Mermaid Hygiene & Contrast Validation 専門スキルガイド

本スキルは、Obsidian Vault および Quartz 公開環境における **Mermaid ダイアグラムの構文エラー防止、アクセシビリティ（背景色と文字色の十分なコントラスト比）、およびテーマ互換性（ライト/ダーク両対応）** を担保・自動検証するための専門スキルである。

---

## 🧭 背景と解決する課題

### 1. 視認性・コントラスト問題（背景が濃い色で文字が黒くなる問題）
Quartz等の静的サイトジェネレータでは、グローバルCSS（`text { fill: var(--darkgray); color: var(--darkgray); }`）がSVGテキストに強制適用される場合があります。
Mermaidで濃紺（`#1e3a8a`）や深紅（`#991b1b`）などの暗い背景色を指定した際、文字色に明示的な白（`color:#ffffff` または `color:#fff`）を指定しないと、**ライトモード下で文字が黒に近いグレーで描画され、人間には全く読めなくなる（可読性の破綻）** 現象が発生します。

### 2. Mermaid 11（Quartz採用版）レキサー制約
Mermaid 11 では、`subgraph` の識別子（ID）に中黒（`・`）やスラッシュ（`/`）、丸括弧（`（`, `(`）などの記号が含まれていると、パーサーが字句解析（Lexical analysis）の段階でクラッシュし、**ページ全体のMermaid描画が真っ白・エラーブロック化**します。

---

## 🛡️ 9大構文・視認性バリデーションルール

本スキルでは、以下の9つのルールを厳格に検査します：

| ルールID | 種別 | 判定内容 | 修正・対応方針 |
| :--- | :--- | :--- | :--- |
| **Rule 1: BLOCK_MISMATCH** | 構文 | Mermaidコードブロックの終了バッククォート（` ``` `）の欠落 | ブロックを必ず ` ``` ` で閉じる |
| **Rule 2: SUBGRAPH_MISMATCH** | 構文 | `subgraph` の開始数と `end` の対応数が不一致 | すべての `subgraph` に対応する `end` を配置する |
| **Rule 3: QUOTE_COLLISION** | 構文 | HTMLタグ付きラベル内でのシングルクォート混入（例: `L'Oreal`） | アポストロフィ `’` または和名表記に置換する |
| **Rule 4: INVALID_ARROW** | 構文 | 不正な矢印演算子（例: `-->>`, `-->-->` 等） | 標準の `-->` または `-.->`, `==>` を使用する |
| **Rule 5: UNQUOTED_EDGE_LABEL** | 構文 | 双方向リンクの未クォートラベル（例: `<-->\|label\|`） | 必ずダブルクォートで囲む（例: `<--> \|"label"\|`） |
| **Rule 6: HAZARDOUS_SUBGRAPH_ID** | 構文 | `subgraph` ID に中黒（`・`）やスラッシュ、括弧などの記号を含む | IDから記号を除去し、表示名は `subgraph ID["表示名"]` で指定する |
| **Rule 7: DARK_FILL_WITHOUT_WHITE_TEXT** | 視認性 | 暗色背景（YIQ輝度 < 130）のノードに白文字（`color:#fff`）が未指定 | `classDef` または `style` に必ず `color:#ffffff` を追加する |
| **Rule 8: MERMAID_COMMENT_HAZARD** | 互換性 | コードブロック内に `%%` コメントが存在（Quartz OFMが削除し破損） | コメント行を削除するか、コードブロック外の注記にする |
| **Rule 9: WHITE_TEXT_WITHOUT_DARK_FILL** | 視認性 | ラベルが白文字なのに、暗色の fill（`style`/`classDef`/`class`/`:::`/div内`background:`）が無い。既定背景はライトテーマで白に近く、文字が読めない | 文字を黒（`color:#000000`）にし、淡色 fill を明示する（例 `style X fill:#f1f5f9,stroke:#475569,color:#000000`）。白文字を残すなら暗色 fill を付ける |

---

## 🎨 推奨カラーパレット＆クラス定義標準

ダイアグラムを作成・編集する際は、以下の高コントラスト標準カラーパレットを使用すること：

```mermaid
flowchart TD
    classDef root fill:#1e3a8a,stroke:#ffffff,stroke-width:2px,color:#ffffff;
    classDef main fill:#1e40af,stroke:#ffffff,stroke-width:2px,color:#ffffff;
    classDef expelled fill:#991b1b,stroke:#ffffff,stroke-width:2px,color:#ffffff;
    classDef lay fill:#065f46,stroke:#ffffff,stroke-width:1px,color:#ffffff;
    classDef cult fill:#7f1d1d,stroke:#ffffff,stroke-width:2px,color:#ffffff;
    classDef neutral fill:#374151,stroke:#ffffff,stroke-width:1px,color:#ffffff;

    subgraph 宗派系統["宗派・分派系統図"]
        A["<div style='color:#ffffff;'>宗祖・根本本部</div>"]:::root
        B["<div style='color:#ffffff;'>正統本流・管長</div>"]:::main
        C["<div style='color:#ffffff;'>除名・破門・分立</div>"]:::expelled
        D["<div style='color:#ffffff;'>信徒連合・外郭団体</div>"]:::lay
    end

    A --> B
    A --> C
    B --> D
```

### 💡 設計原則
1. **暗色背景ノードには必ず `color:#ffffff;` または `color:#fff;` をセットにする**。
   - 逆に、**背景が白に近い（または fill 未指定の）ノードの文字は黒（`color:#000000`）にする**。白文字の `<div style='color:#ffffff;'>` だけ書いて fill を付け忘れると、ライトテーマで白地に白文字になる（2026-10 cpg Vault で多数発生）。
   - 黒文字にする場合も淡色 fill を明示する。fill 未指定のままだと、ダークテーマで既定背景が暗色になり黒文字が読めなくなる。
   - 一括修正スクリプトを書くときは、`A["..."]:::cls`（ラベル直後の `:::`）と `A --> B["..."]`（エッジ行内のノード定義）を取りこぼさないこと。取りこぼすと暗色ノードを誤って黒文字化したり、修正漏れが出る。
2. **`subgraph` に中黒や記号を使わない**:
   - ❌ 悪い例: `subgraph 門祖・開山期["【門流草創】"]`
   - ⭕ 良い例: `subgraph 門祖開山期["【門流草創】"]`
3. **双方向リンクのラベルは必ず引用符で囲む**:
   - ❌ 悪い例: `A <-->|対立抗争| B`
   - ⭕ 良い例: `A <--> |"対立抗争"| B`

---

## 🛠️ 検証ツールの実行方法

本スキルのスクリプトを用いて、Markdownファイル単体またはディレクトリ全体のダイアグラムを即座に検証できます。

### 1. 単体ファイル検証
```powershell
python "C:\Users\iidam\claude-gemini-skills\mermaid-hygiene\scripts\validate_mermaid.py" "D:\Vault\religion\01_宗派・異端研究\05_法華・日蓮系\日蓮正宗.md"
```

### 2. Vault全体の全件検証
```powershell
python "C:\Users\iidam\claude-gemini-skills\mermaid-hygiene\scripts\validate_mermaid.py" "D:\Vault\religion"
```

### 3. Quartz公開ディレクトリの検証
```powershell
python "C:\Users\iidam\claude-gemini-skills\mermaid-hygiene\scripts\validate_mermaid.py" "C:\Users\iidam\quartz-religion\content"
```

### 4. 自動修正（Rule 7 のみ）
`--fix` を付けると、暗色背景なのに白文字指定がないノードのラベルを `<div style='color:#ffffff;'>…</div>` で囲む。暗色の判定はブロック単位（`classDef`・`style`・`class`・`:::`・div内の`background:`）で、改行コード（CRLF/LF）は維持する。Rule 9（白文字なのに暗色背景がない）は自動修正しないので、文字を黒にして淡色fillを明示する形に手で直す。
```powershell
python "C:\Users\iidam\claude-gemini-skills\mermaid-hygiene\scripts\validate_mermaid.py" --fix "D:\Vault\cpg"
```
