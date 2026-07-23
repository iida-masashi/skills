"""
リトライ機構ユーティリティ

ネットワーク障害やAPI rate limitに対応した再試行ロジックを提供します。
"""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_error(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (ConnectionError, TimeoutError),
    logger_instance: logging.Logger | None = None,
) -> Callable:
    """
    エラー時に自動再試行するデコレータ

    Args:
        max_retries: 最大再試行回数
        delay: 初回遅延時間（秒）
        backoff: 遅延時間の倍率（指数バックオフ）
        exceptions: 再試行対象の例外タプル
        logger_instance: ロガーインスタンス

    Returns:
        Callable: デコレートされた関数

    Example:
        >>> @retry_on_error(max_retries=3, delay=1.0)
        ... def fetch_data():
        ...     return requests.get("https://api.example.com/data")
    """
    log = logger_instance or logger

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            func_name = getattr(func, "__name__", str(func))

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries - 1:
                        log.error(
                            f"{func_name} failed after {max_retries} attempts: {e}",
                            exc_info=True,
                        )
                        raise

                    log.warning(
                        f"{func_name} attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
                except Exception as e:
                    # 再試行対象外の例外は即座にraise
                    log.error(
                        f"{func_name} failed with non-retryable error: {e}",
                        exc_info=True,
                    )
                    raise

            # Should never reach here
            raise RuntimeError(f"{func_name} exceeded retry limit")

        return wrapper

    return decorator


def safe_execute[T](
    func: Callable[..., T],
    *args,
    default: T | None = None,
    error_msg: str = "Execution failed",
    logger_instance: logging.Logger | None = None,
    **kwargs,
) -> T | None:
    """
    例外を安全に処理する関数実行ラッパー

    Args:
        func: 実行する関数
        *args: 関数の引数
        default: エラー時のデフォルト戻り値
        error_msg: エラーメッセージ
        logger_instance: ロガーインスタンス
        **kwargs: 関数のキーワード引数

    Returns:
        Optional[T]: 実行結果、またはエラー時はdefault

    Example:
        >>> result = safe_execute(
        ...     risky_function,
        ...     arg1, arg2,
        ...     default=[],
        ...     error_msg="Failed to fetch data"
        ... )
    """
    log = logger_instance or logger

    try:
        return func(*args, **kwargs)
    except Exception as e:
        log.error(f"{error_msg}: {e}", exc_info=True)
        return default


class RetryableError(Exception):
    """再試行可能なエラーを示す基底クラス"""

    pass


class NetworkError(RetryableError):
    """ネットワーク関連のエラー"""

    pass


class APIError(RetryableError):
    """API関連のエラー"""

    pass


class RateLimitError(RetryableError):
    """レート制限エラー"""

    pass
