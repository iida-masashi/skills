# convMD Skill

Webソース（記事・SNS投稿・動画/音声・デジタルアーカイブ）とローカルのOffice/PDFファイルをObsidian向けMarkdownに変換する **convMD CLI**（`<convmd-repo>`、uv管理・venv同梱）を呼び出すためのSkill。このフォルダ自体にはコードは含まれない——コマンドの組み立て方に関する知識のみを提供し、convMD本体のコード編集はここでは行わない。

| Document | Purpose |
|---|---|
| [SKILL.md](SKILL.md) | プラットフォーム別オプション判定・よく使うフラグ・診断手順・判断指針 |

convMD自体の実装詳細（モジュール構成、Gemini呼び出し規約など）は別リポジトリの `<convmd-repo>/CLAUDE.md` と `README.md` を参照。

## Quick Start

```bash
cd "<convmd-repo>"
uv run python -m convmd.cli <URLまたはファイルパス> [オプション]
```

環境不備が疑われる場合はまず診断を走らせる（終了コードは常に0のため、成否は出力の`[FAIL]`/`[MISSING]`で判定する）。

```bash
uv run python -m convmd.cli doctor
```

機能によっては追加セットアップが必要:

```bash
uv sync --extra whisper   # ローカル音声/動画の文字起こし（+ FFmpeg必要）
uv sync --extra render    # JS動的レンダリングサイト向け（+ playwright install）
# epub/pdf/docx/html形式での出力には pandoc が必要
```

## 対応ソース

URLドメインは自動判別されるため、ほとんどの場合は素のURLを渡すだけでよい。追加オプションが要る/推奨されるケースのみ:

| ソース | 追加オプション | 備考 |
|---|---|---|
| 国書データベース (`kokusho.nijl.ac.jp`) | `--ocr`、`--bilingual` | `--ocr`なしだと画像ダウンロードのみ |
| NDLデジタルコレクション (`dl.ndl.go.jp`) | 同上 | IIIF経由、国書DBと同じ仕組み |
| SpeakerDeck | （なし） | Gemini OCRが自動実行される |
| YouTube (`youtu.be` / `youtube.com`) | （なし） | 字幕を自動抽出 |
| X/Twitter (`x.com` / `twitter.com`) | （なし、要 `XAI_API_KEY`） | AI再構成のため出力に要検証タグが付く |
| ローカル音声/動画 (`.mp3/.m4a/.mp4`等) | （なし、要 `uv sync --extra whisper` + FFmpeg） | faster-whisperでオフライン文字起こし |
| Podcast/RSS (`*.rss`, `/feed`) | `--podcast-limit N`（既定1） | 最新エピソードのMP3を取得して文字起こし |
| JS動的レンダリングが必要な一般サイト | `--render-js`（要 `uv sync --extra render` + playwright install） | 静的抽出が失敗する/空になる場合に検討 |
| 上記以外で静的抽出が失敗しそうなサイト | `--ai-extract` | Gemini DOM解析にフォールバック（自動でも失敗時/200バイト未満で発動） |
| Office/PDF (`.pptx/.xlsx/.docx/.pdf`) | （なし） | markitdown経由 |
| 一般的なニュース/ブログ | （なし） | Readability相当で抽出 |

他にZenn, Qiita, note, Wikipedia, GitHub, Reddit, Hacker News, はてなブログ, Substack, Mediumにも対応（frontmatter記載）。

## 主要コマンド/フラグ

```bash
# 変換の基本形
uv run python -m convmd.cli <URLまたはファイルパス> [オプション]

# 出力先の明示（既定のままだと.convmd.yamlのobsidian_vault設定に従う場合がある。下記Highlights参照）
uv run python -m convmd.cli <対象> --output-dir <path>
uv run python -m convmd.cli <対象> --obsidian-vault <path>

# 既存.mdをAIで加工（結果は<元名>_transformed.md）
uv run python -m convmd.cli <対象> --transform "<指示>"

# Obsidianリンク化・タグ正規化
uv run python -m convmd.cli <対象> --auto-link
uv run python -m convmd.cli <対象> --auto-link --normalize-tags --tag-similarity-cutoff 0.85

# 複数ファイル横断のサマリー（Slack通知も可）
uv run python -m convmd.cli <対象> --summary [--slack-webhook <URL>]

# 再取得時、変化があった場合のみ*_diff.mdを出力（キャッシュは出力先配下の.convmd.db）
uv run python -m convmd.cli <対象> --diff-only
uv run python -m convmd.cli <対象> --no-cache   # キャッシュ・差分スキップを無効化

# 出力形式（既定md。epub/pdf/docx/htmlはpandoc必要）
uv run python -m convmd.cli <対象> --format {md,json,epub,pdf,docx,html}

# --ai-extract時の構造化抽出項目指定
uv run python -m convmd.cli <対象> --ai-extract --schema '<JSON>'

# 同一ドメインのリンクをBFSで辿って複数ページ取得（既定0=クロールなし）
uv run python -m convmd.cli <対象> --depth N

# N分ごとの繰り返し実行（既定0=1回のみ）
uv run python -m convmd.cli <対象> --interval N

# 複数URL一括処理・失敗分の再試行（--retry-failedは同じ--output-dirを指定する必要あり）
uv run python -m convmd.cli --input-file urls.txt --output-dir <path>
uv run python -m convmd.cli --retry-failed --output-dir <path>

# 全文検索
uv run python -m convmd.cli find "<キーワード>" [--in <検索先dir>] [-i] [--frontmatter-only] [--limit N]

# 意味検索（ChromaDB + Gemini Embedding。事前のインデックス構築要否は未検証）
uv run python -m convmd.cli find "<自然文クエリ>" --semantic [--domain <ドメイン文字列>] [--title <タイトル文字列>]
```

## Highlights

- **出力先の罠に注意** — `convMD/.convmd.yaml` に `obsidian_vault: "<vault>"` が設定済みだと、`convMD`ディレクトリ内で実行時に何も指定しなくても**デフォルトで`<vault>`直下に出力される**（`convMD/output/`ではない）。CLI引数（`--output-dir` or `--obsidian-vault`）はYAML設定より優先されるため、意図せずVaultに書き込みたくない場合は明示的に指定する。
- **`--ai-extract`は自動フォールバックもする** — 明示指定しなくても、静的抽出が失敗した場合や抽出結果が200バイト未満の場合はGemini DOM解析に自動的にフォールバックする。
- **`doctor`の成否はテキストで判定** — 終了コードは常に0（診断ツールのため）。`[FAIL]`/`[MISSING]`の行の有無で環境不備（`GEMINI_API_KEY`/`GOOGLE_API_KEY`, `XAI_API_KEY`, `NOTION_API_TOKEN`, `OBSIDIAN_REST_API_URL`/`KEY`、pandoc, FFmpegなど）を判定する。
- **バッチ処理は`--input-file`が堅牢** — 複数URLを1行ずつ個別に`uv run`するより、`--input-file urls.txt`でまとめて処理する方が堅牢。失敗分は`.convmd_failed.txt`に記録され、同じ`--output-dir`を指定した`--retry-failed`で再試行できる。
- **X/TwitterはAI再構成に伴う要検証タグ** — `XAI_API_KEY`を使ったAI再構成のため、出力には要検証タグが付く。
- **意味検索は未検証事項あり** — `--semantic`はChromaDB + Gemini Embeddingを使うが、事前のインデックス構築が必要かどうかは未検証。動作しない場合はキーワード検索にフォールバックする。

## 判断の指針（SKILL.mdより）

1. URL/ファイルを渡されたら、まず対応ソース表で追加オプションの要否を判断する。迷う場合はオプションなしで一度実行し、結果が不十分なら追加フラグを足す。
2. AI関連機能（OCR/transform/auto-link/ai-extract/summary/セマンティック検索）を使う前に、`GEMINI_API_KEY`か`GOOGLE_API_KEY`が環境にあるか確認する。
3. 出力先の指定がなければ既定の`convMD/output/`に入る。Vault直接書き込みが必要なタスクでは明示的に`--obsidian-vault`を渡す。
4. 複数URLを一度に処理する依頼が来たら`--input-file`でバッチ化する。
5. 実行後、出力された.mdファイルパスをユーザーに報告する。生成物の中身をこのSkillが独自に加工/要約することはしない。
