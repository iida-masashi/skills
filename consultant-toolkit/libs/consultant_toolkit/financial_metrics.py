"""
財務指標計算ライブラリ

ROIC, CCC, DIO/DSO/DPO などの財務指標計算を統一化します。
全スクリプトで一貫した計算ロジックを保証します。
"""

from typing import Any

import pandas as pd

from consultant_toolkit.constants import DAYS_PER_YEAR, DEFAULT_COGS_RATIO, DEFAULT_TAX_RATE

# ========================================
# ヘルパー関数
# ========================================


def get_val_safe(
    df: pd.DataFrame, keys: list[str], year: Any, default: float = 0.0
) -> float:
    """
    DataFrameから安全に値を取得 (複数キー候補対応)

    Args:
        df: pandas DataFrame
        keys: 試行するキーのリスト
        year: 対象年度
        default: キーが見つからない場合のデフォルト値

    Returns:
        float: 取得した値、または default
    """
    for k in keys:
        if k in df.index and year in df.columns:
            val = df.loc[k, year]
            if not pd.isna(val):
                return float(val)
    return default


# ========================================
# ROIC 関連計算
# ========================================


def calculate_roic(
    pl: pd.DataFrame | None = None,
    bs: pd.DataFrame | None = None,
    year: Any = None,
    use_nopat: bool = True,
    **kwargs,
) -> dict[str, float] | float:
    """
    ROIC (投下資本利益率) を計算

    Args:
        pl: P/L (損益計算書) DataFrame (またはスカラ値呼び出し時はNone)
        bs: B/S (貸借対照表) DataFrame (またはスカラ値呼び出し時はNone)
        year: 対象年度
        use_nopat: NOPAT (税引後営業利益) を使用するか
        **kwargs: スカラ値呼び出し用の引数 (revenue, operating_income, total_assets, current_liabilities, cash, tax_rate)

    Returns:
        Union[Dict, float]: DataFrame時は辞書、スカラ値時はROIC(float)
    """
    if isinstance(pl, pd.DataFrame) and isinstance(bs, pd.DataFrame):
        # DataFrame 形式の計算
        rev = get_val_safe(pl, ["Total Revenue", "Operating Revenue"], year)
        op_inc = get_val_safe(pl, ["Operating Income"], year)
        tax_prov = get_val_safe(pl, ["Tax Provision", "Income Tax Expense"], year)
        pretax = get_val_safe(
            pl,
            ["Pretax Income", "Income Before Tax", "Net Income Before Taxes"],
            year,
            default=1.0,
        )

        # #5: pretaxが負（赤字）の場合はtax_rateが異常値になるためデフォルトに固定
        if pretax > 0 and tax_prov >= 0:
            tax_rate = min(tax_prov / pretax, 0.6)  # 上限60%でサニタイズ
        else:
            tax_rate = DEFAULT_TAX_RATE
        nopat = op_inc * (1 - tax_rate) if use_nopat else op_inc

        debt = get_val_safe(bs, ["Total Debt", "Short Long Term Debt Total"], year)
        equity = get_val_safe(
            bs, ["Stockholders Equity", "Total Equity Gross Minority Interest"], year
        )
        ic = debt + equity

        if ic == 0:
            assets = get_val_safe(bs, ["Total Assets"], year)
            liabs = get_val_safe(
                bs, ["Current Liabilities", "Total Current Liabilities"], year
            )
            cash = get_val_safe(
                bs, ["Cash", "Cash And Cash Equivalents", "Cash And Equivalents"], year
            )
            ic = assets - liabs - cash

        roic = nopat / ic if ic > 0 else 0
        nopat_margin = nopat / rev if rev > 0 else 0
        ic_turnover = rev / ic if ic > 0 else 0

        return {
            "roic": roic,
            "nopat": nopat,
            "invested_capital": ic,
            "nopat_margin": nopat_margin,
            "ic_turnover": ic_turnover,
            "tax_rate": tax_rate,
            "revenue": rev,
            "operating_income": op_inc,
        }
    else:
        # スカラ値形式の計算 (テスト互換用)
        rev = kwargs.get("revenue", 0.0)
        op_inc = kwargs.get("operating_income", 0.0)
        assets = kwargs.get("total_assets", 0.0)
        liabilities = kwargs.get("current_liabilities", 0.0)
        cash = kwargs.get("cash", 0.0)
        tax_rate = kwargs.get("tax_rate", DEFAULT_TAX_RATE)

        ic = assets - liabilities - cash
        nopat = op_inc * (1 - tax_rate) if use_nopat else op_inc
        roic = nopat / ic if ic > 0 else 0.0

        return roic


# ========================================
# CCC (Cash Conversion Cycle) 関連計算
# ========================================


def calculate_ccc(
    pl: pd.DataFrame | None = None,
    bs: pd.DataFrame | None = None,
    year: Any = None,
    **kwargs,
) -> dict[str, float]:
    """
    CCC (Cash Conversion Cycle) を計算

    CCC = DIO + DSO - DPO
    - DIO: Days Inventory Outstanding (在庫回転日数)
    - DSO: Days Sales Outstanding (売上債権回転日数)
    - DPO: Days Payables Outstanding (仕入債務回転日数)

    Args:
        pl: P/L (損益計算書) DataFrame (またはスカラ値呼び出し時はNone)
        bs: B/S (貸借対照表) DataFrame (またはスカラ値呼び出し時はNone)
        year: 対象年度
        **kwargs: スカラ値呼び出し用の引数 (revenue, cogs, inventory, receivables, payables)

    Returns:
        dict: 以下のキーを含む辞書
            - ccc: キャッシュ・コンバージョン・サイクル (日数)
            - dio: 在庫回転日数
            - dso: 売上債権回転日数
            - dpo: 仕入債務回転日数
            - inventory: 在庫金額
            - receivables: 売掛金
            - payables: 買掛金
            - revenue: 売上高
            - cogs: 売上原価

    Example:
        >>> ccc_metrics = calculate_ccc(pl, bs, year)
        >>> print(f"CCC: {ccc_metrics['ccc']:.1f} days")
        >>> print(f"DIO: {ccc_metrics['dio']:.1f} days")
    """
    if isinstance(pl, pd.DataFrame) and isinstance(bs, pd.DataFrame):
        rev = get_val_safe(pl, ["Total Revenue", "Operating Revenue"], year)
        cogs = get_val_safe(pl, ["Cost Of Revenue", "Cost Of Goods Sold"], year)

        # #6: COGSが取得できない場合は業種別原価率でフォールバック
        # yfinanceのindustry情報が取れる場合は業種別レートを使用
        if cogs == 0 and rev > 0:
            _industry_cogs_map = {
                "Electronic Components": 0.82,
                "Electronics & Computer Distribution": 0.85,
                "Semiconductors": 0.50,
                "Semiconductor Equipment & Materials": 0.45,
                "Software - Application": 0.25,
                "Software - Infrastructure": 0.25,
                "Information Technology Services": 0.60,
                "Auto Parts": 0.78,
                "Specialty Retail": 0.65,
                "Grocery Stores": 0.75,
            }
            # DataFrameのattrsに業種情報があれば使用、なければデフォルト
            _industry = getattr(pl, "attrs", {}).get("industry", "")
            _ratio = _industry_cogs_map.get(_industry, DEFAULT_COGS_RATIO)
            cogs = rev * _ratio

        inventory = get_val_safe(bs, ["Inventory", "Total Inventory"], year)
        ar = get_val_safe(bs, ["Accounts Receivable", "Net Receivables"], year)
        ap = get_val_safe(bs, ["Accounts Payable", "Current Accounts Payable"], year)
    else:
        # スカラ値形式
        rev = float(kwargs.get("revenue", 0.0) or 0.0)
        cogs_val = kwargs.get("cogs")
        cogs = (
            float(cogs_val)
            if cogs_val is not None
            else (rev * DEFAULT_COGS_RATIO if rev > 0 else 0.0)
        )

        inventory = float(kwargs.get("inventory", 0.0) or 0.0)
        ar = float(kwargs.get("receivables", 0.0) or 0.0)
        ap = float(kwargs.get("payables", 0.0) or 0.0)

    dio = (inventory / cogs * DAYS_PER_YEAR) if cogs > 0 else 0
    dso = (ar / rev * DAYS_PER_YEAR) if rev > 0 else 0
    dpo = (ap / cogs * DAYS_PER_YEAR) if cogs > 0 else 0
    ccc = dio + dso - dpo

    return {
        "ccc": ccc,
        "dio": dio,
        "dso": dso,
        "dpo": dpo,
        "inventory": inventory,
        "receivables": ar,
        "payables": ap,
        "revenue": rev,
        "cogs": cogs,
    }


# ========================================
# 統合財務指標計算
# ========================================


def calculate_financial_metrics(
    pl: pd.DataFrame, bs: pd.DataFrame, year: Any, use_nopat: bool = True
) -> dict[str, float]:
    """
    ROIC と CCC を含む統合財務指標を計算

    Args:
        pl: P/L (損益計算書) DataFrame
        bs: B/S (貸借対照表) DataFrame
        year: 対象年度
        use_nopat: NOPAT (税引後営業利益) を使用するか

    Returns:
        dict: calculate_roic() と calculate_ccc() の統合結果

    Example:
        >>> all_metrics = calculate_financial_metrics(pl, bs, year)
        >>> print(f"ROIC: {all_metrics['roic']:.2%}")
        >>> print(f"CCC: {all_metrics['ccc']:.1f} days")
    """
    roic_metrics = calculate_roic(pl, bs, year, use_nopat)
    ccc_metrics = calculate_ccc(pl, bs, year)

    roic_dict = (
        roic_metrics if isinstance(roic_metrics, dict) else {"roic": roic_metrics}
    )
    ccc_dict = ccc_metrics if isinstance(ccc_metrics, dict) else {}

    # 統合 (revenue の重複を避ける)
    return {**roic_dict, **ccc_dict}


def calculate_liquidity_ratios(
    balance_sheet: pd.DataFrame, date: Any
) -> dict[str, float]:
    """
    流動性指標を計算

    Args:
        balance_sheet: 貸借対照表 DataFrame
        date: 対象年度

    Returns:
        dict: 流動性指標
            - current_ratio: 流動比率
            - quick_ratio: 当座比率
            - cash_ratio: 現金比率

    Example:
        >>> liquidity = calculate_liquidity_ratios(bs, year)
        >>> print(f"Current Ratio: {liquidity['current_ratio']:.2f}")
    """
    current_assets = get_val_safe(
        balance_sheet, ["Current Assets", "Total Current Assets"], date, 0.0
    )
    current_liabilities = get_val_safe(
        balance_sheet, ["Current Liabilities", "Total Current Liabilities"], date, 0.0
    )
    inventory = get_val_safe(balance_sheet, ["Inventory", "Inventories"], date, 0.0)
    cash = get_val_safe(
        balance_sheet,
        ["Cash", "Cash And Cash Equivalents", "Cash And Equivalents"],
        date,
        0.0,
    )

    # 流動比率 = 流動資産 / 流動負債
    current_ratio = (
        current_assets / current_liabilities if current_liabilities > 0 else 0.0
    )

    # 当座比率 = (流動資産 - 在庫) / 流動負債
    quick_ratio = (
        (current_assets - inventory) / current_liabilities
        if current_liabilities > 0
        else 0.0
    )

    # 現金比率 = 現金 / 流動負債
    cash_ratio = cash / current_liabilities if current_liabilities > 0 else 0.0

    return {
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "cash_ratio": cash_ratio,
    }


def calculate_solvency_ratios(
    financials: pd.DataFrame, balance_sheet: pd.DataFrame, date: Any
) -> dict[str, float]:
    """
    安全性指標を計算

    Args:
        financials: 損益計算書 DataFrame
        balance_sheet: 貸借対照表 DataFrame
        date: 対象年度

    Returns:
        dict: 安全性指標
            - debt_to_equity: 負債比率
            - debt_to_assets: 負債資産比率
            - interest_coverage: インタレストカバレッジレシオ

    Example:
        >>> solvency = calculate_solvency_ratios(pl, bs, year)
        >>> print(f"D/E Ratio: {solvency['debt_to_equity']:.2f}")
    """
    total_debt = get_val_safe(
        balance_sheet,
        ["Total Debt", "Long Term Debt", "Total Liabilities Net Minority Interest"],
        date,
        0.0,
    )
    total_equity = get_val_safe(
        balance_sheet,
        [
            "Total Equity Gross Minority Interest",
            "Stockholders Equity",
            "Total Stockholder Equity",
        ],
        date,
        0.0,
    )
    total_assets = get_val_safe(balance_sheet, ["Total Assets"], date, 0.0)
    operating_income = get_val_safe(financials, ["Operating Income", "EBIT"], date, 0.0)
    interest_expense = get_val_safe(
        financials, ["Interest Expense", "Interest Expense Non Operating"], date, 0.0
    )

    # 負債比率 = 総負債 / 総資本
    debt_to_equity = total_debt / total_equity if total_equity > 0 else 0.0

    # 負債資産比率 = 総負債 / 総資産
    debt_to_assets = total_debt / total_assets if total_assets > 0 else 0.0

    # インタレストカバレッジレシオ = 営業利益 / 支払利息
    interest_coverage = (
        operating_income / abs(interest_expense) if interest_expense != 0 else 0.0
    )

    return {
        "debt_to_equity": debt_to_equity,
        "debt_to_assets": debt_to_assets,
        "interest_coverage": interest_coverage,
    }


def calculate_profitability_ratios(
    financials: pd.DataFrame, balance_sheet: pd.DataFrame, date: Any
) -> dict[str, float]:
    """
    収益性指標を計算

    Args:
        financials: 損益計算書 DataFrame
        balance_sheet: 貸借対照表 DataFrame
        date: 対象年度

    Returns:
        dict: 収益性指標
            - gross_margin: 売上総利益率
            - operating_margin: 営業利益率
            - net_margin: 純利益率
            - roe: 自己資本利益率 (ROE)
            - roa: 総資産利益率 (ROA)

    Example:
        >>> profitability = calculate_profitability_ratios(pl, bs, year)
        >>> print(f"ROE: {profitability['roe']:.2%}")
    """
    revenue = get_val_safe(
        financials, ["Total Revenue", "Operating Revenue"], date, 0.0
    )
    gross_profit = get_val_safe(financials, ["Gross Profit"], date, 0.0)
    operating_income = get_val_safe(financials, ["Operating Income", "EBIT"], date, 0.0)
    net_income = get_val_safe(
        financials, ["Net Income", "Net Income Common Stockholders"], date, 0.0
    )
    total_equity = get_val_safe(
        balance_sheet,
        ["Total Equity Gross Minority Interest", "Stockholders Equity"],
        date,
        0.0,
    )
    total_assets = get_val_safe(balance_sheet, ["Total Assets"], date, 0.0)

    # 売上総利益率 = 売上総利益 / 売上高
    gross_margin = gross_profit / revenue if revenue > 0 else 0.0

    # 営業利益率 = 営業利益 / 売上高
    operating_margin = operating_income / revenue if revenue > 0 else 0.0

    # 純利益率 = 純利益 / 売上高
    net_margin = net_income / revenue if revenue > 0 else 0.0

    # ROE = 純利益 / 自己資本
    roe = net_income / total_equity if total_equity > 0 else 0.0

    # ROA = 純利益 / 総資産
    roa = net_income / total_assets if total_assets > 0 else 0.0

    return {
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "net_margin": net_margin,
        "roe": roe,
        "roa": roa,
    }


def calculate_valuation_ratios(
    ticker_info: dict[str, Any],
    financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    date: Any,
) -> dict[str, float]:
    """
    バリュエーション指標を計算

    Args:
        ticker_info: yfinance ticker.info 辞書
        financials: 損益計算書 DataFrame
        balance_sheet: 貸借対照表 DataFrame
        date: 対象年度

    Returns:
        dict: バリュエーション指標
            - pe_ratio: 株価収益率 (P/E)
            - pb_ratio: 株価純資産倍率 (P/B)
            - dividend_yield: 配当利回り
            - market_cap: 時価総額

    Example:
        >>> valuation = calculate_valuation_ratios(ticker.info, pl, bs, year)
        >>> print(f"P/E Ratio: {valuation['pe_ratio']:.2f}")
    """
    market_cap = ticker_info.get("marketCap", 0)

    net_income = get_val_safe(
        financials, ["Net Income", "Net Income Common Stockholders"], date, 0.0
    )
    total_equity = get_val_safe(
        balance_sheet,
        ["Total Equity Gross Minority Interest", "Stockholders Equity"],
        date,
        0.0,
    )
    trailing_annual_dividend_yield = ticker_info.get("dividendYield", 0.0)

    # P/E Ratio = 時価総額 / 純利益
    pe_ratio = market_cap / net_income if net_income > 0 else 0.0

    # P/B Ratio = 時価総額 / 純資産
    pb_ratio = market_cap / total_equity if total_equity > 0 else 0.0

    # Dividend Yield (from ticker.info)
    dividend_yield = trailing_annual_dividend_yield

    return {
        "pe_ratio": pe_ratio,
        "pb_ratio": pb_ratio,
        "dividend_yield": dividend_yield if dividend_yield else 0.0,
        "market_cap": market_cap,
    }


def calculate_comprehensive_metrics(
    ticker_info: dict[str, Any],
    financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    date: Any,
) -> dict[str, float]:
    """
    包括的な財務指標を計算（全指標統合版）

    Args:
        ticker_info: yfinance ticker.info 辞書
        financials: 損益計算書 DataFrame
        balance_sheet: 貸借対照表 DataFrame
        date: 対象年度

    Returns:
        dict: 全財務指標の統合辞書

    Example:
        >>> all_metrics = calculate_comprehensive_metrics(ticker.info, pl, bs, year)
        >>> print(f"ROE: {all_metrics['roe']:.2%}, P/E: {all_metrics['pe_ratio']:.2f}")
    """
    # 既存のメトリクス
    financial_metrics = calculate_financial_metrics(financials, balance_sheet, date)

    # 新規追加メトリクス
    liquidity = calculate_liquidity_ratios(balance_sheet, date)
    solvency = calculate_solvency_ratios(financials, balance_sheet, date)
    profitability = calculate_profitability_ratios(financials, balance_sheet, date)
    valuation = calculate_valuation_ratios(ticker_info, financials, balance_sheet, date)

    # すべて統合
    return {**financial_metrics, **liquidity, **solvency, **profitability, **valuation}
