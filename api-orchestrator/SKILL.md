---
name: api-orchestrator
description: Gemini API と Grok (xAI) API の呼び出しを一本化する Python ラッパー。利用可能なモデルを偵察して3ティア (Specialist / Primary / Utility) を自動選択し、リトライ・プロバイダ間フォールバック・コスト記録・スキルルーティング・構造化出力・Web検索・MCP ツール呼び出しループをまとめて実行する。Gemini か Grok に推論を任せたいとき、両者を切り替えて使いたいときに使う。
---

# API Orchestrator (Gemini / Grok)

このスキルは、Gemini と Grok の API を同じ使い勝手で呼び出すための司令塔。APIキーに紐づく利用可能なモデルを動的に偵察 (Scout) して各ティアの最新モデルを選び、コスト管理、エラー時の再試行、プロバイダをまたぐフォールバック、ルーティング、MCP を用いた外部ツールとの自律的な連携までを統合する。

## 🎯 ワークフローと機能 (Capabilities)

### 1. プロバイダ切替と相互フォールバック (`--provider gemini|grok`)
既定は Gemini。`--provider grok` で Grok を使う。選んだ側のメインモデル → 同じ側の Primary の順に失敗した場合 (空の回答・ターン上限到達も失敗扱い)、もう一方のプロバイダの Primary に自動で切り替える (そちらのAPIキーがある場合のみ)。

### 2. 動的モデル偵察 (Model Discovery & Categorization)
`scout.py` で利用可能なモデルをリアルタイムに取得し、3ティアに自動分類する。モデル名を決め打ちしないので、新モデルが出れば自動で追従する。

| ティア | 用途 | Gemini の選び方 (2026-10-04 時点の選択) | Grok の選び方 (2026-10-04 時点の選択) |
|---|---|---|---|
| **Specialist** | PSI分析、深い推論 | 最新版の `gemini-X.Y-pro` (`gemini-3.1-pro-preview`) | 最新 (登録時刻 `created` が新しい) の汎用モデル (`grok-4.7`) |
| **Primary** | 日常的なコーディング、調査 | 最新版の `gemini-X.Y-flash` (`gemini-3.8-flash`) | 出力単価が最も安い汎用モデル (`grok-4.3`) |
| **Utility** | 圧縮・ルーティング・データ整形 | 最新版の `gemini-X.Y-flash-lite` (`gemini-3.5-flash-lite`) | 最新の non-reasoning モデル (`grok-4.20-0309-non-reasoning`) |

- Gemini の TTS / Live / 画像などテキスト生成用でない派生モデル (`gemini-3.8-flash-tts` 等) は候補にしない。
- Grok の版番号は発売順と一致しない ("4.20" の後に "4.3") ため、新しさは `created` で判定する。コーディング特化版 (`grok-build`) と並列エージェント版 (`multi-agent`) は除外する。
- API から取得できない場合は上表のモデルをデフォルトとして使う。

### 3. 思考レベル (Gemini)
複雑度キーワード (`数学`/`統計`/`最適化`/`PSI`/`推論`/`a^2`/`アルゴリズム`/`予測`) を含むと Specialist + `thinking_level="high"`、それ以外は Primary + `thinking_level="low"`。`gemini-3.8-flash` は `minimal` を 400 エラーで拒否するため `low` を使う。Grok は Specialist を選ぶことで推論の深さを切り替える。

### 4. トークン＆コスト最適化トラッカー (Cost & Token Manager)
APIコールのたびに入出力のトークン数を計測し、概算コストを出力・`usage_log.jsonl` に記録する。Gemini は料金表 (`COST_PER_1M_TOKENS`) で、思考トークンも出力単価で計算する。Grok は起動時に xAI の `/v1/language-models` から料金を取得して計算する。

### 5. 指数的バックオフによる堅牢なリトライ (Advanced Retry)
レートリミット（429）や一時的な通信エラーに対し、`tenacity` で指数関数的な待機と最大3回の再試行を自動で行う。

### 6. コンテキスト最適化 (Context Optimization & Caching)
- **動的コンテキスト圧縮**: プロンプトが5000文字を超える場合、Utility モデルで事前要約してからメインモデルに渡す。
- **Context Caching (`--cache-file`)**: Gemini では Context Caching API でキャッシュ (TTL 5分) を作る。Grok には同等の API が無いため、ファイル本文をプロンプトに埋め込む (xAI 側のプロンプト自動キャッシュが効く)。

### 7. Web検索 (`--grounding`)
Gemini は `google_search`、Grok は Responses API の `web_search` を使う。

### 8. スキル・ルーティングと Agentic Chaining (`--auto-run`)
- **Skill Dispatcher**: ユーザーの要求意図を Pydantic の構造化出力で解析し、社内スキルから最適なタスクを提案する。
- **Agentic Chaining**: `--auto-run` を指定すると、提案されたスキルを実行する CLI コマンドを動的に生成してサブプロセスで実行し、その結果をコンテキストに統合する。
  - 生成されたコマンドは実行前に確認を求める（対話環境で `y` 応答が必要）。非対話環境（Claude Code / Gemini CLIから呼び出す場合など）では `--yes` を明示しない限り実行を拒否する。`--yes` は確認を無条件でスキップするため、生成コマンドの安全性を自分で判断できる場合のみ使う。

### 9. MCP (Model Context Protocol) 連携 (Agentic Loop)
公式の `mcp` Python SDK で、`mcp_servers.json` に定義した MCP サーバーをサブプロセスとして同時起動・接続する。Gemini / Grok がツール呼び出しを要求する限り、ツールを実行して結果を返し推論を続ける（ReAct パターン、既定で最大8ターン）。
現在デフォルトで以下のサーバーが定義されている：
- **Sequential Thinking**: 複雑な問題を段階的に分解・思考させる。
- **Puppeteer**: ブラウザを自動操作し、ウェブページをスクレイピングする（npm パッケージは非推奨化済み）。
- **Reddit**: ログイン不要で海外フォーラムの投稿を検索・収集する。
- **Fetch**: 指定したURLのテキスト（Markdown変換済み）を取得する。
- **Memory**: ナレッジグラフを用いて情報を永続的に記憶する。

加えて、ローカル専用のカスタムサーバーを接続可能（npx/uvx 配布ではなく要ビルド・要認証）：
- **Anaplan** (ローカル / `command: node`): `anaplan-mcp/dist/index.js`（別リポジトリ、要 `npm run build`・要 Anaplan 認証情報）を起動し、Anaplan モデルへのアクセスをツール化する。`mcp_servers.json` 内の `<path-to-anaplan-mcp>` は各自の環境の実パスに書き換えて使用する。

### 10. 構造化出力の強制 (Structured Output Enforcement)
`--json` で JSON での返答を強制する（Gemini: `response_mime_type`、Grok: `text.format`）。

## 🛡️ 環境の浄化 (Environment Guard)
Windows PowerShell 環境の UTF-8 化と仮想環境の整合性を常にチェックせよ。

## 🛠️ 提供リソース
- `scripts/orchestrator.py`: 全体の流れ（圧縮・ルーティング・モデル選択・フォールバック・コスト記録）と CLI。
- `scripts/providers.py`: Gemini / Grok ごとの API 呼び出し差分を吸収する層（MCP ループ・Web検索・構造化出力）。
- `scripts/mcp_manager.py`: 複数の MCP サーバーを非同期で管理・接続し、Gemini / Grok のツール形式に変換するマネージャー。
- `mcp_servers.json`: 起動する MCP サーバー群の定義ファイル。
- `scripts/scout.py`: 利用可能モデルの偵察とティア選択（Gemini / Grok）。
- `assets/gemini.md_fragment`: プロジェクト設定断片。

## 🚀 使い方
`.env` に `GOOGLE_API_KEY`（または `GEMINI_API_KEY`）と `XAI_API_KEY` を設定する（片方だけでも動くが、その場合プロバイダ間フォールバックは無効）。MCP サーバーは実行時に自動的に起動・接続される。

- **標準実行 (Gemini、MCP 自動連携)**: `python scripts/orchestrator.py "あなたのプロンプト"`
- **Grok で実行**: `python scripts/orchestrator.py --provider grok "あなたのプロンプト"`
- **JSON出力強制**: `python scripts/orchestrator.py --json "あなたのプロンプト"`
- **Web検索**: `python scripts/orchestrator.py --grounding "最新のニュースを教えて"`
- **Agentic Chaining (自動実行、確認あり)**: `python scripts/orchestrator.py --auto-run "トヨタの財務状況を分析して"`
- **Agentic Chaining (確認スキップ)**: `python scripts/orchestrator.py --auto-run --yes "トヨタの財務状況を分析して"`
- **エージェントループの最大ターン数を変更 (既定8)**: `python scripts/orchestrator.py --max-turns 12 "複雑な多段ツール呼び出しが必要なプロンプト"`
- **Context Caching**: `python scripts/orchestrator.py --cache-file "C:\path\to\doc.txt" "このドキュメントを要約して"`
- **モデル偵察**: `python scripts/scout.py` または `python scripts/scout.py [keyword]`（`XAI_API_KEY` があれば Grok の一覧と料金も表示）
