"""
Centralized configuration and business rules.
Single source of truth for paths, column names, and parameters.
"""
from datetime import datetime
from pathlib import Path
from typing import Final

# --- Project Structure ---
BASE_DIR: Final[Path] = Path(__file__).parent.parent
DATA_DIR: Final[Path] = BASE_DIR / "promo_poc_data"
REPORT_DIR: Final[Path] = BASE_DIR / "reports"

# --- Data Files ---
MASTER_FILE: Final[Path] = DATA_DIR / "item_master.csv"
ACTUALS_FILE: Final[Path] = DATA_DIR / "sales_actuals.csv"
CALENDAR_FILE: Final[Path] = DATA_DIR / "promo_calendar.csv"
TRUTH_FILE: Final[Path] = DATA_DIR / "ground_truth.csv"
DECOMPOSED_FILE: Final[Path] = DATA_DIR / "decomposed_data.csv"
FORECAST_FILE: Final[Path] = DATA_DIR / "forecast_results.csv"
REPORT_FILE: Final[Path] = REPORT_DIR / "promo_analysis_report.html"

# --- Business Logic Parameters ---
START_DATE: Final[datetime] = datetime(2021, 1, 1)
END_DATE: Final[datetime] = datetime(2026, 6, 30)
BACKTEST_DAYS: Final[int] = 180
FUTURE_DAYS: Final[int] = 180
HISTORY_DAYS: Final[int] = 1095  # 3 Years
PROMO_THRESHOLD: Final[float] = 0.10  # 10% discount to detect as promo
DEFAULT_OPTUNA_TRIALS: Final[int] = 5

# Forward-buying (pantry loading): a fraction of promo-day lift is pulled forward
# from future demand, so base demand dips for a few days AFTER a promo ends.
PULLFORWARD_FRAC: Final[float] = 0.35   # share of promo lift that is borrowed from the future
PULLFORWARD_DAYS: Final[int] = 7        # rebound window (days the dip is spread over)

# Stockout: on rare days inventory runs out, so observed sales are censored below
# true demand. These days are flagged and excluded from baseline estimation.
STOCKOUT_RATE: Final[float] = 0.03      # share of days that hit a stockout
STOCKOUT_CENSOR: Final[float] = 0.55    # sales are capped at this fraction of demand on a stockout day
COL_STOCKOUT: Final[str] = "stockout"

# Promo wear-out (saturation): repeating promos too often fatigues the response,
# so each promo day's lift decays with how many promo days occurred recently.
SATURATION_WINDOW: Final[int] = 60      # look-back window (days) for recent promo intensity
SATURATION_STRENGTH: Final[float] = 0.5  # max fraction of lift lost when promo intensity is saturated

# --- Column Name Definitions ---
COL_DATE: Final[str] = "date"
COL_ITEM_ID: Final[str] = "item_id"
COL_SALES: Final[str] = "sales_volume"
COL_PRICE_ACT: Final[str] = "actual_price"
COL_PRICE_LIST: Final[str] = "list_price"
COL_UNIT_COST: Final[str] = "unit_cost"
COL_CAMP_COST: Final[str] = "campaign_cost"
COL_PROMO_NAME: Final[str] = "promo_name"
COL_FLYER: Final[str] = "flyer"
COL_DISC_RATE: Final[str] = "discount_rate"

# --- SCM Master Data ---
ITEMS: Final[dict[int, str]] = {
    1: "ビール", 2: "チョコ", 3: "ポテトチップス", 4: "グミ", 5: "オレンジジュース"
}

WEEKDAY_MULTIPLIER_MAP: Final[dict[int, float]] = {0:1.0, 1:1.0, 2:1.0, 3:1.0, 4:1.1, 5:1.2, 6:1.3}

# --- Promo Tier Mapping ---
TIER_MAP: Final[dict[str, str]] = {
    "激推し": "S: Deep Impact",
    "通常": "A: Standard",
    "プチ安": "B: Light",
    "長期": "L: Long-term",
}

TIER_COLORS: Final[dict[str, str]] = {
    "S: Deep Impact": "#e74c3c",
    "A: Standard": "#f39c12",
    "B: Light": "#2ecc71",
    "L: Long-term": "#3498db",
    "Other": "#95a5a6",
}

def map_promo_tier(name: str) -> str:
    """Canonical promo-name to tier-label mapping."""
    for keyword, label in TIER_MAP.items():
        if keyword in name:
            return label
    return "Other"
