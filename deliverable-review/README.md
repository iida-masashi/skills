# deliverable-review

顧客提出前のコンサル資料（`.pptx` / `.docx` / `.pdf`）を **10観点の機械チェック + 戦略コンサル品質ルール（10項目） + AI定性レビュー（15観点）** の3層でチェックし、Markdownレポート・マーキング付きコピー・サニタイズ済みファイル・AIチェック構造化JSONを生成する。

- **CLI**: `scripts/review.py`
- **Web UI (ローカル)**: `webui/app.py`
- **Web UI (Cloud Run)**: <https://deliverable-review-wecljomxda-an.a.run.app>（`main` への push で自動デプロイ。下記「Cloud Run デプロイ」参照）
- **ドキュメント**: [SKILL.md](SKILL.md) / [CHECKS.md](CHECKS.md) / [ARCHITECTURE.md](ARCHITECTURE.md) / [DEPLOYMENT.md](DEPLOYMENT.md)
- **定性レビューのモデル**: Gemini 3.8 Flash (`gemini-3.8-flash`、Gemini Developer API / `google-genai` SDK、Web UI では既定ON)

---

## チェック体系（3層構成）

### 1. 基本機械チェック（10チェッカー）
| # | チェッカー ID | 名称 | 主な検出内容 | CLI既定 | Web UI既定 |
|---:|---|---|---|:---:|:---:|
| 1 | `metadata` | メタデータ | 作成者・会社名(`app.xml` Company)・最終更新者・カスタムプロパティ(`MSIP_Label_*`除く)・Wordコメント・変更履歴・PDF `/Info` | ON | OFF |
| 2 | `internal-content` | 内部コンテンツ | スピーカーノート（危険ワード→HIGH／要注意ワード→MEDIUM）、非表示スライド、PPT/Wordコメント | ON | ON |
| 3 | `url-contamination` | URL汚染 | `utm_source=chatgpt.com` 等のAI由来クエリ、AI会話URL、`fbclid`/`gclid` 等のトラッキング（表示文字裏のリンク先URLも含む） | ON | ON |
| 4 | `ai-trace` | AI生成痕跡 | 日英AI定型句、knowledge cutoff言及、Markdown残骸（複数行バレット等）、絵文字過多 | ON | ON |
| 5 | `numeric-integrity` | 数値整合性 | 円グラフ合計≠100%、100%積上げ合計、通貨単位混在、`%`/`pp`混在、表の行・列・小計の再計算 | ON | ON |
| 6 | `consulting-style` | コンサル作法(文体) | タイトル体言止め、表記ゆれ（11グループ）、景表法リスク表現、曖昧表現多用、敬体/常体混在、日付書式混在、全半角混在 | ON | ON |
| 7 | `consulting-layout` | コンサル作法(体裁) | タイトル/ページ番号欠落、フォント種類過多（スライド内3種以上/全体5種以上）、極小文字（8pt/10pt未満） | ON | ON |
| 8 | `copyright` | 著作権リスク | 100文字以上の本文で出典記載なし、画像・表で出典記載なし（©フッターは出典扱いしない） | ON | OFF |
| 9 | `url-liveness` | URL死活 | 全URLを HEAD（失敗時 GET フォールバック、5秒タイムアウト、10並列）で到達確認 | ON | OFF |
| 10 | `verifiable-claim` | 検証要主張 | 出典記載のない箇所の数値・日付・ランキング主張を抽出（人間による裏取り補助） | ON | ON |

### 2. 戦略コンサル品質ルール（`strategy` チェッカー・ローカル機械判定）
`scripts/strategy_checks.py` により、外部API通信なしで以下10項目を自動判定（CLI・Web UI とも既定ON、CLIは `--no-strategy` で無効化可）：
- タイトル長超過（40文字超） / タイトル内複数文（句点混在） / 曖昧・主語なしタイトル
- バレット・段落過多（Miller's Law: 9行超）
- 結論・提言スライド欠落 / アジェンダと後続セクションの不整合 / スライド数不足
- カタカナ多用（密度20%以上かつユニーク5語以上）
- 予測・試算スライドにおける前提条件キーワード不在
- エグゼクティブサマリー欠落（5枚以上のPPTXで冒頭4枚以内に要旨がない）

### 3. AI定性レビュー（`llm-review` チェッカー・Tier-1 MD/Partner視点 15観点）
資料の構造データ（`_aicheck.json`）をもとに、以下の15観点を網羅レビュー（各観点につき最低1件の指摘または「該当なし」の根拠宣言が必須）：
1. `pyramid`（ピラミッド原則） / 2. `mece`（MECE） / 3. `so-what`（So What? / Why So?） / 4. `issue-tree`（Issue Tree / Key Question） / 5. `logic-leap`（ロジックの飛躍） / 6. `data-rigor`（数値の出所と粒度） / 7. `framework`（フレームワーク整合） / 8. `action`（アクションの具体性） / 9. `feasibility`（実行可能性） / 10. `balance`（構成バランス） / 11. `client-view`（顧客視点） / 12. `alternatives`（代替案の提示） / 13. `premise`（前提・限界の開示） / 14. `story-line`（Story Line） / 15. `risk-scenario`（リスクシナリオ）

- **出力構造**: 資料全体の `overall_assessment`（評価グレード A〜D、提出可否、Key Question、ストーリー要旨、強み/弱み、Partner一言）＋ 各指摘8フィールド（`severity`, `category`, `slide`, `quote`, `issue`, `why_it_matters`, `suggestion`, `rewrite_example`）。
- **実行経路の違い**:
  - **Web UI (`webui/app.py`)**: `scripts/llm_review.py` 経由で Gemini 3.8 Flash (`gemini-3.8-flash`) API を呼び出して自動レビュー（既定ON、機密資料ではサイドバーでOFFにする）。
  - **Claude Code / CLI (`scripts/review.py --ai-check-json`)**: 外部LLM APIは呼ばず、出力された `<stem>_aicheck.json` と `<stem>_aicheck_prompt.md` をエージェント自身が読み込んで同一基準でレビューを実施（APIキー不要）。

---

## ローカル実行

### 依存パッケージ
Python 3.14 で動作確認済み。`requirements.txt` の構成は以下のとおり（2026-10 時点の最新版）：

| パッケージ | バージョン | 用途 |
|---|---|---|
| `python-pptx` | `>=1.0.2` | `.pptx` テキスト・表・チャート・ノート・コメント抽出、マーキング、サニタイズ |
| `python-docx` | `>=1.2.0` | `.docx` テキスト・見出し・表抽出、マーキング、サニタイズ |
| `pdfplumber` | `>=0.11.10` | `.pdf` テキスト・表・リンク注釈抽出、メタデータ読取 |
| `requests` | `>=2.34.2` | URL死活チェック（HEAD / GET リクエスト） |
| `pypdf` | `>=6.21.0` | `.pdf` サニタイズ（`/Info`・`/Metadata` 削除） |
| `lxml` | `>=6.1.3` | OOXML（`app.xml` / `custom.xml` / コメント / 変更履歴）のXML解析・サニタイズ |
| `streamlit` | `>=1.66.0` | Web UI (`webui/app.py`) |
| `google-genai` | `>=2.31.0` | Gemini 3.8 Flash 定性レビュー (`scripts/llm_review.py`) |
| `python-dotenv` | `>=1.2.4` | `.env` ファイルからの API キー（`GOOGLE_API_KEY` / `GEMINI_API_KEY`）読込 |

### CLI
```bash
py -m pip install -r requirements.txt
py scripts/review.py path/to/file.pptx

# サニタイズ版＋AIチェックJSONも生成し、HIGHがあれば終了コード1
py scripts/review.py path/to/file.docx --sanitize --ai-check-json --fail-on HIGH
```

#### CLIオプション一覧
| オプション | 説明 |
|---|---|
| `--skip-liveness` | URL死活チェック（HEAD/GET通信）をスキップ |
| `--out-dir DIR` | 出力先ディレクトリを指定（既定: 入力ファイルと同じディレクトリ） |
| `--sanitize` | メタデータ・コメント・変更履歴を削除した `<stem>_sanitized.<ext>` を生成し、再オープン・再検出で事後検証（`verify: OK`）を実行 |
| `--ai-check-json` | 定性レビュー用の構造化データ `<stem>_aicheck.json` と手順書 `<stem>_aicheck_prompt.md` を生成 |
| `--no-strategy` | 戦略コンサル品質ルール（`strategy_checks.py`）をスキップ |
| `--fail-on {HIGH,MEDIUM,LOW,INFO}` | 指定レベル以上の指摘が存在する場合に終了コード `1` を返す（入力・依存エラー時は `2`） |

### Web UI
```bash
py -m pip install -r requirements.txt
py -m streamlit run webui/app.py
```
ブラウザで `http://localhost:8501` が開きます。

### テスト
```bash
py -m pip install -r requirements.txt pytest
py -m pytest tests/ -v
```
外部APIを叩かないスモークテスト（`tests/test_smoke.py`）および不具合の回帰テスト（`tests/test_regressions.py`）を実行します。

---

## Cloud Run デプロイ

### 現在のデプロイ運用（モノレポ + Workload Identity Federation）

このフォルダは共有スキル集リポジトリ（`iida-masashi/skills`、ローカル名 `claude-gemini-skills`）のサブフォルダとして管理されています。
CI/CD ワークフローはリポジトリ直下の [`.github/workflows/deliverable-review-deploy.yml`](../.github/workflows/deliverable-review-deploy.yml) で定義されています。

- **トリガー**:
  - `main` ブランチへの push のうち `deliverable-review/**` または `.github/workflows/deliverable-review-deploy.yml` が変更されたとき
  - 手動実行: GitHub Actions > **"Deploy deliverable-review to Cloud Run"** > **Run workflow**
- **パイプライン**: `test`（`pytest -q tests`、外部API不要）➔ `build`（Dockerビルド・Artifact Registryへpush）➔ `deploy`（Cloud Runデプロイ）。テスト失敗時はビルド・デプロイを行わない。
- **認証方式**: Workload Identity Federation（リポジトリ Secrets `GCP_WIF_PROVIDER` / `GCP_DEPLOYER_SA`）。サービスアカウントキー（`GCP_SA_KEY`）は使用しない。
- **サービスアカウント分離**:
  - デプロイ実行用: `anaplan-skill-deployer@trim-opus-407712.iam.gserviceaccount.com`
  - Cloud Run ランタイム用: `deliverable-review-runtime@trim-opus-407712.iam.gserviceaccount.com`（権限は Secret Manager の `GEMINI_API_KEY` 読み取りのみ）

### Cloud Run 構成仕様

| 項目 | 値 |
|---|---|
| GCPプロジェクト | `trim-opus-407712` |
| リージョン | `asia-northeast1` (東京) |
| Artifact Registry リポジトリ | `apps` |
| Cloud Run サービス名 | `deliverable-review` |
| コンテナイメージ | `asia-northeast1-docker.pkg.dev/trim-opus-407712/apps/deliverable-review` |
| ベースイメージ | `python:3.14-slim` (`Dockerfile`) |
| ランタイム SA | `deliverable-review-runtime@trim-opus-407712.iam.gserviceaccount.com` |
| Secret マウント | `GOOGLE_API_KEY=GEMINI_API_KEY:latest` |
| 認証 | **完全公開** (`--allow-unauthenticated`) ⚠ Backlog: IAP化 |
| メモリ / CPU | 1 GiB / 1 vCPU |
| 最小 / 最大インスタンス | 0 / 1 (セッション一貫性優先、コスト抑制) |
| タイムアウト | 300秒 |

> ℹ️ 初回構築時の手順や運用コマンド（ログ確認・ロールバック・停止等）の詳細は [DEPLOYMENT.md](DEPLOYMENT.md) を参照してください。

---

## Backlog（TODO）

- [ ] **認証追加**: IAP (Identity-Aware Proxy) による Google アカウントログイン必須化
- [x] **WIF への移行**: リポジトリ直下のワークフローで Workload Identity Federation を使用（2026-10）
- [x] **ランタイムSAの最小権限化**: 専用SA `deliverable-review-runtime` に分離（2026-10）
- [ ] **監査ログ**: アップロードされたファイル名・処理時刻・ユーザーを Cloud Logging に出力
- [ ] **レート制限**: Cloud Armor または Streamlit 内で同一IPからの連続アップロードを制限
- [ ] **VPC内限定化**: 社内VPNからのみアクセス可能に
- [ ] **容量制限**: Cloud Run のリクエスト上限 32MB を超えるファイルへの対応（Cloud Storage 経由のアップロード等）
- [ ] **OCR対応**: 画像化スライド（テキスト抽出不可）の Tesseract / Vision API 経由チェック
- [ ] **URLの秘匿運用**: 現在は完全公開のため、URLを公開しないように注意喚起する仕組み

---

## セキュリティ注意事項

- 現在 **完全公開** (`unauthenticated`) のため、URL を知っている第三者がアクセス可能。
- URL を意図せず漏らさないこと（Slack、GitHub Issue、ブラウザ履歴共有、検索エンジンなど）。
- アップロードファイルは Cloud Run インスタンスのメモリ・一時領域（`tempfile`）上で処理され、Cloud Storage 等へは保存されない（レスポンス返却・プロセス終了時に破棄、永続化なし）。
- Web UI の「Gemini 3.8 Flash 定性レビュー」は**既定ON**で、有効な間はスライド本文が Google Gemini API に送信される（Cloud Run には Secret Manager 経由で `GOOGLE_API_KEY` を設定済み）。公開URLのため、アップロードのたびにこのキーで課金される。**機密資料ではサイドバーで OFF にしてから使用すること**。

---

## ファイル構成

```text
deliverable-review/
├── SKILL.md                  # スキル定義・Claude Code ワークフロー
├── CHECKS.md                 # 10チェッカーの検出パターン・Severity詳細カタログ
├── ARCHITECTURE.md           # 内部設計・データフロー・モジュール責務・拡張ガイド
├── DEPLOYMENT.md             # Cloud Run デプロイ記録・運用コマンド
├── README.md                 # このファイル
├── Dockerfile                # Cloud Run コンテナ定義 (python:3.14-slim)
├── .dockerignore
├── .gitignore
├── requirements.txt          # Python依存パッケージ定義
├── scripts/                  # CLI・コアロジック
│   ├── review.py             # CLIエントリポイント・Markdownレポート生成・パイプライン制御
│   ├── extractors.py         # .pptx / .docx / .pdf テキスト・表・ハイパーリンク抽出
│   ├── patterns.py           # 正規表現パターン集約（URL汚染・AI痕跡・出典・検証要主張）
│   ├── checkers.py           # 基本5チェッカー + Finding型 + run_all() 統合
│   ├── numeric_integrity.py  # 数値整合性チェック（グラフ合計・表の行/列/小計再計算・単位混在）
│   ├── metadata.py           # メタデータ検出 + サニタイズ（lxml編集・変更履歴承諾・事後検証）
│   ├── internal_content.py   # ノート・非表示スライド・コメント抽出と危険ワード重要度判定
│   ├── style_checks.py       # コンサル作法(文体)（体言止め・表記ゆれ・景表法・曖昧表現等）
│   ├── layout_checks.py      # コンサル作法(体裁)（タイトル/ページ番号欠落・フォント数・極小文字）
│   ├── strategy_checks.py    # 戦略コンサル品質ルール10項目（ローカル機械判定）
│   ├── ai_check_extract.py   # AIチェック用スライド構造JSON抽出・レビュー手順書生成
│   ├── llm_review.py         # Gemini 3.8 Flash による15観点定性レビュー実行
│   ├── markers.py            # .pptx / .docx への指摘マーキング付きコピー生成
│   └── _smoke_make_sample.py # テスト用サンプルPPTX生成スクリプト
├── webui/
│   └── app.py                # Streamlit Web UI（アップロード・チェック・定性レビュー・DL）
└── tests/
    ├── test_smoke.py         # pytest スモークテスト（外部API不要）
    └── test_regressions.py   # 不具合の回帰テスト（サニタイズ・表計算・コメント対応等）

（Cloud Run 自動デプロイ用ワークフローはリポジトリ直下 .github/workflows/deliverable-review-deploy.yml）
```
