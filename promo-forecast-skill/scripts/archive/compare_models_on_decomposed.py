"""
Model Comparison Script for Decomposed Demand.
Compares Prophet and LightGBM performance on Base Demand and Promotion Lift.
"""

import logging
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
import polars as pl
from darts import TimeSeries
from darts.models import LightGBMModel, Prophet

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
DECOMPOSED_DATA_FILE: Final[Path] = Path("promo_poc_data/decomposed_transactions.csv")
TRAIN_END_DATE: Final[str] = "2024-12-31"
TARGET_ITEM_ID: Final[int] = 2  # Chocolate


def calculate_wape(actual: TimeSeries, forecast: TimeSeries) -> float:
    """
    Calculates Weighted Absolute Percentage Error (WAPE).

    Args:
        actual: Ground truth TimeSeries.
        forecast: Predicted TimeSeries.

    Returns:
        WAPE value in percentage.
    """
    act_vals = actual.values().flatten()
    for_vals = forecast.values().flatten()
    return float(np.sum(np.abs(act_vals - for_vals)) / np.sum(act_vals) * 100)


def compare_models() -> None:
    """
    Loads decomposed data and runs Prophet and LightGBM comparison.
    """
    if not DECOMPOSED_DATA_FILE.exists():
        logger.error(f"Decomposed data file not found: {DECOMPOSED_DATA_FILE}")
        return

    # 1. Load Data
    logger.info(f"Loading decomposed data from {DECOMPOSED_DATA_FILE}...")
    df = pl.read_csv(DECOMPOSED_DATA_FILE)

    # Filter for target item
    item_df = df.filter(pl.col("item_id") == TARGET_ITEM_ID)
    item_pd = item_df.to_pandas()

    # 2. Prepare Darts TimeSeries
    # Base, Lift, and Covariates (price, flyer)
    base_ts = TimeSeries.from_dataframe(
        item_pd, time_col="date", value_cols="estimated_base", freq="D"
    )
    lift_ts = TimeSeries.from_dataframe(
        item_pd, time_col="date", value_cols="estimated_lift", freq="D"
    )
    cov_ts = TimeSeries.from_dataframe(
        item_pd, time_col="date", value_cols=["actual_price", "flyer"], freq="D"
    )

    # Split Train/Validation
    base_train, base_val = base_ts.split_before(pd.Timestamp(TRAIN_END_DATE))
    lift_train, lift_val = lift_ts.split_before(pd.Timestamp(TRAIN_END_DATE))

    logger.info(f"Testing Model: Item ID {TARGET_ITEM_ID}")

    # --- Round 1: Base Demand Forecasting ---
    logger.info("--- Round 1: Base Demand Forecasting ---")

    # Prophet
    m_prophet_base = Prophet()
    m_prophet_base.fit(base_train)
    pred_prophet_base = m_prophet_base.predict(len(base_val))
    err_prophet_base = calculate_wape(base_val, pred_prophet_base)

    # LightGBM
    m_lgbm_base = LightGBMModel(lags=30, output_chunk_length=1)
    m_lgbm_base.fit(base_train)
    pred_lgbm_base = m_lgbm_base.predict(len(base_val))
    err_lgbm_base = calculate_wape(base_val, pred_lgbm_base)

    logger.info(f"Prophet Base WAPE: {err_prophet_base:.2f}%")
    logger.info(f"LightGBM Base WAPE: {err_lgbm_base:.2f}%")

    # --- Round 2: Lift Demand Forecasting ---
    logger.info("--- Round 2: Lift Demand Forecasting ---")

    # Prophet (with Covariates)
    m_prophet_lift = Prophet()
    m_prophet_lift.fit(lift_train, future_covariates=cov_ts)
    pred_prophet_lift = m_prophet_lift.predict(len(lift_val), future_covariates=cov_ts)
    err_prophet_lift = calculate_wape(lift_val, pred_prophet_lift)

    # LightGBM (with Covariates)
    m_lgbm_lift = LightGBMModel(lags=7, lags_future_covariates=(0, 1), output_chunk_length=1)
    m_lgbm_lift.fit(lift_train, future_covariates=cov_ts)
    pred_lgbm_lift = m_lgbm_lift.predict(len(lift_val), future_covariates=cov_ts)
    err_lgbm_lift = calculate_wape(lift_val, pred_lgbm_lift)

    logger.info(f"Prophet Lift WAPE: {err_prophet_lift:.2f}%")
    logger.info(f"LightGBM Lift WAPE: {err_lgbm_lift:.2f}%")

    # --- Final Verdict ---
    logger.info("=== Final Verdict ===")
    if err_prophet_base < err_lgbm_base:
        logger.info("Verdict: Prophet is better for Base Demand.")
    else:
        logger.info("Verdict: LightGBM is better for Base Demand.")

    if err_lgbm_lift < err_prophet_lift:
        logger.info("Verdict: LightGBM is better for Lift Demand (Promotion).")
    else:
        logger.info("Verdict: Prophet is better for Lift Demand (Promotion).")


if __name__ == "__main__":
    compare_models()
