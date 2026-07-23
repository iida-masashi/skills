"""
環境変数読み込みユーティリティ

プロジェクト標準の.env読み込み機能を提供します。
全スクリプトで統一された環境変数管理を実現します。
"""

import os
import sys
from pathlib import Path


def check_required_env_vars(keys: list[str]) -> None:
    """
    指定された環境変数が設定されているか検証し、不足していればエラーメッセージを出力して終了します。
    """
    missing_keys = [key for key in keys if not get_api_key(key)]
    if missing_keys:
        print(
            f"Error: The following required environment variables are missing: {', '.join(missing_keys)}"
        )
        print("Please set them in your .env file or as environment variables.")
        sys.exit(1)


def load_environment(override: bool = True) -> bool:
    """
    プロジェクト標準の.env読み込み機能

    複数の候補パスから.envファイルを探索し、環境変数として読み込みます。

    Args:
        override: 既存の環境変数を上書きするか (デフォルト: True)

    Returns:
        bool: 読み込み成功時はTrue、.envが見つからない場合はFalse

    Example:
        >>> from consultant_toolkit.env_loader import load_environment
        >>> if load_environment():
        ...     api_key = os.getenv("GOOGLE_API_KEY")
    """
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]

    for env_path in env_paths:
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")

                        if override or key not in os.environ:
                            os.environ[key] = value
            return True
    return False


def get_api_key(env_var: str, fallback: str | None = None) -> str | None:
    """
    API キーの安全な取得

    Args:
        env_var: 環境変数名 (例: "GOOGLE_API_KEY")
        fallback: 見つからない場合のフォールバック値

    Returns:
        str | None: API Key (見つからない場合はfallbackまたはNone)

    Example:
        >>> api_key = get_api_key("GOOGLE_API_KEY")
    """
    return os.getenv(env_var, fallback)
