"""
Demand Decomposition Script for Promotion Forecasting POC.
Separates total sales into Base Demand and Promotion Lift using discount thresholds
and weekday-aware interpolation.
"""

import logging
from pathlib import Path
from typing import Final

import polars as pl

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
DATA_DIR: Final[Path] = Path("promo_poc_data")
ITEM_MASTER_FILE: Final[Path] = DATA_DIR / "item_master.csv"
TRANSACTIONS_FILE: Final[Path] = DATA_DIR / "sales_transactions.csv"
OUTPUT_FILE: Final[Path] = DATA_DIR / "decomposed_transactions.csv"


def decompose_demand() -> None:
    """
    Reads transaction data, identifies promotions, and estimates base demand and lift.

    The algorithm:
    1. Joins item master for discount thresholds.
    2. Identifies 'promo days' based on actual price vs list price.
    3. Masks promo day sales and interpolates using same-weekday non-promo averages.
    4. Calculates lift as max(total - base, 0).
    5. Saves the decomposed result to CSV.

    Raises:
        FileNotFoundError: If input CSV files are missing.
    """
    if not ITEM_MASTER_FILE.exists() or not TRANSACTIONS_FILE.exists():
        logger.error(f"Input files missing in {DATA_DIR}")
        raise FileNotFoundError(f"Ensure {ITEM_MASTER_FILE} and {TRANSACTIONS_FILE} exist.")

    # 1. Load Data
    logger.info("Loading transaction and master data...")
    item_master = pl.read_csv(ITEM_MASTER_FILE)
    transactions = pl.read_csv(TRANSACTIONS_FILE)

    # Convert date and merge master
    df = transactions.with_columns(pl.col("date").str.to_datetime().dt.date())
    df = df.join(
        item_master.select(["item_id", "promo_discount_threshold"]), on="item_id"
    )

    # 2. Promotion Detection Logic
    logger.info("Detecting promotions based on discount thresholds...")
    df = df.with_columns(
        (
            (pl.col("list_price") - pl.col("actual_price")) / pl.col("list_price")
        ).alias("calc_discount_rate")
    )
    df = df.with_columns(
        pl.when(
            (pl.col("calc_discount_rate") > pl.col("promo_discount_threshold"))
            | (pl.col("is_promo_flag") == 1)
        )
        .then(1)
        .otherwise(0)
        .alias("is_promo_detected")
    )

    # 3. Base Demand Estimation (Baseline)
    # Mask promo sales and fill using weekday-aware rolling mean
    logger.info("Estimating base demand using weekday-aware interpolation...")
    df = df.with_columns(
        pl.when(pl.col("is_promo_detected") == 0)
        .then(pl.col("sales_volume"))
        .otherwise(None)
        .alias("base_sales_masked")
    )

    # Add weekday (0: Mon, ..., 6: Sun)
    df = df.with_columns(pl.col("date").dt.weekday().alias("weekday"))
    df = df.sort(["item_id", "date"])

    # Interpolation: Rolling mean over the same weekday within each item group
    # Note: center=True uses surrounding weeks. min_samples=1 handles edge cases.
    df = df.with_columns(
        pl.col("base_sales_masked")
        .rolling_mean(window_size=5, center=True, min_samples=1)
        .over(["item_id", "weekday"])
        .alias("estimated_base")
    )

    # Final gap filling (forward/backward) for edges
    df = df.with_columns(
        pl.col("estimated_base")
        .fill_null(strategy="forward")
        .fill_null(strategy="backward")
        .over("item_id")
    )

    # 4. Lift Calculation
    df = df.with_columns(
        (pl.col("sales_volume") - pl.col("estimated_base")).alias("estimated_lift")
    )
    # Clamp negative lift to zero
    df = df.with_columns(
        pl.when(pl.col("estimated_lift") < 0)
        .then(0)
        .otherwise(pl.col("estimated_lift"))
        .alias("estimated_lift")
    )

    # 5. Accuracy Metrics (Estimated vs Ground Truth)
    metrics_df = df.select(
        [
            (
                (pl.col("true_base") - pl.col("estimated_base")).abs().sum()
                / pl.col("true_base").sum()
                * 100
            ).alias("base_wape"),
            (
                (pl.col("true_lift") - pl.col("estimated_lift")).abs().sum()
                / pl.col("true_lift").sum()
                * 100
            ).alias("lift_wape"),
        ]
    )

    base_wape: float = metrics_df["base_wape"][0]
    lift_wape: float = metrics_df["lift_wape"][0]

    logger.info("--- Decomposition Accuracy (WAPE) ---")
    logger.info(f"Base Demand Estimation Error: {base_wape:.2f}%")
    logger.info(f"Lift Demand Estimation Error: {lift_wape:.2f}%")

    # Save output
    df.write_csv(OUTPUT_FILE)
    logger.info(f"Decomposed data saved at {OUTPUT_FILE}")


if __name__ == "__main__":
    decompose_demand()
