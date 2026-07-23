"""
Configuration Example for Anaplan History Audit

このファイルをコピーして config.py として使用してください:
  Windows: copy config.example.py config.py
  Linux/Mac: cp config.example.py config.py

⚠️ セキュリティ注意:
  - config.py には認証情報が含まれるため、Gitにコミットしないでください
  - .gitignore に config.py を追加してください
"""
import logging
import os
from dataclasses import dataclass

# ========================================
# Anaplan認証情報
# ========================================
from dotenv import load_dotenv

# dotenvを利用して親ディレクトリなどの.envから読み込みを試みる
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', '.env'))
load_dotenv(env_path)

ANAPLAN_USER_EMAIL = os.getenv("ANAPLAN_USER", os.getenv("ANAPLAN_USERNAME", ""))
ANAPLAN_PASSWORD = os.getenv("ANAPLAN_PASSWORD", "")


# ========================================
# 出力設定
# ========================================
OUTPUT_FOLDER = "./HistoryAudit"


# ========================================
# パフォーマンス設定
# ========================================
# チャンクサイズ（一度に処理する行数）

# 並列処理のワーカー数
MAX_WORKERS = min(os.cpu_count() or 1, 4)

# APIタイムアウト（秒）
TIMEOUT = 300

# ログレベル
LOG_LEVEL = logging.INFO  # DEBUG, INFO, WARNING, ERROR


# ========================================
# モデル設定
# ========================================
@dataclass
class ModelConfig:
    """モデル設定"""
    ws_id: str          # ワークスペースID
    m_id: str           # モデルID
    action_id: str      # エクスポートアクションID
    file_suffix: str    # 出力ファイルの接尾辞
    users_csv: str      # ユーザー情報CSVファイル名
    model_name: str     # モデルの表示名


# モデル設定リスト
MODELS = [
    # TR S&OP Model（実際のws_id/m_id/action_idに書き換えてください）
    ModelConfig(
        ws_id="your_workspace_id",
        m_id="your_model_id",
        action_id="your_action_id",
        file_suffix="SOP_TR",
        users_csv="Users.csv",
        model_name="【TR】S&OP"
    ),

    # PRD S&OP Model (例 - コメントアウト)
    # ModelConfig(
    #     ws_id="your_workspace_id",
    #     m_id="your_model_id",
    #     action_id="your_action_id",
    #     file_suffix="SOP",
    #     users_csv="Users.csv",
    #     model_name="【PRD】S&OP"
    # ),

    # Sales TR S&OP Model (例 - コメントアウト)
    # ModelConfig(
    #     ws_id="your_workspace_id",
    #     m_id="your_model_id",
    #     action_id="your_action_id",
    #     file_suffix="SOP_SalesTR",
    #     users_csv="Users.csv",
    #     model_name="【Sales TR】S&OP"
    # ),

    # SCM TR S&OP Model (例 - コメントアウト)
    # ModelConfig(
    #     ws_id="your_workspace_id",
    #     m_id="your_model_id",
    #     action_id="your_action_id",
    #     file_suffix="SOP_SCMTR",
    #     users_csv="Users.csv",
    #     model_name="【SCM TR】S&OP"
    # ),

    # BP Model (例 - コメントアウト)
    # ModelConfig(
    #     ws_id="your_workspace_id",
    #     m_id="your_model_id",
    #     action_id="your_action_id",
    #     file_suffix="BP",
    #     users_csv="UsersBP.csv",
    #     model_name="【PRD】BP"
    # ),

    # BP TR Model (例 - コメントアウト)
    # ModelConfig(
    #     ws_id="your_workspace_id",
    #     m_id="your_model_id",
    #     action_id="your_action_id",
    #     file_suffix="BP_TR",
    #     users_csv="UsersBP.csv",
    #     model_name="【TR】BP"
    # ),
]


# ========================================
# 環境別設定の切り替え（オプション）
# ========================================
# 環境変数 ENVIRONMENT で設定を切り替える例
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

if ENVIRONMENT == "development":
    LOG_LEVEL = logging.DEBUG
    MAX_WORKERS = 2
elif ENVIRONMENT == "production":
    LOG_LEVEL = logging.INFO
    MAX_WORKERS = 4
