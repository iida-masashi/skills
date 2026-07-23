"""Walk-forward (multi-origin) backtest validation.

The pipeline's headline accuracy comes from a single 180-day holdout, which can
be lucky or unlucky. This script runs a proper walk-forward backtest: it expands
the training window across several forecast origins and reports WAPE/Bias
mean +/- std across them, so accuracy can be judged for stability rather than a
single draw. Uses darts' native historical_forecasts.

Run: python scripts/validate_walkforward.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.absolute()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging

import numpy as np
import polars as pl
from darts import TimeSeries
from darts.models import LightGBMModel
from libs.config import BACKTEST_DAYS, COL_DATE, COL_ITEM_ID, COL_SALES, DECOMPOSED_FILE, ITEMS
from libs.data_utils import calculate_bias, calculate_metrics, load_csv_with_date, to_time_series
from libs.models import ForecastEngine, add_temporal_features

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Walk-forward config: evaluate every STRIDE days over the last BACKTEST_DAYS,
# forecasting HORIZON days ahead from each origin.
HORIZON = 30
STRIDE = 30


def _origin_metrics(actual: TimeSeries, forecast: TimeSeries) -> tuple[float, float]:
    a = actual.slice_intersect(forecast).values().flatten()
    f = forecast.slice_intersect(actual).values().flatten()
    n = min(len(a), len(f))
    _, wape, _ = calculate_metrics(a[:n], f[:n])
    bias = calculate_bias(a[:n], f[:n])
    return wape, bias


def validate() -> pl.DataFrame:
    decomposed_df = load_csv_with_date(DECOMPOSED_FILE, COL_DATE)
    engine = ForecastEngine()
    rows: list[dict[str, object]] = []

    for item_id in sorted(decomposed_df[COL_ITEM_ID].unique().to_list()):
        item_full = add_temporal_features(decomposed_df.filter(pl.col(COL_ITEM_ID) == item_id))
        actual_df = item_full.filter(pl.col(COL_SALES).is_not_null())
        total = to_time_series(actual_df, COL_DATE, COL_SALES)
        cov = to_time_series(item_full, COL_DATE, engine.covariate_columns)

        model = LightGBMModel(
            lags=14, lags_future_covariates=(0, 1), output_chunk_length=1,
            n_estimators=300, learning_rate=0.05,
            likelihood="quantile", quantiles=[0.1, 0.5, 0.9], verbose=-1,
        )
        # First origin starts BACKTEST_DAYS before the end; expand forward by STRIDE.
        start = total.time_index[-BACKTEST_DAYS]
        hist = model.historical_forecasts(
            total, future_covariates=cov, start=start, forecast_horizon=HORIZON,
            stride=STRIDE, retrain=True, last_points_only=False, verbose=False,
        )
        wapes, biases = [], []
        for fc in hist:
            w, b = _origin_metrics(total, fc.quantile(0.5) if fc.is_stochastic else fc)
            if not np.isnan(w):
                wapes.append(w); biases.append(b)
        if not wapes:
            continue
        rows.append({
            "品目": ITEMS[item_id],
            "origin数": len(wapes),
            "WAPE平均%": round(float(np.mean(wapes)), 1),
            "WAPE標準偏差%": round(float(np.std(wapes)), 1),
            "WAPE最悪%": round(float(np.max(wapes)), 1),
            "バイアス平均%": round(float(np.mean(biases)), 1),
        })
    return pl.DataFrame(rows)


def main() -> None:
    result = validate()
    logger.info("=" * 70)
    logger.info(f"Walk-forward 検証 (horizon={HORIZON}日, stride={STRIDE}日)")
    logger.info("=" * 70)
    with pl.Config(tbl_rows=10, tbl_cols=8, tbl_width_chars=100):
        logger.info(str(result))
    logger.info("")
    logger.info("[読み方] 複数originでの WAPE 平均±標準偏差。標準偏差が小さいほど精度が安定。")
    logger.info("         単一ホールドアウトの数値が運に左右されていないかの確認に使う。")


if __name__ == "__main__":
    main()
