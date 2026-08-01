# deliverable-review

顧客提出前のコンサル資料（.pptx / .docx / .pdf）を10観点でチェックし、
Markdownレポート・マーキング付きコピー・サニタイズ済みファイル・
AIチェック 定性レビュー用JSONを生成する。

- 🌐 **Web UI (稼働中)**: <https://deliverable-review-wecljomxda-an.a.run.app>
- **CLI**: `scripts/review.py`
- **Web UI (ローカル)**: `webui/app.py`
- **ドキュメント**: [SKILL.md](SKILL.md) / [CHECKS.md](CHECKS.md) / [ARCHITECTURE.md](ARCHITECTURE.md) / [DEPLOYMENT.md](DEPLOYMENT.md)

このリポジトリは [`<your-org>/<your-repo>`](https://github.com/<your-org>/<your-repo>) で管理され、
GitHub Actions により Google Cloud Run (`asia-northeast1`) へ自動デプロイされる。

---

## ローカル実行

### CLI
```bash
pip install -r requirements.txt
python scripts/review.py path/to/file.pptx
```

### Web UI
```bash
pip install -r requirements.txt
streamlit run webui/app.py
```

### テスト
```bash
pip install -r requirements.txt pytest
pytest tests/ -v
```

外部APIを叩かないスモークテスト。Gemini 3.1 Pro レビューは別途手動で検証。

---

## Cloud Run デプロイ

### 構成

| 項目 | 値 |
|---|---|
| GCPプロジェクト | `trim-opus-407712` |
| リージョン | `asia-northeast1` (東京) |
| Artifact Registry リポジトリ | `apps` |
| Cloud Run サービス名 | `deliverable-review` |
| イメージ | `asia-northeast1-docker.pkg.dev/trim-opus-407712/apps/deliverable-review` |
| 認証 | **完全公開** (allow-unauthenticated) ⚠ Backlog: IAP化 |
| メモリ / CPU | 1 GiB / 1 vCPU |
| 最大インスタンス | 1 (セッション一貫性優先、コスト抑制) |
| タイムアウト | 300秒 |

### 初回セットアップ（一度だけ実行）

> ℹ️ **2026-04-22 実施済み**。再現手順とデプロイ結果は [DEPLOYMENT.md](DEPLOYMENT.md) 参照。以下は同一構成を別プロジェクトで再構築するとき用の参考手順。

ローカル PC に `gcloud` CLI が必要 ([インストール](https://cloud.google.com/sdk/docs/install))。

```bash
# 1. 認証
gcloud auth login
gcloud config set project trim-opus-407712

# 2. 必要APIを有効化
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com

# 3. Artifact Registry リポジトリ作成
gcloud artifacts repositories create apps \
  --repository-format=docker \
  --location=asia-northeast1 \
  --description="Container images for internal apps"

# 4. デプロイ用サービスアカウント作成
gcloud iam service-accounts create deliverable-review-deployer \
  --display-name="Deliverable Review Deployer (CI/CD)"

# 5. 必要な権限を付与
PROJECT=trim-opus-407712
SA=deliverable-review-deployer@${PROJECT}.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding ${PROJECT} \
  --member="serviceAccount:${SA}" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding ${PROJECT} \
  --member="serviceAccount:${SA}" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding ${PROJECT} \
  --member="serviceAccount:${SA}" \
  --role="roles/iam.serviceAccountUser"

# 6. サービスアカウントキー発行（GitHub Secrets に登録）
gcloud iam service-accounts keys create gcp-key.json \
  --iam-account=${SA}

cat gcp-key.json   # ← この JSON をまるごとコピー
```

Gemini 3.1 Pro 定性レビュー（Web UI）を使う場合は Secret Manager に `GOOGLE_API_KEY` の設定が別途必要。手順は [DEPLOYMENT.md](DEPLOYMENT.md) の「Secret Manager (Gemini APIキー)」を参照。

### GitHub リポジトリ設定

1. <https://github.com/<your-org>/<your-repo>> を新規作成（Private 推奨）

2. ローカルから push:
   ```bash
   cd ~/.claude/skills/deliverable-review
   git init
   git branch -M main
   git add .
   git commit -m "Initial commit: deliverable-review with Cloud Run deploy"
   git remote add origin https://github.com/<your-org>/<your-repo>.git
   git push -u origin main
   ```

3. GitHub > リポジトリ > Settings > Secrets and variables > Actions で **Repository secret** を追加:
   - Name: `GCP_SA_KEY`
   - Value: 手順6で生成した `gcp-key.json` の**中身全文**を貼り付け

4. 手順6の `gcp-key.json` は **ローカルからも削除**しておく（`git status` でトラックされていないことを確認）。

### デプロイ

- `main` ブランチへの push で自動デプロイ
- GitHub リポジトリ > Actions タブでビルドログ確認
- 完了後、Actions 実行結果のサマリにサービス URL が表示される

### 手動デプロイ（GitHub Actions UI から）

GitHub > Actions > "Deploy to Cloud Run" > **Run workflow** ボタン

---

## Backlog（TODO）

- [ ] **認証追加**: IAP (Identity-Aware Proxy) による Google アカウントログイン必須化
- [ ] **WIF への移行**: サービスアカウントキー JSON を廃止し、Workload Identity Federation に
- [ ] **監査ログ**: アップロードされたファイル名・処理時刻・ユーザーを Cloud Logging に出力
- [ ] **レート制限**: Cloud Armor または Streamlit 内で同一IPからの連続アップロードを制限
- [ ] **VPC内限定化**: 社内VPNからのみアクセス可能に
- [ ] **容量制限**: Cloud Run のリクエスト上限 32MB を超えるファイルへの対応（Cloud Storage 経由のアップロード等）
- [ ] **OCR対応**: 画像化スライド（テキスト抽出不可）の Tesseract / Vision API 経由チェック
- [ ] **AIチェック 自動実行**: Claude API 統合（現在は Claude Code が JSON を読んで自分でレビューする運用。Web UI には Gemini 3.1 Pro 経由の定性レビューあり・既定OFF）
- [ ] **URLの秘匿運用**: 現在は完全公開のため、URLを公開しないように注意喚起する仕組み（デプロイ後にURLをSlack等に自動投稿しない等）

---

## セキュリティ注意事項

- 現在 **完全公開** (unauthenticated) のため、URL を知っている第三者がアクセス可能
- URL を意図せず漏らさないこと（Slack、GitHub issue、ブラウザ履歴共有、検索エンジンなど）
- アップロードファイルは Cloud Run インスタンスのメモリ上で処理され、Cloud Storage 等へは保存されない（`tempfile` 経由、プロセス終了時に破棄）
- コンテナが再起動すると一時ファイルは消える（永続化なし）
- サービスアカウントキー `gcp-key.json` は**絶対に git に commit しない**（`.gitignore` で除外済み）
- Web UI の「Gemini 3.1 Pro 定性レビュー」を有効にした場合のみ、スライド本文が Google Gemini API に送信される（Cloud Run には Secret Manager 経由で `GOOGLE_API_KEY` が設定済みのため機能自体は常に呼び出し可能。既定は OFF）。機密資料では OFF のまま使用すること

---

## ファイル構成

```
deliverable-review/
├── SKILL.md             # スキル定義
├── CHECKS.md            # 10チェッカーのリファレンス
├── ARCHITECTURE.md      # 内部設計
├── DEPLOYMENT.md        # Cloud Run デプロイ記録・運用手順
├── README.md            # このファイル
├── Dockerfile           # Cloud Run 用
├── .dockerignore
├── .gitignore
├── .github/
│   └── workflows/
│       └── deploy.yml   # GitHub Actions
├── requirements.txt
├── scripts/             # CLI・コアロジック
│   ├── review.py
│   ├── extractors.py
│   ├── patterns.py
│   ├── checkers.py
│   ├── numeric_integrity.py
│   ├── metadata.py
│   ├── internal_content.py
│   ├── style_checks.py
│   ├── layout_checks.py
│   ├── strategy_checks.py
│   ├── ai_check_extract.py
│   ├── llm_review.py
│   └── markers.py
├── webui/
│   └── app.py           # Streamlit UI
└── tests/
    └── test_smoke.py    # pytest スモーク
```
