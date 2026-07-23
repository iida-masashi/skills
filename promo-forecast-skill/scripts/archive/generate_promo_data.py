"""
Test Data Generation Script for Promotion Forecasting POC.
Generates 5 years of daily sales data for 5 items with seasonality and promotion effects.
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
START_DATE: Final[datetime] = datetime(2021, 1, 1)
END_DATE: Final[datetime] = datetime(2025, 12, 31)
OUTPUT_DIR: Final[Path] = Path("promo_poc_data")


def generate_test_data() -> None:
    """
    Generates synthetic sales data for 5 items and saves to CSV.

    The generated data includes:
    - Base demand: Trend + Weekly Seasonality + Yearly Seasonality.
    - Promotion Lift: Price elasticity and flyer effects during discount periods.
    """
    days: int = (END_DATE - START_DATE).days + 1
    dates: Sequence[datetime] = [START_DATE + timedelta(days=i) for i in range(days)]

    # 1. Define Item Master
    item_master = pl.DataFrame(
        {
            "item_id": [1, 2, 3, 4, 5],
            "item_name": ["ビール", "チョコ", "ポテトチップス", "グミ", "オレンジジュース"],
            "list_price": [250, 150, 180, 120, 200],
            "promo_discount_threshold": [0.15, 0.15, 0.15, 0.15, 0.15],
            "base_volume": [100, 50, 80, 40, 70],
        }
    )

    all_transactions: list[pl.DataFrame] = []

    # Set seed for reproducibility
    np.random.seed(42)

    for item in item_master.to_dicts():
        item_id: int = item["item_id"]
        item_name: str = item["item_name"]
        base_vol: float = item["base_volume"]
        list_price: float = item["list_price"]

        logger.info(f"Generating data for item: {item_name} (ID: {item_id})")

        # Create time series
        df = pl.DataFrame({"date": dates})
        df = df.with_columns(pl.lit(item_id).alias("item_id"))

        # --- 2. Base Demand Generation ---
        # Trend (Slight upward)
        trend = np.linspace(1.0, 1.2, days)

        # Weekly Seasonality (Weekends 1.5x)
        weekday = df["date"].dt.weekday()
        weekday_effect = (
            df.select(
                pl.when(weekday >= 6).then(1.5).otherwise(1.0).alias("effect")
            ).to_series().to_numpy()
        )

        # Yearly Seasonality
        month = df["date"].dt.month().to_numpy()
        day = df["date"].dt.day().to_numpy()

        if item_name == "ビール":
            # Peak in Summer (July-August)
            yearly_effect = 1.0 + 0.8 * np.exp(-((month - 7.5) ** 2) / 2.0)
        elif item_name == "チョコ":
            # Massive spike before Valentine's Day
            yearly_effect = 1.0 + 3.0 * np.exp(
                -((month - 2) ** 2 + (day - 10) ** 2 / 50) / 0.5
            )
            # High in Winter
            yearly_effect += 0.3 * (month >= 11).astype(float) + 0.3 * (
                month <= 3
            ).astype(float)
        elif item_name == "オレンジジュース":
            # Slight peak in Summer
            yearly_effect = 1.0 + 0.3 * np.exp(-((month - 8) ** 2) / 4.0)
        else:
            # Stable for others
            yearly_effect = np.ones(days)

        # Random noise
        noise = np.random.normal(1.0, 0.05, days)

        base_demand = base_vol * trend * weekday_effect * yearly_effect * noise
        df = df.with_columns(pl.Series("true_base", base_demand))

        # --- 3. Promotion and Lift Generation ---
        is_promo = np.zeros(days, dtype=int)
        actual_price = np.full(days, list_price, dtype=float)
        flyer = np.zeros(days, dtype=int)

        # Generate promos: ~1-2 times per month, 3-5 days each
        total_months = 12 * 5
        for m in range(1, total_months + 1):
            if np.random.rand() > 0.3:
                start_idx = np.random.randint(0, 25) + (m - 1) * 30
                if start_idx + 5 < days:
                    duration = np.random.randint(3, 6)
                    is_promo[start_idx : start_idx + duration] = 1
                    # 20%-40% discount
                    discount = np.random.uniform(0.20, 0.40)
                    actual_price[start_idx : start_idx + duration] = np.round(
                        list_price * (1 - discount)
                    )
                    # 50% chance of flyer
                    if np.random.rand() > 0.5:
                        flyer[start_idx : start_idx + duration] = 1

        # Calculate Lift (Price Elasticity Model: (Regular/Actual)^2.5 * Flyer effect)
        price_ratio = list_price / actual_price
        lift_effect = np.where(is_promo == 1, (price_ratio**2.5) * (1 + flyer * 0.5), 0)
        true_lift = base_demand * lift_effect * np.random.normal(1.0, 0.1, days)

        df = df.with_columns(
            [
                pl.Series("true_lift", true_lift),
                pl.Series("list_price", np.full(days, list_price)),
                pl.Series("actual_price", actual_price),
                pl.Series("flyer", flyer),
                pl.Series("is_promo_flag", is_promo),
            ]
        )

        # Total Volume
        df = df.with_columns(
            (pl.col("true_base") + pl.col("true_lift")).alias("sales_volume")
        )

        all_transactions.append(df)

    # Combine all items
    full_df = pl.concat(all_transactions)

    # Save outputs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    item_master.write_csv(OUTPUT_DIR / "item_master.csv")
    full_df.write_csv(OUTPUT_DIR / "sales_transactions.csv")

    logger.info(f"Test data generated at {OUTPUT_DIR}")
    logger.info(f"Total records: {len(full_df)}")


if __name__ == "__main__":
    generate_test_data()
