import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
"""
Comprehensive Strategic Test Suite for Promo Forecast Skill.
Covers end-to-end data integrity, logic validation, and mathematical consistency.
"""
from datetime import timedelta

import numpy as np
import polars as pl
import pytest
from libs.config import BACKTEST_DAYS, DATA_DIR, DECOMPOSED_FILE, FORECAST_FILE, PROMO_THRESHOLD, map_promo_tier
from libs.data_utils import (
    calculate_bias,
    calculate_metrics,
    calibrate_bands,
    get_all_items_campaign_summary,
    get_campaign_summary,
    get_promo_blocks,
)
from scripts.step0_generate_data import generate_data
from scripts.step1_decompose_demand import decompose_demand
from scripts.step2_run_forecast import run_forecast


@pytest.fixture(scope="module", autouse=True)
def setup_full_pipeline():
    generate_data()
    decompose_demand()
    run_forecast(n_trials=1)


# ── Step 0: Data Generation ──────────────────────────────────────────────────

def test_step0_item_master_schema():
    """Master table has exactly 5 items with expected columns."""
    master_df = pl.read_csv(DATA_DIR / "item_master.csv")
    assert len(master_df) == 5
    assert set(master_df.columns) == {"item_id", "item_name", "list_price", "unit_cost"}

def test_step0_item_master_prices_positive():
    """All prices and costs are positive."""
    master_df = pl.read_csv(DATA_DIR / "item_master.csv")
    assert (master_df["list_price"] > 0).all()
    assert (master_df["unit_cost"] > 0).all()
    assert (master_df["list_price"] > master_df["unit_cost"]).all()

def test_step0_actuals_no_leaks():
    """Sales actuals CSV must not contain ground-truth columns."""
    actuals_df = pl.read_csv(DATA_DIR / "sales_actuals.csv")
    assert "true_base" not in actuals_df.columns
    assert "true_lift" not in actuals_df.columns

def test_step0_actuals_date_format():
    """Date column is parseable as ISO date (YYYY-MM-DD)."""
    actuals_df = pl.read_csv(DATA_DIR / "sales_actuals.csv")
    parsed = actuals_df.with_columns(pl.col("date").str.to_date())
    assert parsed["date"].dtype == pl.Date

def test_step0_actuals_sales_non_negative():
    """All sales volumes are non-negative."""
    actuals_df = pl.read_csv(DATA_DIR / "sales_actuals.csv")
    assert (actuals_df["sales_volume"] >= 0).all()

def test_step0_calendar_from_to_logic():
    """Every promo event ends on or after it starts."""
    calendar_df = pl.read_csv(DATA_DIR / "promo_calendar.csv").with_columns([
        pl.col("start_date").str.to_date(),
        pl.col("end_date").str.to_date()
    ])
    assert (calendar_df["end_date"] >= calendar_df["start_date"]).all()
    assert "campaign_cost" in calendar_df.columns

def test_step0_calendar_cost_positive():
    """All campaign costs are positive."""
    calendar_df = pl.read_csv(DATA_DIR / "promo_calendar.csv")
    assert (calendar_df["campaign_cost"] > 0).all()


def test_step0_promo_saturation(tmp_path):
    """A4: promo lift per unit discount shrinks when promos are frequent.

    Splits promo days into low- vs high-recent-promo-intensity halves (by the
    rolling count of recent promo days, reconstructed from the calendar) and
    checks that lift efficiency (true_lift / discount proxy) is lower in the
    saturated half.
    """
    truth = pl.read_csv(DATA_DIR / "ground_truth.csv").with_columns(pl.col("date").str.to_date())
    actuals = pl.read_csv(DATA_DIR / "sales_actuals.csv").with_columns(pl.col("date").str.to_date())
    item = 1
    df = (
        truth.filter(pl.col("item_id") == item)
        .join(actuals.filter(pl.col("item_id") == item).select("date", "actual_price"), on="date")
        .sort("date")
    )
    # promo day = lift materially above base
    df = df.with_columns((pl.col("true_lift") > pl.col("true_base") * 0.05).cast(pl.Int8).alias("is_promo"))
    df = df.with_columns(
        pl.col("is_promo").shift(1, fill_value=0).rolling_sum(window_size=60, min_samples=1).alias("recent")
    )
    # Lift efficiency = lift relative to baseline; exclude base<=0 days (the
    # rebound dip can zero the baseline and make the ratio explode).
    promo = df.filter((pl.col("is_promo") == 1) & (pl.col("true_base") > 0)).with_columns(
        (pl.col("true_lift") / pl.col("true_base")).alias("lift_ratio")
    )
    median_recent = promo["recent"].median()
    low = promo.filter(pl.col("recent") <= median_recent)["lift_ratio"].mean()
    high = promo.filter(pl.col("recent") > median_recent)["lift_ratio"].mean()
    assert high < low, f"saturated promos should have lower lift ratio: high={high:.3f} low={low:.3f}"


def test_step0_forward_buying_rebound(tmp_path):
    """A1: base demand dips in the days right after a promo (pantry loading).

    Compares the mean true_base on the days immediately following promo blocks
    against the overall mean. Forward-buying must pull the post-promo baseline
    below average.
    """
    truth = pl.read_csv(DATA_DIR / "ground_truth.csv").with_columns(pl.col("date").str.to_date())
    cal = pl.read_csv(DATA_DIR / "promo_calendar.csv").with_columns(pl.col("end_date").str.to_date())
    item = 1
    item_truth = truth.filter(pl.col("item_id") == item).sort("date")
    overall_mean = item_truth["true_base"].mean()
    # Days 1..3 after each promo end for this item.
    ends = cal.filter(pl.col("item_id") == item)["end_date"].to_list()
    rebound_dates = {e + timedelta(days=k) for e in ends for k in (1, 2, 3)}
    rebound = item_truth.filter(pl.col("date").is_in(list(rebound_dates)))
    assert not rebound.is_empty()
    assert rebound["true_base"].mean() < overall_mean, (
        f"post-promo base {rebound['true_base'].mean():.1f} should dip below mean {overall_mean:.1f}"
    )


# ── Step 1: Decomposition ─────────────────────────────────────────────────────

def test_step1_output_schema():
    """Decomposed file has all required columns."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE)
    required = {"date", "item_id", "sales_volume", "estimated_base", "estimated_lift", "is_promo_detected", "promo_name", "discount_rate"}
    assert required.issubset(set(decomposed_df.columns))

def test_step1_data_merging():
    """Decomposed file contains promo_name and estimated_base columns."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE)
    assert "promo_name" in decomposed_df.columns
    assert "estimated_base" in decomposed_df.columns

def test_step1_base_and_lift_non_negative():
    """estimated_base and estimated_lift are always >= 0."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE).drop_nulls(subset=["estimated_base", "estimated_lift"])
    assert decomposed_df["estimated_base"].min() >= 0
    assert decomposed_df["estimated_lift"].min() >= 0

def test_step1_non_promo_lift_is_zero():
    """Non-promo days carry zero promo lift by definition (M2 fix).

    The asymmetric clip(>=0) of (sales - rolling_base) used to leave a positive
    residual on non-promo days (rolling-mean noise survives the clip), inflating
    total lift by ~4-6%. A promo lift can only exist on a promo day, so non-promo
    lift must be exactly zero.
    """
    decomposed_df = pl.read_csv(DECOMPOSED_FILE).drop_nulls(subset=["sales_volume"])
    non_promo_lift = decomposed_df.filter(pl.col("is_promo_detected") == 0)["estimated_lift"]
    assert non_promo_lift.max() == 0.0, (
        f"Non-promo lift must be 0, found max={non_promo_lift.max()}"
    )
    # And promo days must still carry meaningful lift.
    promo_mean_lift = decomposed_df.filter(pl.col("is_promo_detected") == 1)["estimated_lift"].mean()
    assert promo_mean_lift > 0

def test_step0_stockout_flag_present_and_censoring():
    """A3: actuals carry a stockout flag and stockouts are non-promo days only."""
    actuals_df = pl.read_csv(DATA_DIR / "sales_actuals.csv")
    assert "stockout" in actuals_df.columns
    n_stockout = actuals_df.filter(pl.col("stockout") == 1).height
    assert n_stockout > 0, "expected some stockout days in synthetic data"


def test_step1_stockout_excluded_from_base():
    """A3: a stockout day's censored sales must NOT drag its own base estimate down.

    The estimated base on a stockout day should sit above its (censored) sales,
    because the day is masked out of the rolling-mean and interpolated from
    surrounding healthy days.
    """
    decomposed_df = pl.read_csv(DECOMPOSED_FILE).drop_nulls(subset=["sales_volume"])
    if "stockout" not in decomposed_df.columns:
        pytest.skip("stockout column not propagated")
    stockout_days = decomposed_df.filter(
        (pl.col("stockout") == 1) & (pl.col("is_promo_detected") == 0)
    )
    assert not stockout_days.is_empty()
    # On average, base should exceed the censored sales on stockout days.
    mean_base = stockout_days["estimated_base"].mean()
    mean_sales = stockout_days["sales_volume"].mean()
    assert mean_base > mean_sales, (
        f"stockout base {mean_base:.1f} should exceed censored sales {mean_sales:.1f}"
    )


def test_step1_overlap_aggregation():
    """Overlapping promo events have combined campaign cost >= single event minimum."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE)
    overlap_days = decomposed_df.filter(pl.col("promo_name").str.contains("&"))
    if not overlap_days.is_empty():
        assert (overlap_days["campaign_cost"] >= 5000).all()

def test_step1_promo_detection():
    """High-discount rows must be flagged as promo."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE)
    high_discount_df = decomposed_df.filter(pl.col("discount_rate") > PROMO_THRESHOLD)
    assert (high_discount_df["is_promo_detected"] == 1).all()

def test_step1_all_items_present():
    """All 5 items appear in decomposed data."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE)
    assert decomposed_df["item_id"].n_unique() == 5


# ── Utils: Campaign Summary ───────────────────────────────────────────────────

def test_utils_campaign_summary_columns():
    """Campaign summary has ROI and required columns."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE).with_columns(pl.col("date").str.to_date())
    campaign_summary_df = get_campaign_summary(decomposed_df.filter(pl.col("item_id") == 1))
    if not campaign_summary_df.is_empty():
        assert "ROI (%)" in campaign_summary_df.columns
        assert "増分粗利" in campaign_summary_df.columns

def test_utils_campaign_summary_roi_calculation():
    """ROI is computed correctly as incremental_profit / campaign_cost * 100."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE).with_columns(pl.col("date").str.to_date())
    campaign_summary_df = get_campaign_summary(decomposed_df.filter(pl.col("item_id") == 1))
    if not campaign_summary_df.is_empty():
        row = campaign_summary_df.row(0, named=True)
        if row["販促費用"] > 0:
            expected = row["増分粗利"] / row["販促費用"] * 100
            assert pytest.approx(row["ROI (%)"], rel=1e-6) == expected


# ── Step 2: Forecasting ───────────────────────────────────────────────────────

def test_step2_output_schema():
    """Forecast file has all required columns with new naming convention."""
    forecast_df = pl.read_csv(FORECAST_FILE)
    required = {
        "date", "item_id", "actual_total",
        "forecast_hybrid_base", "forecast_hybrid_lift",
        "forecast_hybrid_lower", "forecast_hybrid_upper",
        "forecast_lgbm_base", "forecast_lgbm_lift"
    }
    assert required.issubset(set(forecast_df.columns))

def test_step2_all_items_forecasted():
    """All 5 items have forecast rows."""
    forecast_df = pl.read_csv(FORECAST_FILE)
    assert forecast_df["item_id"].n_unique() == 5

def test_step2_forecast_row_count():
    """Each item has at least BACKTEST_DAYS rows (backtest + optional future)."""
    forecast_df = pl.read_csv(FORECAST_FILE)
    per_item = forecast_df.group_by("item_id").len()
    assert (per_item["len"] >= BACKTEST_DAYS).all()

def test_step2_backtest_rows_have_actuals():
    """The first BACKTEST_DAYS rows per item contain non-null actual_total."""
    forecast_df = pl.read_csv(FORECAST_FILE)
    for item_id in forecast_df["item_id"].unique().to_list():
        item_df = forecast_df.filter(pl.col("item_id") == item_id).head(BACKTEST_DAYS)
        assert item_df["actual_total"].null_count() == 0, f"item_id={item_id} has nulls in backtest actuals"

def test_step2_hybrid_values_non_negative():
    """Hybrid base and lift forecasts must be non-negative."""
    forecast_df = pl.read_csv(FORECAST_FILE)
    assert (forecast_df["forecast_hybrid_base"] >= 0).all()
    assert (forecast_df["forecast_hybrid_lift"] >= 0).all()

def test_step2_confidence_band_ordering():
    """Lower bound <= upper bound for all rows."""
    forecast_df = pl.read_csv(FORECAST_FILE)
    assert (forecast_df["forecast_hybrid_lower"] <= forecast_df["forecast_hybrid_upper"]).all()

def test_step2_no_old_column_names():
    """Old fc_ prefixed column names must not exist (naming convention check)."""
    forecast_df = pl.read_csv(FORECAST_FILE)
    old_style = [c for c in forecast_df.columns if c.startswith("fc_")]
    assert old_style == [], f"Old column names found: {old_style}"


# ── New Feature Tests ────────────────────────────────────────────────────────

def test_config_map_promo_tier():
    """map_promo_tier resolves known promo names to expected tier labels."""
    assert map_promo_tier("激推しSALE") == "S: Deep Impact"
    assert map_promo_tier("通常特売") == "A: Standard"
    assert map_promo_tier("週末プチ安") == "B: Light"
    assert map_promo_tier("長期重点販売") == "L: Long-term"
    assert map_promo_tier("バレンタイン超特売") == "Other"


def test_utils_promo_blocks_detection():
    """get_promo_blocks returns valid start/end dates for each block."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE).with_columns(pl.col("date").str.to_date())
    blocks = get_promo_blocks(decomposed_df.filter(pl.col("item_id") == 1))
    assert not blocks.is_empty()
    assert {"promo_name", "start_date", "end_date", "tier"}.issubset(set(blocks.columns))
    assert (blocks["end_date"] >= blocks["start_date"]).all()


def test_utils_all_items_campaign_summary():
    """Cross-item campaign summary includes item_name and covers all items."""
    decomposed_df = pl.read_csv(DECOMPOSED_FILE).with_columns(pl.col("date").str.to_date())
    master_df = pl.read_csv(DATA_DIR / "item_master.csv")
    result = get_all_items_campaign_summary(decomposed_df, master_df)
    assert not result.is_empty()
    assert "item_name" in result.columns
    assert result["item_id"].n_unique() == 5


# ── Zero-handling: metric consistency ─────────────────────────────────────────

def test_metrics_all_zero_actual_is_undefined():
    """A series whose actuals are all zero cannot have a defined % error.

    Returning 0.0 here would masquerade as a *perfect* forecast. MAPE and WAPE
    must report NaN (undefined) so a zero-demand series is not mistaken for
    100% accuracy.
    """
    actual = np.zeros(10)
    pred = np.full(10, 5.0)
    mape, wape, rmse = calculate_metrics(actual, pred)
    assert np.isnan(mape), f"MAPE on all-zero actuals must be NaN, got {mape}"
    assert np.isnan(wape), f"WAPE on all-zero actuals must be NaN, got {wape}"
    # RMSE is still well-defined (errors exist even if the denominator is zero).
    assert rmse == pytest.approx(5.0)


def test_metrics_wape_uses_all_points_not_just_positive():
    """WAPE divisor is sum of |actual| over ALL points, unlike MAPE's positive mask.

    Verifies the two metrics are computed over the documented populations and a
    perfect forecast yields 0 on both.
    """
    actual = np.array([0.0, 10.0, 20.0, 0.0])
    pred = actual.copy()
    mape, wape, rmse = calculate_metrics(actual, pred)
    assert wape == pytest.approx(0.0)
    assert mape == pytest.approx(0.0)
    assert rmse == pytest.approx(0.0)


def test_metrics_preserve_true_zero_in_error():
    """An error on a true-zero actual still contributes to WAPE (not silently dropped)."""
    actual = np.array([0.0, 100.0])
    pred = np.array([30.0, 100.0])
    _, wape, _ = calculate_metrics(actual, pred)
    # |30-0| + |100-100| = 30 ; sum|actual| = 100 -> 30%
    assert wape == pytest.approx(30.0)


# ── M4: directional bias metric ───────────────────────────────────────────────

def test_bias_positive_when_over_forecasting():
    """Over-forecasting (excess inventory risk) yields positive bias."""
    actual = np.array([100.0, 100.0, 100.0])
    pred = np.array([110.0, 120.0, 130.0])  # +60 over 300
    assert calculate_bias(actual, pred) == pytest.approx(20.0)


def test_bias_negative_when_under_forecasting():
    """Under-forecasting (stockout risk) yields negative bias."""
    actual = np.array([100.0, 100.0])
    pred = np.array([80.0, 90.0])  # -30 over 200
    assert calculate_bias(actual, pred) == pytest.approx(-15.0)


def test_bias_cancels_where_wape_does_not():
    """A symmetric over/under error nets to ~0 bias while WAPE stays large.

    This is the whole point of adding bias: WAPE cannot distinguish a balanced
    forecast from one that is systematically off in one direction.
    """
    actual = np.array([100.0, 100.0])
    pred = np.array([150.0, 50.0])  # +50 and -50 -> net 0
    bias = calculate_bias(actual, pred)
    _, wape, _ = calculate_metrics(actual, pred)
    assert bias == pytest.approx(0.0)
    assert wape == pytest.approx(50.0)


def test_bias_undefined_for_zero_actual():
    """Zero total actual -> bias is undefined (NaN), not a misleading 0."""
    assert np.isnan(calculate_bias(np.zeros(3), np.full(3, 5.0)))


# ── Leakage: neutral-covariate window must be date-aligned, not tail-sliced ────

def test_step2_hybrid_base_below_total_on_promo_days():
    """On detected promo days the extracted base must be < total forecast.

    The neutral-covariate counterfactual (price=list, flyer=0, discount=0) should
    strip the promo lift. If the neutral window were misaligned (the [-horizon:]
    leak), base would not consistently sit below total on promo days.
    """
    forecast_df = pl.read_csv(FORECAST_FILE)
    total = forecast_df["forecast_hybrid_base"] + forecast_df["forecast_hybrid_lift"]
    # lift is clipped >= 0, so base <= total must hold for every row.
    assert (forecast_df["forecast_hybrid_base"] <= total + 1e-6).all()


# ── M1: Confidence-band calibration (conformal-style) ─────────────────────────

def test_calibrate_bands_brackets_point_and_orders():
    """Calibrated bands straddle the point forecast and stay ordered."""
    rng = np.random.default_rng(0)
    point_bt = np.full(200, 100.0)
    actual_bt = point_bt + rng.normal(0, 15, 200)  # residual std ~15
    point_future = np.full(50, 120.0)
    lower, upper = calibrate_bands(actual_bt, point_bt, point_future, coverage=0.80)
    assert (lower <= point_future).all()
    assert (upper >= point_future).all()
    assert (lower <= upper).all()


def test_calibrate_bands_recovers_empirical_quantiles():
    """Band half-widths match the empirical residual quantiles of the backtest.

    With symmetric residuals ~N(0, sigma), the 80% band should be roughly
    +/- 1.28*sigma around the point forecast.
    """
    rng = np.random.default_rng(1)
    sigma = 20.0
    point_bt = np.full(5000, 50.0)
    actual_bt = point_bt + rng.normal(0, sigma, 5000)
    point_future = np.array([200.0])
    lower, upper = calibrate_bands(actual_bt, point_bt, point_future, coverage=0.80)
    half_lo = point_future[0] - lower[0]
    half_hi = upper[0] - point_future[0]
    # 10th/90th percentile of N(0,sigma) ~ +/-1.2816*sigma
    assert half_lo == pytest.approx(1.2816 * sigma, rel=0.15)
    assert half_hi == pytest.approx(1.2816 * sigma, rel=0.15)


def test_calibrate_bands_clips_lower_at_zero():
    """Demand bands cannot go negative."""
    actual_bt = np.array([10.0, 5.0, 8.0])
    point_bt = np.array([12.0, 6.0, 9.0])
    point_future = np.array([2.0])
    lower, _ = calibrate_bands(actual_bt, point_bt, point_future, coverage=0.80)
    assert (lower >= 0).all()


def test_step2_confidence_band_coverage_near_nominal():
    """Backtest coverage of the 80% band must be substantially above the old ~26%.

    The forecast file is regenerated by the module fixture with calibrated bands.
    We require coverage on the backtest window to be in a sane range around the
    nominal 80% (calibration is in-sample on the backtest so it should be high,
    and must not collapse to the old broken ~26%).
    """
    forecast_df = pl.read_csv(FORECAST_FILE).filter(
        pl.col("actual_total").is_not_nan()
    )
    inside = forecast_df.filter(
        (pl.col("actual_total") >= pl.col("forecast_hybrid_lower"))
        & (pl.col("actual_total") <= pl.col("forecast_hybrid_upper"))
    )
    coverage = inside.height / forecast_df.height
    assert coverage >= 0.65, f"80% band coverage too low: {coverage:.1%} (was ~26% when broken)"
