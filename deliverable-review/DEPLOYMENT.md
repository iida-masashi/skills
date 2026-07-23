# Deployment Record

本ドキュメントは、`deliverable-review` を Cloud Run へ初回デプロイした際の
作業記録・構成詳細・運用手順を残したもの。

- **初回デプロイ**: 2026-04-22
- **実行者**: Iida Masashi
- **環境**: Windows 11 / gcloud CLI / gh CLI

---

## 🌐 稼働中サービス

| 項目 | 値 |
|---|---|
| **Service URL** | <https://deliverable-review-wecljomxda-an.a.run.app> |
| **GitHub Repo** | <https://github.com/<your-org>/<your-repo>> (Private) |
| **Default Branch** | `main` |
| **Initial Commit** | `11241a8` |

### ヘルスチェック
```
GET /_stcore/health  → 200 "ok"  (267ms)
```

---

## 構成 (as deployed)

### GCP

| リソース | 値 |
|---|---|
| プロジェクト | `trim-opus-407712` |
| リージョン | `asia-northeast1` (東京) |
| Artifact Registry | `apps` (docker format) |
| イメージ | `asia-northeast1-docker.pkg.dev/trim-opus-407712/apps/deliverable-review:<short-sha>` |
| Cloud Run サービス | `deliverable-review` |
| 認証 | **`--allow-unauthenticated`** (完全公開) ⚠ Backlog: IAP化 |
| メモリ | 1 GiB |
| CPU | 1 vCPU |
| Port | 8080 |
| タイムアウト | 300秒 |
| Min / Max instances | 0 / 1 |

### サービスアカウント

| SA | 用途 | 付与ロール |
|---|---|---|
| `deliverable-review-deployer@trim-opus-407712.iam.gserviceaccount.com` | GitHub Actions → GCP デプロイ | `run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser` |
| `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` | Cloud Run runtime（Gemini Secret 読取） | `secretmanager.secretAccessor`（`GEMINI_API_KEY`限定） |

### Secret Manager (Gemini APIキー)

Cloud Run ランタイムで `GOOGLE_API_KEY` 環境変数として Gemini 3.1 Pro 定性レビューに使用。

| 項目 | 値 |
|---|---|
| Secret ID | `GEMINI_API_KEY` |
| Region | `automatic` replication |
| マウント方式 | `--set-secrets "GOOGLE_API_KEY=GEMINI_API_KEY:latest"` (環境変数) |

⚠ **セキュリティ警告**: Cloud Run は `--allow-unauthenticated` のためURLを知る第三者が Gemini APIキーを介して無制限にレビューを実行可能。コスト消費・漏洩リスクがあるため、将来的にIAP化/レート制限/VPC内限定化が必須。

#### 初回セットアップコマンド

```bash
PROJECT=trim-opus-407712
gcloud services enable secretmanager.googleapis.com --project=$PROJECT

# APIキーを登録（.env から読み取る例）
gcloud secrets create GEMINI_API_KEY --replication-policy=automatic --project=$PROJECT
grep "^GOOGLE_API_KEY=" ".env" | cut -d= -f2- \
  | gcloud secrets versions add GEMINI_API_KEY --data-file=- --project=$PROJECT

# Cloud Run のデフォルト compute SA に Secret Accessor を付与
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding GEMINI_API_KEY \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=$PROJECT
```

### 有効化済み GCP API

- `artifactregistry.googleapis.com`
- `run.googleapis.com`
- `iamcredentials.googleapis.com`

### GitHub Secrets

| Name | 内容 |
|---|---|
| `GCP_SA_KEY` | 上記 SA のキー JSON（ローカルキーはデプロイ後に削除済） |

---

## デプロイフロー

```
ローカル
  └─ git push origin main
        ↓
GitHub Actions (.github/workflows/deploy.yml)
  ├─ Checkout
  ├─ google-github-actions/auth@v2 (GCP_SA_KEY)
  ├─ docker build -t asia-northeast1-docker.pkg.dev/.../deliverable-review:<sha>
  ├─ docker push (:sha + :latest)
  └─ gcloud run deploy --image=<sha> --allow-unauthenticated
        ↓
Cloud Run (asia-northeast1)
  └─ https://deliverable-review-wecljomxda-an.a.run.app
```

- `main` ブランチへの push で自動デプロイ
- `workflow_dispatch` で GitHub UI からも手動起動可能

---

## 運用コマンド

### サービスURL取得
```bash
gcloud run services describe deliverable-review \
  --region=asia-northeast1 \
  --project=trim-opus-407712 \
  --format='value(status.url)'
```

### 最新ログ
```bash
gcloud run services logs tail deliverable-review \
  --region=asia-northeast1 \
  --project=trim-opus-407712
```

### 手動デプロイ
```bash
gh workflow run deploy.yml --repo <your-org>/<your-repo> --ref main
gh run watch --repo <your-org>/<your-repo>
```

### ロールバック（直前のイメージ `:latest` に戻す）
```bash
gcloud run services update deliverable-review \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/trim-opus-407712/apps/deliverable-review:<前のSHA>
```

過去イメージ一覧：
```bash
gcloud artifacts docker images list \
  asia-northeast1-docker.pkg.dev/trim-opus-407712/apps/deliverable-review \
  --include-tags
```

### サービス停止 (インスタンスを完全に0に)
```bash
# 一時停止（料金停止）
gcloud run services update deliverable-review \
  --region=asia-northeast1 \
  --min-instances=0 --max-instances=0

# 再開
gcloud run services update deliverable-review \
  --region=asia-northeast1 \
  --min-instances=0 --max-instances=1
```

### サービス完全削除
```bash
gcloud run services delete deliverable-review --region=asia-northeast1
```

---

## 初回セットアップで実行したコマンド（再現手順）

参考として、今回実施したセットアップコマンドを時系列で記録：

```bash
# 1. GCP API 有効化
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  iamcredentials.googleapis.com \
  --project=trim-opus-407712

# 2. Artifact Registry リポジトリ作成
gcloud artifacts repositories create apps \
  --repository-format=docker \
  --location=asia-northeast1 \
  --description="Container images for internal apps" \
  --project=trim-opus-407712

# 3. デプロイ用サービスアカウント作成
gcloud iam service-accounts create deliverable-review-deployer \
  --display-name="Deliverable Review Deployer (CI/CD)" \
  --project=trim-opus-407712

# 4. SA にロール付与 (3つ)
PROJECT=trim-opus-407712
SA=deliverable-review-deployer@${PROJECT}.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding ${PROJECT} \
  --member="serviceAccount:${SA}" --role="roles/run.admin"

gcloud projects add-iam-policy-binding ${PROJECT} \
  --member="serviceAccount:${SA}" --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding ${PROJECT} \
  --member="serviceAccount:${SA}" --role="roles/iam.serviceAccountUser"

# 5. GitHub リポジトリ作成 + push (ローカルで git init/add/commit 済の状態から)
gh repo create <your-org>/<your-repo> \
  --private --source=. --remote=origin \
  --description="Pre-delivery review for consulting deliverables (.pptx/.docx/.pdf)" \
  --push

# 6. SA キー発行 → GitHub Secret 登録 → ローカルキー削除
gcloud iam service-accounts keys create /tmp/gcp-key.json \
  --iam-account=${SA}

gh secret set GCP_SA_KEY --repo <your-org>/<your-repo> < /tmp/gcp-key.json
rm /tmp/gcp-key.json

# 7. デプロイワークフロー起動（任意のpushでも自動起動）
gh workflow run deploy.yml --repo <your-org>/<your-repo> --ref main
gh run watch --repo <your-org>/<your-repo> --exit-status
```

---

## コスト見積り

Cloud Run はリクエスト従量課金で、アイドル時は課金されない。

| 前提 | 値 |
|---|---|
| 月間リクエスト | 100回 (1回あたり約30秒処理) |
| メモリ | 1 GiB |
| 概算 | **月額約 $0 〜 $0.5** (Always Free枠内に収まる可能性大) |

Artifact Registry のストレージ:
- 1イメージあたり約300MB、無料枠0.5GB/月 → 数イメージなら無料
- それを超えても $0.10/GB/月

**実質、無料 ～ 数百円/月** で運用可能。

---

## セキュリティ状況

### 🟢 対応済
- サービスアカウントキー JSON は GitHub Secrets に保存、ローカルから削除済
- `.gitignore` に `gcp-key.json`, `service-account*.json`, `.env`, `*.pem`, `*.key` を登録
- Cloud Run のファイル処理は `tempfile` 経由、インスタンス終了時に破棄（永続化なし）
- リポジトリは Private

### 🔴 未対応（Backlog）
- **認証なし**：URLを知る誰でもアクセス可能
- 監査ログなし：誰がいつ何をアップロードしたか不明
- レート制限なし：大量リクエストで課金暴発の可能性
- サービスアカウントキー運用：WIF 未移行、鍵ローテーションなし

### URL取り扱い注意
完全公開のため、以下で URL を公開しないこと：
- Slack / Teams / メール等の永続チャネル
- GitHub Issue / PR 本文
- ブログ・SNS
- 検索エンジンにクロールされる場所

---

## 今後の改善 (Backlog)

優先度順：

| 優先度 | 項目 | 備考 |
|:---:|---|---|
| 高 | IAP 認証の追加 | Googleアカウントログイン必須化 |
| 高 | レート制限 | Cloud Armor または Streamlit 側で同一IP制限 |
| 中 | Workload Identity Federation 移行 | SA鍵の廃止 |
| 中 | 監査ログ | アップロードファイル名・実行時刻・IPを Cloud Logging へ |
| 中 | 容量制限対応 | Cloud Run の 32MB 制約を超えるファイル (GCS経由) |
| 低 | OCR対応 | 画像化スライドの Tesseract / Vision API 対応 |
| 低 | AIチェック 自動実行 | Claude API 統合（現在は手動） |
| 低 | VPC内限定化 | 社内VPN限定アクセス |
| 低 | CDブランチ保護 | main への直pushをPR必須化 |

---

## トラブルシュート

### デプロイが失敗する
- **permission denied**: SA に `run.admin` / `artifactregistry.writer` / `iam.serviceAccountUser` があるか確認
- **image pull error**: Artifact Registry の location と Dockerfile の image URL が一致するか
- **secret missing**: `gh secret list --repo <your-org>/<your-repo>` で `GCP_SA_KEY` を確認

### サービスにアクセスできない
- `gcloud run services describe deliverable-review --region=asia-northeast1` で `status.url` 確認
- `--allow-unauthenticated` が効いているか: `gcloud run services get-iam-policy ... --region=asia-northeast1`
- ログ確認: `gcloud run services logs tail deliverable-review --region=asia-northeast1`

### ファイルアップロードで413エラー
- Cloud Run のリクエスト上限 32MB を超えている
- → 大きなファイルはローカル CLI を使用、または GCS 経由アップロード (未実装)

### Streamlit の WebSocket 切断
- Cloud Run の `max-instances=1` によりスティッキーセッションを確保しているが、インスタンス再起動時は切断される
- → ブラウザをリロードで復旧

---

## 関連ドキュメント

- [SKILL.md](SKILL.md) — スキル定義・利用者向けガイド
- [CHECKS.md](CHECKS.md) — 10チェッカーのリファレンス
- [ARCHITECTURE.md](ARCHITECTURE.md) — 内部アーキテクチャ
- [README.md](README.md) — リポジトリ概要

---

## 変更履歴

| 日付 | 変更内容 | 関連コミット |
|---|---|---|
| 2026-04-22 | 初回デプロイ (10チェッカー + AIチェック + Web UI + Cloud Run) | `11241a8` |
