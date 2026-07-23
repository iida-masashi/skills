import argparse
from pathlib import Path

import pandas as pd

# Import utility modules
from consultant_toolkit.finance_data import fetch_financial_data


def fetch_finance_data(ticker_symbol, include_trends=False):
    """
    Fetches basic financial info and saves to CSV.

    Args:
        ticker_symbol: Ticker symbol to fetch
        include_trends: Include financial trends analysis (ROIC, margins, etc.)
    """
    print(f"Fetching data for {ticker_symbol}...")

    # Use unified data fetching
    data = fetch_financial_data(ticker_symbol, history_period="1y")
    if not data:
        print(f"Failed to fetch data for {ticker_symbol}")
        return

    # 1. Info (Company Summary)
    info = data.info
    summary_data = {
        "Name": info.get("longName"),
        "Sector": info.get("sector"),
        "Industry": info.get("industry"),
        "Market Cap": info.get("marketCap"),
        "Forward PE": info.get("forwardPE"),
        "Trailing PE": info.get("trailingPE"),
        "Dividend Yield": info.get("dividendYield"),
        "Operating Margin": info.get("operatingMargins"),
        "ROA": info.get("returnOnAssets"),
        "ROE": info.get("returnOnEquity"),
        "Price to Book": info.get("priceToBook"),
    }

    # 2. Historical Data
    hist = data.history

    # Save Results
    output_dir = Path("financial_data") / ticker_symbol.replace(".", "_")
    output_dir.mkdir(parents=True, exist_ok=True)

    hist_path = output_dir / "price_history.csv"
    hist.to_csv(hist_path)

    summary_path = output_dir / "company_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        for k, v in summary_data.items():
            f.write(f"{k}: {v}\n")

    print("\n--- 📊 Company Overview ---")
    for k, v in summary_data.items():
        if v is not None:
            if isinstance(v, float):
                if k in ["Operating Margin", "ROA", "ROE"]:
                    print(f"{k:20s}: {v:.2%}")
                elif k == "Dividend Yield":
                    print(f"{k:20s}: {v:.2%}" if v else f"{k:20s}: N/A")
                else:
                    print(f"{k:20s}: {v:.2f}")
            else:
                print(f"{k:20s}: {v}")

    print(f"\n✅ Price history saved to: {hist_path.absolute()}")
    print(f"✅ Summary saved to: {summary_path.absolute()}")

    # 3. Financial Trends (if requested)
    if include_trends:
        income = data.financials
        balance = data.balance_sheet

        if not income.empty and not balance.empty:
            print("\n--- 📈 Financial Trends (Annual) ---")

            try:
                # Extract key financial metrics across years
                revenue = (
                    income.loc["Total Revenue"]
                    if "Total Revenue" in income.index
                    else None
                )
                ebit = income.loc["EBIT"] if "EBIT" in income.index else None
                net_income = (
                    income.loc["Net Income"] if "Net Income" in income.index else None
                )
                equity = (
                    balance.loc["Stockholders Equity"]
                    if "Stockholders Equity" in balance.index
                    else None
                )

                if revenue is not None and equity is not None:
                    trends = pd.DataFrame(
                        {
                            "Revenue": revenue,
                            "Net Income": net_income
                            if net_income is not None
                            else pd.Series(),
                            "EBIT": ebit if ebit is not None else pd.Series(),
                            "ROE_Proxy": (net_income / equity * 100)
                            if net_income is not None
                            else pd.Series(),
                        }
                    )
                    print(trends.to_string())

                    trends_path = output_dir / "financial_trends.csv"
                    trends.to_csv(trends_path)
                    print(f"\n✅ Financial trends saved to: {trends_path.absolute()}")
                else:
                    print("⚠️  Insufficient data for trend analysis")

            except KeyError as e:
                print(f"⚠️  Financial data structure issue: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Financial Data Fetcher")
    parser.add_argument(
        "--ticker", required=True, help="Ticker symbol (e.g., AAPL, 7203.T, 2229.T)"
    )
    parser.add_argument(
        "--trends", action="store_true", help="Include financial trends analysis"
    )

    args = parser.parse_args()
    fetch_finance_data(args.ticker, include_trends=args.trends)
