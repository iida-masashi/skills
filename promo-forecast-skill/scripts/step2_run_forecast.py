"""
Step 2: Strategic Forecasting.
Predicts 180d backtest + 180d future with Confidence Bands.
Follows Quality Gate standards.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.absolute()
if str(ROOT_DIR) not in sys.path: sys.path.insert(0, str(ROOT_DIR))

import logging
from datetime import timedelta

import numpy as np
import pandas as pd
import polars as pl
from libs.config import (
    BACKTEST_DAYS,
    COL_DATE,
    COL_ITEM_ID,
    COL_SALES,
    DECOMPOSED_FILE,
    DEFAULT_OPTUNA_TRIALS,
    FORECAST_FILE,
)
from libs.data_utils import calibrate_bands, load_csv_with_date, to_time_series
from libs.models import ForecastEngine, add_temporal_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def _forecast_one_item(item_id: int, decomposed_df: pl.DataFrame, n_trials: int) -> pl.DataFrame:
    """Forecast a single item. Module-level so it can be pickled for parallel runs."""
    engine = ForecastEngine()
    logger.info(f"Forecasting for item_id: {item_id}")
    item_full_df = decomposed_df.filter(pl.col(COL_ITEM_ID) == item_id)
    item_full_df = add_temporal_features(item_full_df)

    actual_df = item_full_df.filter(pl.col(COL_SALES).is_not_null())
    max_actual_date = actual_df[COL_DATE].max()
    backtest_start_date = pd.Timestamp(max_actual_date - timedelta(days=BACKTEST_DAYS - 1))

    actual_pandas_df = actual_df.to_pandas()

    total_series = to_time_series(actual_df, COL_DATE, COL_SALES)
    base_series = to_time_series(actual_df, COL_DATE, "estimated_base")
    lift_series = to_time_series(actual_df, COL_DATE, "estimated_lift")
    covariate_series = to_time_series(item_full_df, COL_DATE, engine.covariate_columns)

    total_train_series, _ = total_series.split_before(backtest_start_date)
    train_subseries, val_subseries = total_train_series.split_after(len(total_train_series) - 31)
    best_params = engine.tune_lgbm(train_subseries, val_subseries, covariate_series, n_trials=n_trials)

    future_rows = item_full_df.filter(pl.col(COL_SALES).is_null()).height
    total_horizon = BACKTEST_DAYS + future_rows

    base_train_series = base_series.split_before(backtest_start_date)[0]
    lift_train_series  = lift_series.split_before(backtest_start_date)[0]

    item_list_price = actual_pandas_df["list_price"].iloc[0]
    hybrid_base, hybrid_lift, hybrid_lower, hybrid_upper = engine.get_hybrid_forecast(
        base_train_series, lift_train_series,
        covariate_series, total_horizon, lgbm_params=best_params, list_price=item_list_price
    )
    _, lgbm_base, lgbm_lift, _, _ = engine.get_lgbm_breakdown(total_train_series, covariate_series, total_horizon, actual_pandas_df["list_price"].iloc[0], params=best_params)

    # Calibrate confidence bands on realised backtest error (conformal-style).
    # The raw LGBM quantiles only capture in-training noise and covered ~26%
    # of actuals at the nominal 80% level. We instead size the band from how
    # wrong the point forecast actually was over the backtest window.
    hybrid_point = hybrid_base + hybrid_lift
    actual_backtest = actual_df.tail(BACKTEST_DAYS)[COL_SALES].to_numpy()
    hybrid_lower, hybrid_upper = calibrate_bands(
        actual_backtest, hybrid_point[:BACKTEST_DAYS], hybrid_point, coverage=0.80
    )

    # FIXED: Use scalar values for pl.date_range (map_elements not needed here since eager)
    forecast_start_date, forecast_end_date = backtest_start_date, item_full_df[COL_DATE].max()
    dates = pl.date_range(forecast_start_date, forecast_end_date, interval="1d", eager=True)

    return pl.DataFrame({
        COL_DATE: dates,
        COL_ITEM_ID: [item_id] * len(dates),
        "actual_total": np.concatenate([actual_df.tail(BACKTEST_DAYS)[COL_SALES].to_numpy(), np.full(future_rows, np.nan)]),
        "forecast_hybrid_base": hybrid_base, "forecast_hybrid_lift": hybrid_lift,
        "forecast_hybrid_lower": hybrid_lower, "forecast_hybrid_upper": hybrid_upper,
        "forecast_lgbm_base": lgbm_base, "forecast_lgbm_lift": lgbm_lift
    })


def run_forecast(n_trials: int = DEFAULT_OPTUNA_TRIALS) -> None:
    """Forecast every item sequentially.

    Item-level parallelism was measured and rejected: LightGBM fit/predict
    already saturate all CPU cores per item, so running items concurrently only
    adds thread oversubscription (threads: 93s -> 121s) or process spawn cost
    (loky: 93s -> 125s). Speedups instead come from cheaper per-item work.
    """
    if not DECOMPOSED_FILE.exists(): raise FileNotFoundError("Run Step 1 first.")

    decomposed_df = load_csv_with_date(DECOMPOSED_FILE, COL_DATE)
    item_ids = decomposed_df[COL_ITEM_ID].unique().sort().to_list()
    all_results = [_forecast_one_item(i, decomposed_df, n_trials) for i in item_ids]

    pl.concat(all_results).sort([COL_ITEM_ID, COL_DATE]).write_csv(FORECAST_FILE)
    logger.info("Step 2 complete.")

if __name__ == "__main__": run_forecast()
