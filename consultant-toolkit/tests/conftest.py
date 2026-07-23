"""共通テストフィクスチャ。UI コンポーネントのスモークテスト用。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

# ========================================
# Streamlit モック
# ========================================


class _SessionState(dict):
    """Streamlit の session_state を模倣: dict + attribute access。"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        try:
            del self[name]
        except KeyError:
            raise AttributeError(name)

    def __contains__(self, key):
        return dict.__contains__(self, key)


def _make_st_mock() -> MagicMock:
    """Streamlit (st) のモックを構築する。

    st.columns / st.tabs の tuple-unpack、st.cache_data のデコレータ、
    st.slider 等の算術利用に対応。
    """
    m = MagicMock()

    # --- デコレータ系 ---
    m.cache_data = lambda **kw: lambda fn: fn
    m.cache_resource = lambda **kw: lambda fn: fn

    # --- レイアウト系 (tuple-unpack 対応) ---
    def _columns(spec, **kw):
        n = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
        return [MagicMock() for _ in range(n)]

    m.columns.side_effect = _columns
    m.tabs.side_effect = lambda names: [MagicMock() for _ in names]

    # --- 入力ウィジェット: 算術に使われるため実値を返す ---
    m.slider.return_value = 0.0
    m.number_input.return_value = 2023
    m.text_input.return_value = ""
    m.text_area.return_value = "{}"
    m.selectbox.return_value = ""
    m.radio.return_value = ""
    m.select_slider.return_value = ""
    m.checkbox.return_value = False
    m.button.return_value = False
    m.chat_input.return_value = None

    # --- session_state: dict + attribute access (Streamlit 互換) ---
    m.session_state = _SessionState()

    return m


@pytest.fixture()
def st_mock():
    """パッチ不要の st モックインスタンスを返す。"""
    return _make_st_mock()


# ========================================
# 財務データ モック
# ========================================

_YEAR = pd.Timestamp("2024-01-01")
_PREV_YEAR = pd.Timestamp("2023-01-01")


def _make_income_statement(
    revenue: float = 1_000_000,
    cogs: float = 650_000,
    opex: float = 200_000,
    oi: float = 150_000,
    *,
    years: int = 2,
) -> pd.DataFrame:
    """テスト用の損益計算書 DataFrame。"""
    columns = [_YEAR] if years == 1 else [_YEAR, _PREV_YEAR]
    data = {}
    for y in columns:
        data[y] = {
            "Total Revenue": revenue,
            "Operating Revenue": revenue,
            "Cost Of Revenue": cogs,
            "Operating Expense": opex,
            "Operating Income": oi,
            "Gross Profit": revenue - cogs,
            "EBIT": oi,
            "Tax Provision": oi * 0.3,
            "Pretax Income": oi,
            "Net Income": oi * 0.7,
        }
    return pd.DataFrame(data)


def _make_balance_sheet(
    inventory: float = 100_000,
    receivables: float = 80_000,
    payables: float = 60_000,
    equity: float = 500_000,
    debt: float = 200_000,
    total_assets: float = 1_000_000,
    *,
    years: int = 2,
) -> pd.DataFrame:
    """テスト用の貸借対照表 DataFrame。"""
    columns = [_YEAR] if years == 1 else [_YEAR, _PREV_YEAR]
    data = {}
    for y in columns:
        data[y] = {
            "Inventory": inventory,
            "Accounts Receivable": receivables,
            "Accounts Payable": payables,
            "Stockholders Equity": equity,
            "Total Debt": debt,
            "Total Assets": total_assets,
            "Current Assets": 300_000,
            "Current Liabilities": 150_000,
            "Cash And Cash Equivalents": 50_000,
            "Net Income": 105_000,
        }
    return pd.DataFrame(data)


@pytest.fixture()
def sample_income_statement():
    return _make_income_statement()


@pytest.fixture()
def sample_balance_sheet():
    return _make_balance_sheet()


def mock_load_financial_data(ticker: str):
    """正常なデータを返すモックローダー。"""
    return _make_income_statement(), _make_balance_sheet()


def mock_load_financial_data_empty(ticker: str):
    """空データを返すモックローダー。"""
    return pd.DataFrame(), pd.DataFrame()


def mock_get_val_safe(df, keys, year, default=0.0):
    """テスト用 get_val_safe。"""
    for k in keys:
        if k in df.index and year in df.columns:
            val = df.loc[k, year]
            if not pd.isna(val):
                return float(val)
    return default


def mock_calculate_financial_metrics(pl, bs, year, use_nopat=True):
    """テスト用 calculate_financial_metrics。"""
    rev = mock_get_val_safe(pl, ["Total Revenue", "Operating Revenue"], year)
    oi = mock_get_val_safe(pl, ["Operating Income"], year)
    eq = mock_get_val_safe(bs, ["Stockholders Equity"], year)
    debt = mock_get_val_safe(bs, ["Total Debt"], year)
    inv = mock_get_val_safe(bs, ["Inventory"], year)
    recv = mock_get_val_safe(bs, ["Accounts Receivable"], year)
    pay = mock_get_val_safe(bs, ["Accounts Payable"], year)
    cogs = mock_get_val_safe(pl, ["Cost Of Revenue"], year)
    ic = eq + debt
    nopat = oi * 0.7
    roic = nopat / ic if ic > 0 else 0
    dio = inv / cogs * 365 if cogs > 0 else 0
    dso = recv / rev * 365 if rev > 0 else 0
    dpo = pay / cogs * 365 if cogs > 0 else 0
    return {
        "revenue": rev,
        "operating_income": oi,
        "nopat": nopat,
        "invested_capital": ic,
        "roic": roic,
        "ccc": dio + dso - dpo,
        "dio": dio,
        "dso": dso,
        "dpo": dpo,
        "cogs": cogs,
        "inventory": inv,
        "receivables": recv,
        "payables": pay,
    }


def mock_calculate_ccc_metrics(pl, bs, year):
    """テスト用 calculate_ccc_metrics。"""
    m = mock_calculate_financial_metrics(pl, bs, year)
    return {k: m[k] for k in ("revenue", "cogs", "inventory", "receivables", "payables", "dio", "dso", "dpo", "ccc")}


def mock_calculate_comprehensive_metrics(pl, bs, year, companies_dict, get_val_safe_fn):
    """テスト用 calculate_comprehensive_metrics。"""
    return mock_calculate_financial_metrics(pl, bs, year)


def mock_load_markdown_asset(name: str) -> str:
    """テスト用 markdown ローダー。"""
    return f"# Mock Markdown: {name}"


def mock_get_cashflow_data(ticker: str) -> pd.DataFrame:
    """テスト用キャッシュフローデータ。"""
    data = {
        _YEAR: {
            "Capital Expenditure": -50_000,
            "Operating Cash Flow": 200_000,
            "Free Cash Flow": 150_000,
            "Depreciation And Amortization": 30_000,
        },
        _PREV_YEAR: {
            "Capital Expenditure": -45_000,
            "Operating Cash Flow": 180_000,
            "Free Cash Flow": 135_000,
            "Depreciation And Amortization": 28_000,
        },
    }
    return pd.DataFrame(data)


def mock_ensure_historical_marginal_profit_data(path):
    """ノーオペレーション。"""
    pass


def mock_load_marginal_profit_data(path):
    """テスト用の限界利益データ。"""
    mock = MagicMock()
    mock.to_pandas.return_value = pd.DataFrame(
        {
            "Year": [2023, 2024],
            "Category": ["A", "B"],
            "Total_Revenue": [100, 200],
            "Avg_Margin": [0.3, 0.4],
            "Total_Volume": [10, 20],
        }
    )
    return mock
