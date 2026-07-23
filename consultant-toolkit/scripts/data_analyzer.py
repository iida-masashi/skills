#!/usr/bin/env python3
"""
High-performance SCM/Finance Data Analyzer (Project Fusion)
Author: Gemini CLI (SCM Galaxy Engineer)
Description: Uses Polars to analyze part history and revenue trends.
"""

import argparse
from pathlib import Path

import polars as pl


def analyze_parts_history(input_file: Path) -> pl.DataFrame:
    """
    Analyzes CSV data to find CAGR and Profitability by Category.
    """
    print(f"📈 Analyzing Data: {input_file}")

    # 1. Load data
    df = pl.read_csv(input_file)

    # 2. Aggregation: Group by Category and calculate trends
    summary = (
        df.group_by("Category")
        .agg(
            [
                pl.col("Total_Revenue").sum().alias("LifeTime_Revenue"),
                pl.col("Total_Marginal_Profit").sum().alias("LifeTime_Profit"),
                pl.col("Total_Revenue").mean().alias("Avg_Annual_Revenue"),
                (
                    pl.col("Total_Marginal_Profit").sum()
                    / pl.col("Total_Revenue").sum()
                ).alias("Overall_Margin"),
            ]
        )
        .sort("LifeTime_Revenue", descending=True)
    )

    # 3. Trend Analysis: Calculate Growth Rate (CAGR simplified)
    # Get First and Last Year for each Category
    years = df.select(
        [pl.col("Year").min().alias("Start"), pl.col("Year").max().alias("End")]
    ).row(0)
    duration = years[1] - years[0]

    # Self-join to compare first year and last year
    start_rev = (
        df.filter(pl.col("Year") == years[0])
        .select(["Category", "Total_Revenue"])
        .rename({"Total_Revenue": "Start_Revenue"})
    )
    end_rev = (
        df.filter(pl.col("Year") == years[1])
        .select(["Category", "Total_Revenue"])
        .rename({"Total_Revenue": "End_Revenue"})
    )

    trends = start_rev.join(end_rev, on="Category", how="inner").with_columns(
        [
            (
                ((pl.col("End_Revenue") / pl.col("Start_Revenue")) ** (1 / duration))
                - 1
            ).alias("CAGR")
        ]
    )

    return summary.join(trends, on="Category", how="inner")


def main() -> None:
    parser = argparse.ArgumentParser(description="Polars Data Analyzer")
    parser.add_argument(
        "--input",
        default="consultant-toolkit/data/mock_parts_data_history.csv",
        help="CSV to analyze",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ File not found: {input_path}")
        return

    result = analyze_parts_history(input_path)

    print("\n--- 🏁 Analysis Result (Top Categories by Revenue) ---")
    print(
        result.select(["Category", "LifeTime_Revenue", "Overall_Margin", "CAGR"]).head(
            10
        )
    )

    # Highlight Risks: Low Margin and Negative CAGR
    risks = result.filter((pl.col("Overall_Margin") < 0.20) | (pl.col("CAGR") < 0))
    if not risks.is_empty():
        print("\n⚠️ Alert: High Risk Categories (Low Margin or Negative Growth)!")
        print(risks.select(["Category", "Overall_Margin", "CAGR"]))


if __name__ == "__main__":
    main()
