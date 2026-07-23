"""
Gemini クライアント生成・エラーハンドリング共通モジュール

全スクリプト/UIコンポーネントで Gemini API の利用パターンを統一する。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.genai import Client

logger = logging.getLogger(__name__)

# デフォルトモデル (変更時はここだけ修正)
DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"


def create_gemini_client(
    api_key: str | None = None,
    *,
    use_vertex: bool = False,
    project: str | None = None,
    location: str = "us-central1",
) -> Client:
    """
    Gemini クライアントを生成する。

    Args:
        api_key: API キー。None の場合は GOOGLE_API_KEY 環境変数を使用。
        use_vertex: Vertex AI を使用するか。
        project: GCP プロジェクト ID (Vertex AI 使用時)。
        location: GCP リージョン (Vertex AI 使用時)。

    Returns:
        genai.Client インスタンス

    Raises:
        ImportError: google-genai がインストールされていない場合
        ValueError: API キーが未設定の場合
    """
    from google import genai

    if use_vertex:
        project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        return genai.Client(vertexai=True, project=project, location=location)

    resolved_key = api_key or os.getenv("GOOGLE_API_KEY", "")
    if not resolved_key:
        raise ValueError("Gemini API キーが設定されていません。")

    return genai.Client(api_key=resolved_key, vertexai=False)


def generate_text(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    use_vertex: bool = False,
    history: list | None = None,
) -> str:
    """
    テキスト生成のショートカット。

    Args:
        prompt: プロンプト文字列
        api_key: API キー
        model: 使用モデル
        use_vertex: Vertex AI を使用するか
        history: 対話履歴 (google-genai SDK 形式)

    Returns:
        生成テキスト
    """
    client = create_gemini_client(api_key=api_key, use_vertex=use_vertex)
    contents = history if history else prompt
    response = client.models.generate_content(model=model, contents=contents)
    return response.text or ""


def handle_gemini_api_error(e: Exception, context: str = "") -> str:
    """
    Gemini API エラーを統一的に処理し、ユーザー向けメッセージを返す。

    Args:
        e: 発生した例外
        context: エラー文脈の説明

    Returns:
        ユーザー向けエラーメッセージ文字列
    """
    status_code = getattr(e, "status_code", "")
    prefix = f"{context}: " if context else ""

    if status_code == 429:
        return f"{prefix}API レート制限に達しました。しばらく待ってから再試行してください。"
    if status_code in (401, 403):
        return f"{prefix}APIキーが無効または権限がありません。設定を確認してください。"
    return f"{prefix}Gemini API エラー ({status_code}): {e}"
