---
name: convmd
description: Convert web sources (articles, SNS posts, video/audio, digital archives) and local Office/PDF files into Obsidian-ready Markdown using the convMD CLI at <convmd-repo>. Use when the user asks to import/取り込んで/変換して a URL or file into Markdown/Vault, mentions convMD by name, or shares a URL from a supported platform (Zenn, Qiita, note, X/Twitter, Wikipedia, GitHub, Reddit, Hacker News, はてなブログ, Substack, Medium, SpeakerDeck, Podcast/RSS, 国書データベース, NDLデジタルコレクション, YouTube, or local audio/video/Office/PDF files).
---

# convMD

Webソース・ローカルファイルをObsidian向けMarkdownに変換するCLIツール。リポジトリは `<convmd-repo>`（uv管理、venv同梱）。このSkillはコマンドの組み立て方の知識のみを提供する — convMD自体のコード編集はここでは行わない。

## 基本の呼び出し方

すべてのコマンドはconvMDリポジトリ内で `uv run` 経由で実行する。

```bash
cd "<convmd-repo>"
uv run python -m convmd.cli <URLまたはファイルパス> [オプション]
```

**⚠️ 出力先は必ず明示すること。** `convMD/.convmd.yaml` に `obsidian_vault: "<vault>"` が設定済みのため、`convMD`ディレクトリ内で`cd`して実行すると**何も指定しなくてもデフォルトで`<vault>`直下に出力される**（`convMD/output/`ではない）。これは既知の罠で、意図せずVaultに直接書き込んでしまう事故が起きる。

- `convMD/output/` に出したい/テスト目的の場合 → `--output-dir <path>` を明示的に渡す（CLI引数で明示すればYAMLの`obsidian_vault`より優先される）
- 別のVaultや`<vault>`配下の特定フォルダに入れたい場合 → `--obsidian-vault <path>` を明示的に渡す
- ユーザーが単に「変換して」と言っただけでVault書き込みの意図が不明な場合は、まず`--output-dir`でconvMD/output/に出力し、確認の上で必要ならVaultへ移動する

## プラットフォーム判定 → 推奨オプション

URLを見て以下の表で判断する。convMDはURLドメインを自動判別するので、ほとんどの場合は素のURLを渡すだけでよい。追加オプションが要る/推奨されるケースのみ挙げる。

| ソース | 追加オプション | 備考 |
|---|---|---|
| 国書データベース (`kokusho.nijl.ac.jp`) | `--ocr`（翻刻したい場合）、`--bilingual`（現代語訳も併記） | `--ocr`なしだと画像ダウンロードのみ |
| NDLデジタルコレクション (`dl.ndl.go.jp`) | 同上 | IIIF経由、国書DBと同じ仕組み |
| SpeakerDeck | （なし・自動でOCR文字起こし） | Gemini OCRが自動実行される |
| YouTube (`youtu.be` / `youtube.com`) | （なし） | 字幕を自動抽出 |
| X/Twitter (`x.com` / `twitter.com`) | （なし、要 `XAI_API_KEY`） | AI再構成のため出力に要検証タグが付く |
| ローカル音声/動画 (`.mp3/.m4a/.mp4`等) | （なし、要 `uv sync --extra whisper` + FFmpeg） | faster-whisperでオフライン文字起こし |
| Podcast/RSS (`*.rss`, `/feed`) | `--podcast-limit N`（既定1） | 最新エピソードのMP3を取得して文字起こし |
| JS動的レンダリングが必要な一般サイト | `--render-js`（要 `uv sync --extra render` + playwright install） | 静的抽出が失敗する/空になる場合に検討 |
| 上記以外で静的抽出が失敗しそうなサイト | `--ai-extract` | Gemini DOM解析にフォールバック（自動でも失敗時/200バイト未満で発動する） |
| Office/PDF (`.pptx/.xlsx/.docx/.pdf`) | （なし） | markitdown経由 |
| 一般的なニュース/ブログ | （なし） | Readability相当で抽出 |

## よく使う追加フラグ

- `--transform "<指示>"`: 既存の.mdファイルをAIで加工（例: 「現代語訳して」「要点を3つに要約」）。ローカルファイルパスを渡す。結果は `<元名>_transformed.md`。
- `--auto-link`: 重要キーワードをObsidianの `[[ ]]` リンクに自動変換。`--normalize-tags`（+`--tag-similarity-cutoff 0.85`既定）と併用すると既存Vaultのタグ表記に正規化される。
- `--summary`: 複数ファイル横断のエグゼクティブサマリー生成。`--slack-webhook <URL>` で通知も可能。
- `--diff-only`: 再取得時、内容変化があった場合だけ `*_diff.md`（unified diff）を出力。キャッシュは `.convmd.db`（出力先配下のSQLite）。
- `--no-cache`: キャッシュ・差分スキップを無効化し常に再取得。
- `--format {md,json,epub,pdf,docx,html}`: 既定md。epub/pdf/docx/htmlは要pandoc。
- `--schema '<JSON>'`: `--ai-extract` 時に構造化データとして抽出したい項目を指定。
- `--depth N`: 同一ドメインのリンクをBFSで辿って複数ページ取得（既定0=クロールなし）。
- `--interval N`: N分ごとに繰り返し実行するデーモンモード（既定0=1回のみ）。
- `--input-file urls.txt` / `--retry-failed`: 複数URL一括処理と失敗分の再試行（`--retry-failed`は同じ`--output-dir`を指定する必要あり）。

## 診断・トラブルシュート

環境不備が疑われる場合（APIキー未設定、pandoc/ffmpeg不在など）は必ず先に診断を走らせる。

```bash
cd "<convmd-repo>"
uv run python -m convmd.cli doctor
```

`[FAIL]`/`[MISSING]`の行を確認し、必要な環境変数（`GEMINI_API_KEY`/`GOOGLE_API_KEY`, `XAI_API_KEY`, `NOTION_API_TOKEN`, `OBSIDIAN_REST_API_URL`/`KEY`）や外部ツール（pandoc, FFmpeg）の有無をユーザーに伝える。終了コードは常に0（診断ツールのため）なので、成否判定は出力テキストの`[FAIL]`/`[MISSING]`で行う。

よくある不足への対処:
- Gemini系機能（OCR/transform/auto-link）が動かない → `$env:GOOGLE_API_KEY` または `$env:GEMINI_API_KEY` 未設定
- X/Twitter取得が動かない → `$env:XAI_API_KEY` 未設定
- 音声文字起こしができない → `uv sync --extra whisper` 未実行 or FFmpeg未インストール
- epub/pdf/docx/html変換が失敗 → pandoc未インストール

## 全文検索

既存の変換済みMarkdownを検索する場合:

```bash
uv run python -m convmd.cli find "<キーワード>" [--in <検索先dir>] [-i] [--frontmatter-only] [--limit N]

# 意味検索（ChromaDB + Gemini Embedding。事前のインデックス構築要否は未検証 — 動作しない場合はキーワード検索にフォールバック）
uv run python -m convmd.cli find "<自然文クエリ>" --semantic [--domain <ドメイン文字列>] [--title <タイトル文字列>]
```

## 判断の指針

1. ユーザーがURL/ファイルを渡してきたら、まず上の判定表で追加オプションの要否を判断する。迷う場合はオプションなしで一度実行し、結果が不十分なら追加フラグを足す。
2. AI関連機能（OCR/transform/auto-link/ai-extract/summary/セマンティック検索）を使う前に、`GEMINI_API_KEY`か`GOOGLE_API_KEY`が環境にあるか確認する。なければユーザーに聞くか`doctor`で確認する。
3. 出力先の指定がなければ既定の`convMD/output/`に入る。Vault直接書き込みが必要なタスク（Vault整備系）では明示的に`--obsidian-vault`を渡す。
4. 複数URLを一度に処理する依頼が来たら、`--input-file`でバッチ化する（1行ずつ個別に`uv run`を呼ぶより堅牢— 失敗分は`.convmd_failed.txt`に記録され`--retry-failed`で再試行できる）。
5. 実行後、出力された.mdファイルパスをユーザーに報告する。生成物の中身をこのSkillが独自に加工/要約することはしない（`--transform`はconvMD側の機能として使う）。

詳細な実装（モジュール構成、Gemini呼び出し規約など）は `<convmd-repo>/CLAUDE.md` と `README.md` を参照。convMD自体のバグ修正・機能追加はそちらのリポジトリで行う。
