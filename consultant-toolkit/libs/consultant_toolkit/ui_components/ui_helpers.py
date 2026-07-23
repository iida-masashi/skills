"""
UI共通ヘルパー

UIコンポーネント間で重複するデータ取得・フォールバック処理・
表示ユーティリティを集約する。ビジネスロジックは financial_metrics に委譲。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from consultant_toolkit.constants import DAYS_PER_YEAR, DEFAULT_TAX_RATE
from consultant_toolkit.financial_metrics import (
    calculate_ccc,
    calculate_roic,
    get_val_safe,
)

# ========================================
# 共通データ構造
# ========================================


@dataclass
class BaseFinancials:
    """UI コンポーネントが共通で使う財務データの集約。"""

    has_real_data: bool = False

    # 収益・コスト
    revenue: float = 100_000_000.0
    cogs: float = 65_000_000.0
    opex: float = 20_000_000.0
    operating_income: float = 15_000_000.0

    # マージン (%)
    cogs_ratio: float = 65.0
    opex_ratio: float = 20.0
    oi_margin: float = 15.0

    # ROIC 関連
    nopat: float = 10_500_000.0
    invested_capital: float = 50_000_000.0
    roic: float = 21.0

    # CCC 関連
    inventory: float = 15_000_000.0
    receivables: float = 12_000_000.0
    payables: float = 8_000_000.0
    dio: float = 60.0
    dso: float = 45.0
    dpo: float = 30.0
    ccc: float = 75.0

    # キャッシュフロー
    capex: float = 5_000_000.0
    ocf: float = 15_000_000.0
    fcf: float = 10_000_000.0

    # メタ
    latest_year: Any = None
    raw_income_statement: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame()
    )
    raw_balance_sheet: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame()
    )


# ========================================
# データ取得
# ========================================

_DEFAULT_FALLBACK = BaseFinancials(has_real_data=False)


def load_base_financials(
    ticker: str,
    load_financial_data: Callable,
    get_val_safe_fn: Callable = get_val_safe,
    get_cashflow_data: Callable | None = None,
    days_per_year: float = DAYS_PER_YEAR,
) -> BaseFinancials:
    """
    財務データを取得し、共通指標を計算して BaseFinancials を返す。

    取得失敗時・データ空の場合はデフォルト値入りの BaseFinancials
    (has_real_data=False) を返す。呼び出し元で st.warning を出すかは任意。

    Args:
        ticker: ティッカーシンボル
        load_financial_data: (ticker) -> (income_statement, balance_sheet)
        get_val_safe_fn: DataFrame から値を安全取得する関数
        get_cashflow_data: (ticker) -> cashflow DataFrame (任意)
        days_per_year: 年間日数定数
    """
    try:
        income_statement, balance_sheet = load_financial_data(ticker)
    except (ConnectionError, KeyError, ValueError):
        return BaseFinancials(has_real_data=False)

    if income_statement.empty:
        return BaseFinancials(has_real_data=False)

    latest_year = income_statement.columns[0]

    # --- 収益・コスト ---
    revenue = get_val_safe_fn(
        income_statement, ["Total Revenue", "Operating Revenue"], latest_year
    )
    cogs = get_val_safe_fn(
        income_statement,
        ["Cost Of Revenue", "Cost of Goods Sold"],
        latest_year,
    )
    opex = get_val_safe_fn(
        income_statement, ["Operating Expense"], latest_year
    )
    oi = get_val_safe_fn(
        income_statement, ["Operating Income"], latest_year
    )

    # --- B/S ---
    inventory = get_val_safe_fn(
        balance_sheet, ["Inventory"], latest_year
    )
    receivables = get_val_safe_fn(
        balance_sheet, ["Accounts Receivable", "Receivables"], latest_year
    )
    payables = get_val_safe_fn(
        balance_sheet, ["Accounts Payable", "Payables"], latest_year
    )
    equity = get_val_safe_fn(
        balance_sheet,
        ["Stockholders Equity", "Total Equity Gross Minority Interest"],
        latest_year,
    )
    debt = get_val_safe_fn(
        balance_sheet, ["Total Debt"], latest_year
    )
    invested_capital = equity + debt

    # --- マージン (safe division) ---
    cogs_ratio = (cogs / revenue * 100) if revenue > 0 else 65.0
    opex_ratio = (opex / revenue * 100) if revenue > 0 else 20.0
    oi_margin = (oi / revenue * 100) if revenue > 0 else 15.0

    # --- ROIC (financial_metrics に委譲) ---
    roic_result = calculate_roic(income_statement, balance_sheet, latest_year)
    if isinstance(roic_result, dict):
        nopat = roic_result.get("nopat", oi * (1 - DEFAULT_TAX_RATE))
        roic_pct = roic_result.get("roic", 0.0) * 100
    else:
        nopat = oi * (1 - DEFAULT_TAX_RATE)
        roic_pct = roic_result * 100 if roic_result else 0.0

    # --- CCC (financial_metrics に委譲) ---
    ccc_result = calculate_ccc(income_statement, balance_sheet, latest_year)
    dio = ccc_result.get("dio", 60.0)
    dso = ccc_result.get("dso", 45.0)
    dpo = ccc_result.get("dpo", 30.0)
    ccc_val = ccc_result.get("ccc", 75.0)

    # --- キャッシュフロー (任意) ---
    capex = 0.0
    ocf = 0.0
    fcf = 0.0
    if get_cashflow_data is not None:
        try:
            cf_data = get_cashflow_data(ticker)
            capex_raw = get_val_safe_fn(
                cf_data,
                ["Capital Expenditure", "Capital Expenditures"],
                latest_year,
            )
            capex = abs(capex_raw)
            ocf = get_val_safe_fn(
                cf_data, ["Operating Cash Flow"], latest_year
            )
            fcf = ocf - capex
        except (ConnectionError, KeyError, ValueError):
            pass

    return BaseFinancials(
        has_real_data=True,
        revenue=revenue,
        cogs=cogs,
        opex=opex,
        operating_income=oi,
        cogs_ratio=cogs_ratio,
        opex_ratio=opex_ratio,
        oi_margin=oi_margin,
        nopat=nopat,
        invested_capital=invested_capital,
        roic=roic_pct,
        inventory=inventory,
        receivables=receivables,
        payables=payables,
        dio=dio,
        dso=dso,
        dpo=dpo,
        ccc=ccc_val,
        capex=capex,
        ocf=ocf,
        fcf=fcf,
        latest_year=latest_year,
        raw_income_statement=income_statement,
        raw_balance_sheet=balance_sheet,
    )


# ========================================
# 表示ユーティリティ
# ========================================


def color_by_sign(
    value: float,
    positive: str = "#2ca02c",
    negative: str = "#d62728",
) -> str:
    """値の正負に応じた色コードを返す。"""
    return positive if value >= 0 else negative


def load_markdown_asset(filename: str, base_dir: str | None = None) -> str:
    """
    assets/texts/ からマークダウンファイルを読み込む。

    Args:
        filename: 読み込むファイル名 (例: "roic_explanation.md")
        base_dir: ベースディレクトリ。None の場合はプロジェクトルートの assets/texts/ を使用。

    Returns:
        ファイル内容の文字列。読み込み失敗時はエラーメッセージ。
    """
    import os

    if base_dir is None:
        # ui_components/ -> consultant_toolkit/ -> libs/ -> project_root/
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "assets",
            "texts",
        )

    file_path = os.path.join(base_dir, filename)
    try:
        if os.path.exists(file_path):
            with open(file_path, encoding="utf-8") as f:
                return f.read()
        return f"Warning: {filename} not found at {file_path}."
    except OSError as e:
        return f"Error loading {filename}: {e}"
