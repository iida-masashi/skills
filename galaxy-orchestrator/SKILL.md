---
name: galaxy-orchestrator
description: Gemini 3 世代 (3.1 Pro / 3.6 Flash / 3.5 Flash-Lite) を極限まで使いこなすための軍師。動的な思考レベル制御、確実なフォールバック、コストトラッキング、ルーティング、構造化出力、および MCP (Model Context Protocol) クライアントを統合して実現する。
---

# Galaxy Orchestrator (Gemini 3 Edition)

このスキルは、Gemini 3 シリーズの「推論能力」と「スピード」を最適にバランスさせる。APIキーに紐づく利用可能なモデルを動的に偵察(Scout)し、常に最も費用対効果が高く強力なエンジンを選択するだけでなく、コスト管理からエラー時の再試行、ルーティング、さらに MCP を用いた外部ツールとの自律的な連携までを統合した「完全な司令塔」として機能する。

## 🎯 ワークフローと機能 (Capabilities)

### 1. 動的モデル偵察 (Model Discovery & Categorization)
`scout.py` を用いて利用可能なモデルをリアルタイムに取得し、以下の層に自動分類する。API未取得時のデフォルトは以下（2026-08時点）。
- **Specialist**: `gemini-3.1-pro-preview` (PSI分析、深い推論が必要なタスク)
- **Primary**: `gemini-3.6-flash` (日常的なコーディング、高速レスポンス)
- **Utility**: `gemini-3.5-flash-lite` (データ整形、ログ解析などの単純作業)

### 2. トークン＆コスト最適化トラッカー (Cost & Token Manager)
APIコールのたびに入出力のトークン数を計測し、1ドル以下のミクロなAPI課金額をリアルタイムで算出してログに出力する。

### 3. 指数的バックオフによる堅牢なリトライ (Advanced Retry)
レートリミット（429）や一時的な通信エラーに対し、`tenacity` を用いて指数関数的な待機と最大3回の再試行を自動で行う。それでも失敗した場合は下位モデルへフォールバックする。

### 4. コンテキスト最適化 (Context Optimization & Caching)
- **動的コンテキスト圧縮**: プロンプトが5000文字を超える場合、高価なモデルに投げる前に軽量な Utility モデル（Flash Lite）で事前要約を自動実行し、ノイズを除去してトークン消費を大幅に削減する。
- **Context Caching API (`--cache-file`)**: 巨大な仕様書やデータセットなどを指定することで、API側にキャッシュを作成（TTL5分）し、コンテキストの高速読み込みと低コスト化を実現する。

### 5. Google Search Grounding (`--grounding`)
Gemini 3 の公式グラウンディング機能をネイティブサポート。フラグを指定することで、最新のウェブ検索結果に基づいた事実推論を行う。

### 6. スキル・ルーティングと Agentic Chaining (`--auto-run`)
- **Skill Dispatcher**: ユーザーの要求意図を Pydantic の構造化出力を用いて解析し、社内スキルから最適なタスクを自動で提案する。
- **Agentic Chaining**: `--auto-run` フラグを指定することで、提案されたスキルを実行するための CLI コマンドを動的に生成し、サブプロセスとして自動実行。その結果（標準出力・エラー）をコンテキストに統合し、自律的な問題解決を図る。
  - 生成されたコマンドは実行前に確認を求める（対話環境で `y` 応答が必要）。非対話環境（Claude Code / Gemini CLIから呼び出す場合など）では `--yes` を明示しない限り実行を拒否する。`--yes` は確認を無条件でスキップするため、生成コマンドの安全性を自分で判断できる場合のみ使う。

### 7. MCP (Model Context Protocol) 連携 (Agentic Loop)
公式の `mcp` Python SDK を組み込み、無料でAPIキー不要な複数のオープンソース MCP サーバーをサブプロセスとして同時起動・接続する。
Gemini が動的に Function Calling (ツール呼び出し) を要求し、最終的な回答にたどり着くまで自律的にツールを実行・推論を繰り返す（ReAct パターン）。
現在デフォルトで以下のオープンソースサーバー（`mcp_servers.json` に定義）が利用可能：
- **Sequential Thinking**: 複雑な問題を段階的に分解・思考させる。
- **Puppeteer**: ブラウザを自動操作し、ウェブページをスクレイピングする。
- **Reddit**: ログイン不要で海外フォーラムの生の声やトレンドを検索・収集する。
- **Fetch**: 指定したURLのテキスト（Markdown変換済み）を高速に取得する。
- **Memory**: ナレッジグラフを用いてユーザー情報やプロジェクトの設定を永続的に記憶する。

加えて、ローカル専用のカスタムサーバーを接続可能（npx/uvx 配布ではなく要ビルド・要認証）：
- **Anaplan** (ローカル / `command: node`): `anaplan-mcp/dist/index.js`（別リポジトリ、要 `npm run build`・要 Anaplan 認証情報）を起動し、Anaplan モデルへのアクセスをツール化する。`mcp_servers.json` 内の `<path-to-anaplan-mcp>` は各自の環境の実パスに書き換えて使用する。

### 8. 構造化出力の強制 (Structured Output Enforcement)
引数として `--json` を渡すことで、指定した JSON スキーマでの返答を強制し、他システムとの連携（データパイプライン化）を容易にする。

## 🛡️ 環境の浄化 (Environment Guard)
Windows PowerShell 環境の UTF-8 化と仮想環境の整合性を常にチェックせよ。

## 🛠️ 提供リソース
- `scripts/orchestrator.py`: Gemini 3 専用の動的思考レベル制御および高度なルーティング・MCP（ReAct ループ）・フォールバックラッパー。
- `scripts/mcp_manager.py`: 複数の MCP サーバーを非同期で管理・接続し、Gemini の Function Calling に対応させるマネージャー。
- `mcp_servers.json`: 起動する MCP サーバー群の定義ファイル。
- `scripts/scout.py`: Google GenAI SDKを用いたコア偵察エンジン（利用可能モデルリスト取得）。
- `assets/gemini.md_fragment`: Gemini 3 仕様のプロジェクト設定断片。

## 🚀 使い方
複雑なタスクの前にこのスキルを召喚し、`orchestrator.py` で最適な推論パスを確保せよ。MCP サーバーは実行時に自動的に起動・接続される。

- **標準実行 (MCP 自動連携)**: `python scripts/orchestrator.py "あなたのプロンプト"`
- **JSON出力強制**: `python scripts/orchestrator.py --json "あなたのプロンプト"`
- **Google Search Grounding**: `python scripts/orchestrator.py --grounding "最新のニュースを教えて"`
- **Agentic Chaining (自動実行、確認あり)**: `python scripts/orchestrator.py --auto-run "トヨタの財務状況を分析して"`
- **Agentic Chaining (確認スキップ)**: `python scripts/orchestrator.py --auto-run --yes "トヨタの財務状況を分析して"`
- **エージェントループの最大ターン数を変更 (既定8)**: `python scripts/orchestrator.py --max-turns 12 "複雑な多段ツール呼び出しが必要なプロンプト"`
- **Context Caching**: `python scripts/orchestrator.py --cache-file "C:\path\to\doc.txt" "このドキュメントを要約して"`
- **モデル偵察**: `python scripts/scout.py` または `python scripts/scout.py [keyword]`
