"""
Demand Forecasting Engine.
Wraps LightGBM with probabilistic and breakdown capabilities.
"""
import logging
from typing import Any

import numpy as np
import optuna
import polars as pl
from darts import TimeSeries
from darts.models import LightGBMModel

from .config import COL_DATE
from .data_utils import calculate_metrics

logger = logging.getLogger(__name__)

def get_tuned_sim_model(item_id: int, decomposed_df: pl.DataFrame) -> tuple[LightGBMModel, TimeSeries, pl.DataFrame]:
    from .config import COL_DATE, COL_ITEM_ID, COL_SALES
    actual_df = decomposed_df.filter((pl.col(COL_ITEM_ID) == item_id) & (pl.col(COL_SALES).is_not_null()))
    actual_df = add_temporal_features(actual_df)
    actual_pandas_df = actual_df.to_pandas()
    lift_series = TimeSeries.from_dataframe(actual_pandas_df, COL_DATE, "estimated_lift", freq="D")
    covariate_series = TimeSeries.from_dataframe(actual_pandas_df, COL_DATE, ["actual_price", "flyer", "discount_rate", "day_of_week", "month", "year", "time_idx"], freq="D")
    simulator_model = LightGBMModel(lags=14, lags_future_covariates=(0,1), output_chunk_length=1, n_estimators=200, likelihood="quantile", quantiles=[0.1, 0.5, 0.9], verbose=-1)
    simulator_model.fit(lift_series, future_covariates=covariate_series)
    return simulator_model, lift_series, actual_df

def add_temporal_features(df: pl.DataFrame) -> pl.DataFrame:
    """Standardized feature engineering in Polars."""
    return df.with_columns([
        pl.col(COL_DATE).dt.weekday().alias("day_of_week"),
        pl.col(COL_DATE).dt.month().alias("month"),
        pl.col(COL_DATE).dt.year().alias("year"),
        ((pl.col(COL_DATE) - pl.date(2021, 1, 1)).dt.total_days()).alias("time_idx")
    ])


def _slice_forecast_window(covariate_series: TimeSeries, train_series: TimeSeries, horizon: int) -> TimeSeries:
    """Slice the covariate window that lines up with ``predict(horizon)``.

    ``predict`` forecasts ``horizon`` steps starting the day after ``train_series``
    ends. We slice that exact window from the (longer) covariate series by date so
    the neutral-covariate counterfactual cannot drift onto the wrong dates if the
    covariate range and the forecast horizon stop disagreeing.
    """
    freq = covariate_series.freq
    forecast_start = train_series.end_time() + freq
    forecast_end = forecast_start + freq * (horizon - 1)
    return covariate_series.slice(forecast_start, forecast_end)

class ForecastEngine:
    def __init__(self, n_estimators: int = 500, learning_rate: float = 0.05) -> None:
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.covariate_columns = ["actual_price", "flyer", "discount_rate", "day_of_week", "month", "year", "time_idx"]

    def tune_lgbm(self, train_series: TimeSeries, val_series: TimeSeries, covariate_series: TimeSeries, n_trials: int = 5) -> dict[str, Any]:
        """Auto-tunes LGBM using Optuna."""
        def objective(trial: optuna.Trial) -> float:
            lgbm_model = LightGBMModel(
                lags=trial.suggest_int("lags", 7, 28),
                lags_future_covariates=(0, 1),
                output_chunk_length=1,
                n_estimators=self.n_estimators,
                learning_rate=self.learning_rate,
                likelihood="quantile", quantiles=[0.1, 0.5, 0.9],
                verbose=-1
            )
            lgbm_model.fit(train_series, future_covariates=covariate_series)
            val_prediction = lgbm_model.predict(len(val_series), future_covariates=covariate_series, num_samples=100)
            _, wape, _ = calculate_metrics(val_series.values(), val_prediction.mean().values())
            return wape

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials)
        return study.best_params

    def get_lgbm_breakdown(self, train_series: TimeSeries, covariate_series: TimeSeries, horizon: int, list_price: float, params: dict[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Fits LGBM and returns (mean, base, lift, lower, upper).

        Base is extracted via neutral-covariate counterfactual:
        predict with price=list_price, flyer=0, discount_rate=0.
        """
        lgbm_params = {"lags": 14, "num_leaves": 31, "min_child_samples": 5}
        if params: lgbm_params.update(params)

        lgbm_model = LightGBMModel(
            lags=lgbm_params["lags"], lags_future_covariates=(0, 1), output_chunk_length=1,
            n_estimators=self.n_estimators, learning_rate=self.learning_rate,
            num_leaves=lgbm_params.get("num_leaves", 31), min_child_samples=lgbm_params.get("min_child_samples", 5),
            likelihood="quantile", quantiles=[0.1, 0.5, 0.9], verbose=-1
        )
        lgbm_model.fit(train_series, future_covariates=covariate_series)
        total_forecast = lgbm_model.predict(horizon, future_covariates=covariate_series, num_samples=100)

        # Neutral-covariate window must match the predict() horizon, which starts
        # the day after train_series ends — NOT the tail of the full covariate
        # series. Tail-slicing only happens to align when the covariate series
        # ends exactly `horizon` days after training; deriving the window from the
        # forecast start instead makes it leak-proof against any range mismatch.
        forecast_cov = _slice_forecast_window(covariate_series, train_series, horizon)
        covariate_df = forecast_cov.to_dataframe()
        neutral_covariate_df = covariate_df.copy()
        neutral_covariate_df["actual_price"] = float(list_price)
        neutral_covariate_df["flyer"] = 0.0
        neutral_covariate_df["discount_rate"] = 0.0
        neutral_covariate_series = TimeSeries.from_dataframe(neutral_covariate_df.reset_index(), COL_DATE, self.covariate_columns, freq="D")

        base_forecast = lgbm_model.predict(horizon, future_covariates=neutral_covariate_series, num_samples=100)
        base_forecast_values = base_forecast.quantile(0.5).values().flatten()
        lift_forecast_values = total_forecast.quantile(0.5).values().flatten() - base_forecast_values
        return total_forecast.mean().values().flatten(), base_forecast_values, lift_forecast_values, total_forecast.quantile(0.1).values().flatten(), total_forecast.quantile(0.9).values().flatten()

    def get_hybrid_forecast(self, base_train_series: TimeSeries, lift_train_series: TimeSeries, covariate_series: TimeSeries, horizon: int, lgbm_params: dict[str, Any] | None = None, list_price: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """LGBM Base + LGBM Lift with probabilistic confidence bands.

        Trains on total (base + lift) series, then extracts base via the
        neutral-covariate counterfactual (price=list_price, flyer=0, discount=0).
        """
        params = {"lags": 14, "min_child_samples": 5}
        if lgbm_params: params.update(lgbm_params)

        # Reconstruct total series from decomposed base + lift
        base_pd = base_train_series.to_dataframe()
        lift_pd = lift_train_series.to_dataframe()
        base_col = base_pd.columns[0]
        lift_col = lift_pd.columns[0]
        total_pd = base_pd.copy()
        total_pd[base_col] = base_pd[base_col].values + lift_pd[lift_col].values
        total_train_series = TimeSeries.from_dataframe(total_pd, value_cols=base_col, freq="D")

        lgbm_model = LightGBMModel(
            lags=params["lags"], lags_future_covariates=(0, 1), output_chunk_length=1,
            n_estimators=self.n_estimators, learning_rate=self.learning_rate,
            likelihood="quantile", quantiles=[0.1, 0.5, 0.9], verbose=-1
        )
        lgbm_model.fit(total_train_series, future_covariates=covariate_series)
        total_forecast = lgbm_model.predict(horizon, future_covariates=covariate_series, num_samples=100)

        forecast_cov = _slice_forecast_window(covariate_series, total_train_series, horizon)
        cov_df = forecast_cov.to_dataframe()
        neutral_df = cov_df.copy()
        neutral_price = float(list_price) if list_price is not None else float(cov_df["actual_price"].max())
        neutral_df["actual_price"] = neutral_price
        neutral_df["flyer"] = 0.0
        neutral_df["discount_rate"] = 0.0
        neutral_series = TimeSeries.from_dataframe(neutral_df.reset_index(), "date", self.covariate_columns, freq="D")

        base_forecast = lgbm_model.predict(horizon, future_covariates=neutral_series, num_samples=100)

        base = base_forecast.quantile(0.5).values().flatten()
        lift = (total_forecast.quantile(0.5).values().flatten() - base).clip(min=0)
        # Confidence bands are taken directly from total_forecast quantiles.
        # total_forecast already captures all uncertainty (base + lift combined),
        # so its quantiles are the correct 10th/90th percentile bounds.
        lower = total_forecast.quantile(0.1).values().flatten()
        upper = total_forecast.quantile(0.9).values().flatten()
        return base, lift, lower, upper
