"""
Step 1: Demand Decomposition.
Refined for Polars 1.0 logic and future-ready calendar merging.
Strictly follows Lessons Learned checklist.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.absolute()
if str(ROOT_DIR) not in sys.path: sys.path.insert(0, str(ROOT_DIR))

import logging

import polars as pl
from libs.config import (
    ACTUALS_FILE,
    CALENDAR_FILE,
    COL_DATE,
    COL_ITEM_ID,
    COL_SALES,
    COL_STOCKOUT,
    DECOMPOSED_FILE,
    MASTER_FILE,
    PROMO_THRESHOLD,
)
from libs.data_utils import explode_calendar, get_date_item_skeleton, load_csv_with_date

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def decompose_demand() -> None:
    if not ACTUALS_FILE.exists(): raise FileNotFoundError("Run Step 0 first.")

    # 1. Load Data
    actuals_df = load_csv_with_date(ACTUALS_FILE, COL_DATE)
    calendar_df = pl.read_csv(CALENDAR_FILE)
    master_df = pl.read_csv(MASTER_FILE)

    # 2. Process Calendar
    calendar_daily_df = explode_calendar(calendar_df)
    calendar_agg_df = calendar_daily_df.group_by([COL_DATE, COL_ITEM_ID]).agg([
        pl.col("promo_name").str.join(" & "),
        pl.col("flyer").max(),
        pl.col("campaign_cost").sum(),
        pl.col("discount_rate_target").max()
    ])

    # 3. Build full timeframe using map_elements for scalar safety
    data_start_date, data_end_date = actuals_df[COL_DATE].min(), calendar_agg_df[COL_DATE].max()
    skeleton_df = get_date_item_skeleton(data_start_date, data_end_date, master_df[COL_ITEM_ID].unique().to_list())

    # 4. Merge
    merged_df = (
        skeleton_df
        .join(actuals_df, on=[COL_DATE, COL_ITEM_ID], how="left")
        .join(calendar_agg_df, on=[COL_DATE, COL_ITEM_ID], how="left")
        .join(master_df, on=COL_ITEM_ID)
    )

    # Fill defaults
    merged_df = merged_df.with_columns([
        pl.col("promo_name").fill_null("通常販売"),
        pl.col("flyer").fill_null(0),
        pl.col("campaign_cost").fill_null(0),
        pl.col(COL_STOCKOUT).fill_null(0),
        pl.col("actual_price").fill_null(pl.col("list_price") * (1 - pl.col("discount_rate_target").fill_null(0)))
    ]).with_columns([
        pl.col("discount_rate_target").fill_null(0).alias("discount_rate")
    ])

    # 5. Decomposition
    merged_df = merged_df.with_columns(pl.when((pl.col("discount_rate") > PROMO_THRESHOLD) | (pl.col("promo_name") != "通常販売")).then(1).otherwise(0).alias("is_promo_detected"))
    # Base is the rolling mean of non-promo, non-stockout sales. Stockout days are
    # censored (sales < true demand), so feeding them in would drag the baseline
    # down; we mask them out and let the rolling mean interpolate over them.
    merged_df = merged_df.with_columns(
        pl.when(
            (pl.col("is_promo_detected") == 0)
            & (pl.col(COL_STOCKOUT) == 0)
            & (pl.col(COL_SALES).is_not_null())
        ).then(pl.col(COL_SALES)).otherwise(None).alias("base_masked")
    )

    merged_df = (
        merged_df.with_columns(pl.col(COL_DATE).dt.weekday().alias("weekday"))
        .sort([COL_ITEM_ID, COL_DATE])
        .with_columns(
            pl.col("base_masked").rolling_mean(window_size=5, center=True, min_samples=1).over([COL_ITEM_ID, "weekday"]).alias("estimated_base")
        )
        .with_columns(
            pl.col("estimated_base").fill_null(strategy="forward").fill_null(strategy="backward").over(COL_ITEM_ID)
        )
    )

    # Lift = sales - base, but a promo lift can only exist on a detected promo
    # day. On non-promo days the residual is pure rolling-mean noise; the old
    # asymmetric clip(>=0) kept its positive half and dropped the negative half,
    # inflating total lift by ~4-6%. We zero out non-promo lift entirely and keep
    # the >=0 clip only where a promo is actually running.
    merged_df = merged_df.with_columns([
        (pl.col(COL_SALES).fill_null(0) - pl.col("estimated_base")).alias("raw_lift")
    ]).with_columns([
        pl.when(pl.col("is_promo_detected") == 0)
        .then(0)
        .otherwise(pl.col("raw_lift").clip(lower_bound=0))
        .alias("estimated_lift")
    ])

    merged_df.write_csv(DECOMPOSED_FILE)
    logger.info("Step 1 complete: Decomposed data saved.")

if __name__ == "__main__": decompose_demand()
