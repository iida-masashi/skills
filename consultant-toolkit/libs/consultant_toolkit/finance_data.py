"""
財務データ取得ユーティリティ

yfinance からの財務データ取得を統一化します。
全スクリプトで一貫したデータ取得インターフェースを提供します。
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf

from .retry import retry_on_error

logger = logging.getLogger(__name__)


@dataclass
class FinancialData:
    """
    財務データの統一フォーマット

    Attributes:
        ticker_symbol: ティッカーシンボル (例: "5988.T")
        info: 企業情報 (辞書形式)
        financials: 損益計算書 (P/L) DataFrame
        balance_sheet: 貸借対照表 (B/S) DataFrame
        cash_flow: キャッシュフロー計算書 DataFrame (オプション)
        history: 株価履歴 DataFrame (オプション)
    """

    ticker_symbol: str
    info: dict[str, Any]
    financials: pd.DataFrame
    balance_sheet: pd.DataFrame
    cash_flow: pd.DataFrame | None = None
    history: pd.DataFrame | None = None


@retry_on_error(max_retries=3, delay=1.0, exceptions=(ConnectionError, TimeoutError))
def fetch_financial_data(
    ticker_symbol: str,
    include_cash_flow: bool = False,
    history_period: str | None = None,
) -> FinancialData | None:
    """
    yfinance から財務データを統一形式で取得

    Args:
        ticker_symbol: ティッカーシンボル (例: "5988.T", "AAPL")
        include_cash_flow: キャッシュフローデータを含めるか (デフォルト: False)
        history_period: 株価履歴期間 (例: "1y", "5y", "max") (デフォルト: None)

    Returns:
        FinancialData | None: 取得成功時は財務データ、失敗時はNone

    Example:
        >>> from consultant_toolkit.finance_data import fetch_financial_data
        >>> data = fetch_financial_data("5988.T", include_cash_flow=True)
        >>> if data:
        ...     print(data.info['longName'])
        ...     roic = calculate_roic(data.financials, data.balance_sheet, ...)
    """
    try:
        ticker = yf.Ticker(ticker_symbol)

        # 必須データ
        info = ticker.info
        financials = ticker.financials
        balance_sheet = ticker.balance_sheet

        if financials.empty or balance_sheet.empty:
            return None

        # オプションデータ
        cash_flow = ticker.cash_flow if include_cash_flow else None
        history = ticker.history(period=history_period) if history_period else None

        return FinancialData(
            ticker_symbol=ticker_symbol,
            info=info,
            financials=financials,
            balance_sheet=balance_sheet,
            cash_flow=cash_flow,
            history=history,
        )
    except (ConnectionError, TimeoutError) as e:
        logger.error(f"Network error fetching {ticker_symbol}: {e}", exc_info=True)
        raise  # Let retry decorator handle it
    except KeyError as e:
        logger.error(f"Data structure error for {ticker_symbol}: {e}", exc_info=True)
        return None
    except ValueError as e:
        logger.error(f"Invalid ticker or data for {ticker_symbol}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching {ticker_symbol}: {e}")
        return None


def fetch_financial_data_batch(
    ticker_symbols: list[str],
    include_cash_flow: bool = False,
    history_period: str | None = None,
    max_workers: int = 5,
) -> dict[str, FinancialData | None]:
    """
    複数企業の財務データを並列取得 (パフォーマンス向上)

    Args:
        ticker_symbols: ティッカーシンボルのリスト
        include_cash_flow: キャッシュフローデータを含めるか
        history_period: 株価履歴期間
        max_workers: 並列実行数 (デフォルト: 5)

    Returns:
        Dict[str, FinancialData | None]: ティッカーシンボル -> 財務データのマッピング

    Example:
        >>> tickers = ["5988.T", "5949.T", "5991.T"]
        >>> results = fetch_financial_data_batch(tickers)
        >>> for ticker, data in results.items():
        ...     if data:
        ...         print(f"{ticker}: {data.info['longName']}")
    """
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(
                fetch_financial_data, ticker, include_cash_flow, history_period
            ): ticker
            for ticker in ticker_symbols
        }

        # Collect results
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                results[ticker] = future.result()
            except Exception as e:
                logger.error(f"Failed to fetch {ticker}: {e}")
                results[ticker] = None

    return results


def get_safe_value(
    df: pd.DataFrame, keys: list, column: Any, default: float = 0.0
) -> float:
    """
    DataFrameから安全に値を取得 (複数キー候補対応)

    financial_metrics.get_val_safe のエイリアス。後方互換のために残す。
    新規コードでは financial_metrics.get_val_safe を直接使用してください。
    """
    from .financial_metrics import get_val_safe

    return get_val_safe(df, keys, column, default)
