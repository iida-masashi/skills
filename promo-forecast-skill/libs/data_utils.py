"""
SCM Business Logic and Data Utilities.
Fixed Polars compatibility for date_range in explode_calendar.
"""
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
from darts import TimeSeries

from .config import (
    COL_CAMP_COST,
    COL_DATE,
    COL_ITEM_ID,
    COL_PRICE_ACT,
    COL_PRICE_LIST,
    COL_PROMO_NAME,
    COL_SALES,
    COL_UNIT_COST,
    DECOMPOSED_FILE,
    FORECAST_FILE,
    MASTER_FILE,
    map_promo_tier,
)


def load_csv_with_date(filepath: str | Path, date_col: str = "date") -> pl.DataFrame:
    return pl.read_csv(filepath).with_columns(pl.col(date_col).str.to_date())

def to_time_series(df: pl.DataFrame, time_col: str, value_col: str | list[str]) -> TimeSeries:
    return TimeSeries.from_dataframe(df.to_pandas(), time_col, value_col, freq="D")

def get_date_item_skeleton(start_date: date, end_date: date, item_ids: list[int]) -> pl.DataFrame:
    skeleton_dates = pl.date_range(start_date, end_date, interval="1d", eager=True).alias("date")
    return skeleton_dates.to_frame().join(pl.DataFrame({"item_id": item_ids}), how="cross")


def calculate_metrics(actual: Sequence[float] | np.ndarray, pred: Sequence[float] | np.ndarray) -> tuple[float, float, float]:
    """Return (MAPE%, WAPE%, RMSE).

    MAPE is averaged over strictly-positive actuals (its denominator is undefined
    at zero); WAPE divides by the sum of |actual| over ALL points. When the
    relevant denominator is zero the percentage error is genuinely undefined, so
    we return NaN rather than 0.0 — a zero-demand series must not masquerade as a
    perfect (0% error) forecast.
    """
    actual_arr, pred_arr = np.asarray(actual, dtype=float), np.asarray(pred, dtype=float)
    mask = actual_arr > 0
    mape = float(np.mean(np.abs((actual_arr[mask] - pred_arr[mask]) / actual_arr[mask])) * 100) if mask.any() else float("nan")
    total_actual = float(np.sum(np.abs(actual_arr)))
    wape = float(np.sum(np.abs(actual_arr - pred_arr)) / total_actual * 100) if total_actual > 0 else float("nan")
    rmse = float(np.sqrt(np.mean((actual_arr - pred_arr) ** 2))) if actual_arr.size > 0 else float("nan")
    return mape, wape, rmse


def calculate_bias(actual: Sequence[float] | np.ndarray, pred: Sequence[float] | np.ndarray) -> float:
    """Directional forecast bias as a percentage: sum(pred - actual) / sum(actual) * 100.

    WAPE/MAPE measure error magnitude but cancel direction, so a forecast that is
    systematically too high (excess inventory) scores the same as one too low
    (stockouts). Bias exposes that direction: positive = over-forecast (excess
    inventory risk), negative = under-forecast (stockout risk). Undefined (NaN)
    when total actual is zero.
    """
    actual_arr, pred_arr = np.asarray(actual, dtype=float), np.asarray(pred, dtype=float)
    total_actual = float(np.sum(actual_arr))
    if total_actual == 0:
        return float("nan")
    return float(np.sum(pred_arr - actual_arr) / total_actual * 100)

def calibrate_bands(
    actual_backtest: np.ndarray,
    point_backtest: np.ndarray,
    point_forecast: np.ndarray,
    coverage: float = 0.80,
) -> tuple[np.ndarray, np.ndarray]:
    """Empirical (conformal-style) prediction bands calibrated on backtest error.

    The raw LightGBM quantiles only capture in-training noise, so the nominal
    "80% interval" covered ~26% of actuals. Instead we measure the realised
    forecast error on the held-out backtest window (``actual - point``) and apply
    its empirical lower/upper quantiles to the point forecast. This is the
    split-conformal idea: the band width is set by how wrong the model actually
    was, not by the model's own optimistic spread.

    Returns (lower, upper) arrays the same length as ``point_forecast``. Lower is
    clipped at zero since demand cannot be negative.
    """
    residuals = np.asarray(actual_backtest, dtype=float) - np.asarray(point_backtest, dtype=float)
    residuals = residuals[~np.isnan(residuals)]
    if residuals.size == 0:
        # No basis to widen — fall back to the point forecast itself.
        pf = np.asarray(point_forecast, dtype=float)
        return pf.clip(min=0), pf
    tail = (1.0 - coverage) / 2.0
    q_lo = float(np.quantile(residuals, tail))
    q_hi = float(np.quantile(residuals, 1.0 - tail))
    pf = np.asarray(point_forecast, dtype=float)
    lower = (pf + q_lo).clip(min=0)
    upper = pf + q_hi
    return lower, np.maximum(upper, lower)


def load_data() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    master_df = pl.read_csv(MASTER_FILE)
    decomposed_df = load_csv_with_date(DECOMPOSED_FILE, COL_DATE)
    forecast_df = load_csv_with_date(FORECAST_FILE, COL_DATE)
    return master_df, decomposed_df, forecast_df

def explode_calendar(calendar_df: pl.DataFrame) -> pl.DataFrame:
    """Robustly expands start/end dates into daily rows using map_elements for compatibility."""
    df = calendar_df.with_columns([
        pl.col("start_date").cast(pl.Date),
        pl.col("end_date").cast(pl.Date)
    ])

    # Use map_elements to ensure it works on older Polars versions where date_range(col, col) fails
    return df.with_columns(
        pl.struct(["start_date", "end_date"]).map_elements(
            lambda s: pl.date_range(s["start_date"], s["end_date"], interval="1d", eager=True),
            return_dtype=pl.List(pl.Date)
        ).alias(COL_DATE)
    ).explode(COL_DATE).drop(["start_date", "end_date"])

def get_campaign_summary(df: pl.DataFrame) -> pl.DataFrame:
    blocks = (
        df.sort(COL_DATE)
        .with_columns([
            (pl.col(COL_PROMO_NAME) != pl.col(COL_PROMO_NAME).shift(1)).fill_null(True).cum_sum().alias("block_id")
        ])
    )
    summary = (
        blocks.filter(pl.col(COL_PROMO_NAME) != "通常販売")
        .group_by("block_id")
        .agg([
            pl.col(COL_PROMO_NAME).first().alias("販促名"),
            pl.col(COL_DATE).min().alias("開始"),
            pl.col(COL_DATE).max().alias("終了"),
            pl.col(COL_SALES).sum().alias("総数量"),
            pl.col("estimated_lift").sum().alias("増分数量"),
            pl.col(COL_CAMP_COST).sum().alias("販促費用"),
            ((pl.col(COL_PRICE_ACT) - pl.col(COL_UNIT_COST)) * pl.col(COL_SALES)).sum().alias("販促時粗利"),
            ((pl.col(COL_PRICE_LIST) - pl.col(COL_UNIT_COST)) * pl.col("estimated_base")).sum().alias("推定定番粗利")
        ])
    )
    if summary.is_empty(): return summary
    return (
        summary.with_columns([(pl.col("販促時粗利") - pl.col("推定定番粗利")).alias("増分粗利")])
        .with_columns([(pl.col("増分粗利") / pl.col("販促費用") * 100).fill_nan(0).alias("ROI (%)")])
        .sort("開始", descending=True)
    )

def get_tier_efficiency_summary(campaign_summary_df: pl.DataFrame) -> pl.DataFrame:
    if campaign_summary_df.is_empty(): return campaign_summary_df
    return (
        campaign_summary_df
        .with_columns(pl.col("販促名").map_elements(map_promo_tier, return_dtype=pl.String).alias("ランク"))
        .group_by("ランク")
        .agg([
            pl.count("ランク").alias("回数"),
            pl.col("ROI (%)").mean().alias("平均ROI"),
            pl.col("増分粗利").sum().alias("総・増分粗利"),
            pl.col("増分数量").sum().alias("総・増分数量"),
            (pl.col("増分数量").sum() / pl.col("販促費用").sum()).alias("1円あたり数量増")
        ]).sort("平均ROI", descending=True)
    )


def get_promo_blocks(df: pl.DataFrame) -> pl.DataFrame:
    """Detect contiguous promo blocks and return summary with tier labels.

    Returns DataFrame with columns:
        promo_name, start_date, end_date, tier, avg_discount_rate
    """
    filtered = df.filter(pl.col(COL_PROMO_NAME) != "通常販売").sort(COL_DATE)
    if filtered.is_empty():
        return pl.DataFrame(schema={
            COL_PROMO_NAME: pl.String, "start_date": pl.Date,
            "end_date": pl.Date, "tier": pl.String, "avg_discount_rate": pl.Float64,
        })
    blocks = filtered.with_columns(
        (pl.col(COL_PROMO_NAME) != pl.col(COL_PROMO_NAME).shift(1))
        .fill_null(True).cum_sum().alias("block_id")
    )
    summary = blocks.group_by("block_id").agg([
        pl.col(COL_PROMO_NAME).first(),
        pl.col(COL_DATE).min().alias("start_date"),
        pl.col(COL_DATE).max().alias("end_date"),
        pl.col("discount_rate").mean().alias("avg_discount_rate"),
    ]).with_columns(
        pl.col(COL_PROMO_NAME).map_elements(map_promo_tier, return_dtype=pl.String).alias("tier")
    ).drop("block_id").sort("start_date")
    return summary


def get_all_items_campaign_summary(
    decomposed_df: pl.DataFrame,
    master_df: pl.DataFrame,
) -> pl.DataFrame:
    """Compute campaign summary for all items, with item_name column."""
    summaries: list[pl.DataFrame] = []
    for item_id in decomposed_df[COL_ITEM_ID].unique().sort().to_list():
        item_df = decomposed_df.filter(pl.col(COL_ITEM_ID) == item_id)
        summary = get_campaign_summary(item_df)
        if not summary.is_empty():
            summary = summary.with_columns(pl.lit(item_id).alias(COL_ITEM_ID))
            summaries.append(summary)
    if not summaries:
        return pl.DataFrame()
    result = pl.concat(summaries)
    return result.join(master_df.select([COL_ITEM_ID, "item_name"]), on=COL_ITEM_ID)


def sweep_price_elasticity(
    simulator_model: object,
    lift_series: object,
    training_df: pl.DataFrame,
    base_demand: np.ndarray,
    today_date: date,
    unit_cost: float,
    list_price: float,
    future_days: int,
    step: int = 10,
    flyer: bool = True,
) -> pl.DataFrame:
    """Sweep price from unit_cost to list_price and return elasticity data.

    Returns DataFrame with columns:
        price, discount_rate, total_lift, total_quantity, incremental_profit
    """
    from .models import add_temporal_features

    cov_cols = ["actual_price", "flyer", "discount_rate", "day_of_week", "month", "year", "time_idx"]
    schema = training_df.select(cov_cols).schema
    sim_start = today_date + timedelta(days=1)
    sim_end = today_date + timedelta(days=future_days)
    sim_dates = pl.date_range(sim_start, sim_end, interval="1d", eager=True)
    base_total = float(np.sum(base_demand))
    baseline_profit = (list_price - unit_cost) * base_total

    rows: list[dict[str, float]] = []
    for price in range(int(unit_cost), int(list_price) + 1, step):
        disc = (list_price - price) / list_price
        cov_df = add_temporal_features(pl.DataFrame({
            COL_DATE: sim_dates,
            "actual_price": [float(price)] * future_days,
            "flyer": [1 if flyer else 0] * future_days,
            "discount_rate": [disc] * future_days,
        })).cast(schema)
        full_cov = pl.concat([
            training_df.select(cov_cols + [COL_DATE]),
            cov_df.select(cov_cols + [COL_DATE]),
        ])
        full_cov_series = TimeSeries.from_dataframe(
            full_cov.to_pandas(), COL_DATE, cov_cols, freq="D"
        )
        forecast = simulator_model.predict(
            future_days, series=lift_series,
            future_covariates=full_cov_series, num_samples=100,
        )
        promo_lift = forecast.quantile(0.5).values().flatten().clip(min=0)
        total_lift = float(np.sum(promo_lift))
        total_qty = base_total + total_lift
        inc_profit = (price - unit_cost) * total_qty - baseline_profit
        rows.append({
            "price": float(price),
            "discount_rate": disc,
            "total_lift": total_lift,
            "total_quantity": total_qty,
            "incremental_profit": inc_profit,
        })
    return pl.DataFrame(rows)
