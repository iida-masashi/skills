# 設定ガイド - Anaplan History Audit

## 📋 現在の設定

### アクティブなモデル

現在、以下の1つのモデルが設定されています：

```python
ModelConfig(
    ws_id="your_workspace_id_1",
    m_id="your_model_id_1",
    action_id="your_action_id",
    file_suffix="SOP_TR",
    users_csv="Users.csv",
    model_name="【TR】S&OP"
)
```

### 設定項目の説明

| 項目 | 値 | 説明 |
|------|-----|------|
| **ws_id** | `your_workspace_id_1` | ワークスペースID |
| **m_id** | `your_model_id_1` | モデルID |
| **action_id** | `your_action_id` | エクスポートアクションID |
| **file_suffix** | `SOP_TR` | 出力ファイルの接尾辞 |
| **users_csv** | `Users.csv` | ユーザー情報CSVファイル名 |
| **model_name** | `【TR】S&OP` | モデルの表示名 |

---

## 🔧 モデルの追加方法

### 方法1: スクリプト内で直接追加

`HistoryAudit_Scheduled.py` の `MODELS` リストに追加：

```python
MODELS = [
    # 既存のモデル
    ModelConfig(
        ws_id="your_workspace_id_1",
        m_id="your_model_id_1",
        action_id="your_action_id",
        file_suffix="SOP_TR",
        users_csv="Users.csv",
        model_name="【TR】S&OP"
    ),

    # 新しいモデルを追加
    ModelConfig(
        ws_id="your_workspace_id",
        m_id="your_model_id",
        action_id="your_action_id",
        file_suffix="new_model",
        users_csv="Users.csv",
        model_name="新しいモデル"
    ),
]
```

### 方法2: 外部設定ファイルを使用（推奨）

1. `config.example.py` をコピー：
   ```bash
   cp config.example.py config.py
   ```

2. `config.py` を編集してモデルを追加

3. スクリプトを修正して外部設定を読み込む（オプション）

---

## 🔍 設定値の見つけ方

### 1. ワークスペースID (ws_id)

**方法A: ブラウザのURLから**
```
https://anaplan.com/ws/your_workspace_id_1/models/...
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                      これがワークスペースID
```

**方法B: Anaplan API経由**
```bash
curl -X GET "https://api.anaplan.com/2/0/workspaces" \
  -H "Authorization: AnaplanAuthToken YOUR_TOKEN"
```

### 2. モデルID (m_id)

**方法A: ブラウザのURLから**
```
https://anaplan.com/ws/.../models/your_model_id_1
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                  これがモデルID
```

**方法B: Anaplan API経由**
```bash
curl -X GET "https://api.anaplan.com/2/0/workspaces/YOUR_WS_ID/models" \
  -H "Authorization: AnaplanAuthToken YOUR_TOKEN"
```

### 3. アクションID (action_id)

Anaplanの管理画面で：
1. モデルを開く
2. Actions → Export → 対象のエクスポートアクションを選択
3. URLまたはAPI経由でIDを確認

**API経由**
```bash
curl -X GET "https://api.anaplan.com/2/0/workspaces/YOUR_WS_ID/models/YOUR_M_ID/exports" \
  -H "Authorization: AnaplanAuthToken YOUR_TOKEN"
```

---

## ⚙️ パフォーマンス設定

### 現在の設定

```python
@dataclass
class Config:
    output_folder: str = "./HistoryAudit"
    user_email: str = "your_email@example.com"
    password: str = "your_password"
    timeout: int = 300              # 5分
    log_level: int = logging.INFO
    chunk_size: int = 50000         # 50,000行/チャンク
    max_workers: int = 4            # 最大4並列
```

### チューニングガイド

#### メモリが少ない環境（4GB以下）
```python
chunk_size: int = 10000   # より小さいチャンク
max_workers: int = 2      # 並列数を減らす
```

#### メモリが豊富な環境（16GB以上）
```python
chunk_size: int = 100000  # より大きいチャンク
max_workers: int = 8      # より多くの並列処理
```

#### 処理速度を最優先
```python
chunk_size: int = 100000
max_workers: int = os.cpu_count()  # 全CPUコアを使用
log_level: int = logging.WARNING   # ログを最小化
```

#### 安定性を最優先
```python
chunk_size: int = 10000
max_workers: int = 1      # 並列処理なし
timeout: int = 600        # より長いタイムアウト
```

---

## 🔐 認証情報の管理

### セキュリティのベストプラクティス

#### 1. 環境変数を使用（推奨）

**設定方法（Windows）:**
```batch
setx ANAPLAN_EMAIL "your_email@example.com"
setx ANAPLAN_PASSWORD "your_password"
```

**スクリプトで使用:**
```python
import os

@dataclass
class Config:
    user_email: str = os.getenv("ANAPLAN_EMAIL", "default@example.com")
    password: str = os.getenv("ANAPLAN_PASSWORD", "default_password")
```

#### 2. 設定ファイルを使用

**config.py を作成（.gitignoreに追加）:**
```python
ANAPLAN_EMAIL = "your_email@example.com"
ANAPLAN_PASSWORD = "your_password"
```

**スクリプトで読み込み:**
```python
try:
    from config import ANAPLAN_EMAIL, ANAPLAN_PASSWORD
except ImportError:
    ANAPLAN_EMAIL = "default@example.com"
    ANAPLAN_PASSWORD = "default_password"
```

---

## 📊 利用可能なモデル例

以下は `config.example.py` に記載されている利用可能なモデルの例です：

### 1. TR S&OP Model（現在有効）
- **ワークスペース**: `your_workspace_id_1`
- **モデル**: `your_model_id_1`
- **アクション**: `your_action_id`

### 2. PRD S&OP Model
- **ワークスペース**: `your_workspace_id_2`
- **モデル**: `your_model_id_2`
- **アクション**: `your_action_id`

### 3. Sales TR S&OP Model
- **ワークスペース**: `your_workspace_id_1`
- **モデル**: `your_model_id_3`
- **アクション**: `your_action_id`

### 4. SCM TR S&OP Model
- **ワークスペース**: `your_workspace_id_1`
- **モデル**: `your_model_id_4`
- **アクション**: `your_action_id`

### 5. BP Models
- **PRD BP**: ワークスペース `your_workspace_id_3`
- **TR BP**: ワークスペース `your_workspace_id_1`

---

## 🎯 使用例

### 例1: 単一モデルの実行（現在の設定）

```python
MODELS = [
    ModelConfig(
        ws_id="your_workspace_id_1",
        m_id="your_model_id_1",
        action_id="your_action_id",
        file_suffix="SOP_TR",
        users_csv="Users.csv",
        model_name="【TR】S&OP"
    ),
]
```

**実行:**
```bash
python HistoryAudit_Scheduled.py
```

**出力:**
- `202512151234SOP_TR.tsv`
- `202512151234SOP_TR_summary.csv`
- `202512151234all_summary.csv`
- `202512151234all_summary_dashboard.html`

### 例2: 複数モデルの並列実行

```python
MODELS = [
    ModelConfig(..., model_name="【TR】S&OP"),
    ModelConfig(..., model_name="【PRD】S&OP"),
    ModelConfig(..., model_name="【TR】BP"),
]
```

**実行時間:**
- 単一モデル: 25秒
- 3モデル並列: 約35秒（従来の75秒から改善）

### 例3: 異なるユーザーCSVを使用

```python
MODELS = [
    ModelConfig(
        ...,
        users_csv="Users.csv",      # S&OP用
        model_name="【TR】S&OP"
    ),
    ModelConfig(
        ...,
        users_csv="UsersBP.csv",    # BP用
        model_name="【TR】BP"
    ),
]
```

---

## 🔧 トラブルシューティング

### 問題: 認証エラー

**解決方法:**
1. `user_email` と `password` が正しいか確認
2. Anaplanアカウントの権限を確認
3. APIアクセスが有効か確認

### 問題: モデルが見つからない

**解決方法:**
1. `ws_id` と `m_id` が正しいか確認
2. ブラウザでモデルにアクセスできるか確認
3. APIトークンの権限を確認

### 問題: エクスポートアクションが実行されない

**解決方法:**
1. `action_id` が正しいか確認
2. エクスポートアクションが有効か確認
3. タイムアウト設定を延長

---

## 📝 設定変更のチェックリスト

新しいモデルを追加する際のチェックリスト：

- [ ] ワークスペースIDを確認
- [ ] モデルIDを確認
- [ ] エクスポートアクションIDを確認
- [ ] 適切なfile_suffixを設定
- [ ] 正しいusers_csvファイルを指定
- [ ] わかりやすいmodel_nameを設定
- [ ] テスト実行して動作確認
- [ ] 本番環境で実行

---

**最終更新**: 2025年12月15日
**バージョン**: 2.0
