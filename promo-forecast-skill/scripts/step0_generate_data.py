"""
Step 0: Strategic Data Generation.
Produces ultra-realistic POS and promo data using multi-tiered rankings.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.absolute()
if str(ROOT_DIR) not in sys.path: sys.path.insert(0, str(ROOT_DIR))

import logging
import random
from datetime import datetime, timedelta

import numpy as np
import polars as pl
from libs.config import (
    ACTUALS_FILE,
    CALENDAR_FILE,
    COL_DATE,
    COL_ITEM_ID,
    COL_STOCKOUT,
    DATA_DIR,
    END_DATE,
    MASTER_FILE,
    PULLFORWARD_DAYS,
    PULLFORWARD_FRAC,
    SATURATION_STRENGTH,
    SATURATION_WINDOW,
    START_DATE,
    STOCKOUT_CENSOR,
    STOCKOUT_RATE,
    TRUTH_FILE,
    WEEKDAY_MULTIPLIER_MAP,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def generate_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    start_dt = START_DATE.date()
    end_dt = END_DATE.date()
    num_days = (end_dt - start_dt).days + 1
    dates = [start_dt + timedelta(days=x) for x in range(num_days)]

    master_data = [
        {"item_id": 1, "item_name": "ビール", "list_price": 220, "unit_cost": 160},
        {"item_id": 2, "item_name": "チョコ", "list_price": 150, "unit_cost": 80},
        {"item_id": 3, "item_name": "ポテトチップス", "list_price": 180, "unit_cost": 90},
        {"item_id": 4, "item_name": "グミ", "list_price": 120, "unit_cost": 60},
        {"item_id": 5, "item_name": "オレンジジュース", "list_price": 200, "unit_cost": 110},
    ]
    pl.DataFrame(master_data).write_csv(MASTER_FILE)

    actuals_all, calendar_all, truth_all = [], [], []

    for item in master_data:
        item_id = item["item_id"]
        logger.info(f"Generating high-signal data for: {item['item_name']}")

        base_volume = random.randint(100, 300)
        trend = np.linspace(1.0, 1.6, num_days)
        seasonal = 1.0 + 0.25 * np.sin(2 * np.pi * np.array([d.timetuple().tm_yday for d in dates]) / 365)
        weekday_mult = np.array([WEEKDAY_MULTIPLIER_MAP[d.weekday()] for d in dates])
        base_demands = base_volume * trend * seasonal * weekday_mult

        promo_events = []
        current_date = dates[0]

        while current_date < dates[-1]:
            if item_id == 2 and current_date.month == 2 and current_date.day < 14:
                promo_events.append({"item_id": item_id, "promo_name": "バレンタイン超特売", "start_date": datetime(current_date.year, 2, 1).date(), "end_date": datetime(current_date.year, 2, 14).date(), "campaign_cost": 50000, "discount_rate_target": 0.35, "flyer": 1})
                current_date = datetime(current_date.year, 2, 15).date(); continue

            current_date += timedelta(days=random.randint(15, 45))
            if current_date >= dates[-1]: break

            tier_roll = random.random()
            if tier_roll > 0.85: rank, disc, dur, cost = "長期重点販売", 0.08, random.randint(30, 45), 40000
            elif tier_roll > 0.65: rank, disc, dur, cost = "激推しSALE", random.uniform(0.25, 0.35), random.randint(3, 7), 30000
            elif tier_roll > 0.30: rank, disc, dur, cost = "通常特売", random.uniform(0.12, 0.18), random.randint(7, 14), 15000
            else: rank, disc, dur, cost = "週末プチ安", random.uniform(0.05, 0.10), random.randint(2, 3), 4000

            event_end_date = min(current_date + timedelta(days=dur), dates[-1])
            promo_events.append({"item_id": item_id, "promo_name": rank, "start_date": current_date, "end_date": event_end_date, "campaign_cost": cost, "discount_rate_target": disc, "flyer": 1 if rank in ["長期重点販売", "激推しSALE"] else 0})
            current_date = event_end_date + timedelta(days=10)

        actual_prices = [float(item["list_price"])] * num_days
        flyers = [0.0] * num_days
        promo_names = ["通常販売"] * num_days

        for p in promo_events:
            for i, d in enumerate(dates):
                if p["start_date"] <= d <= p["end_date"]:
                    actual_prices[i] = float(item["list_price"]) * (1.0 - p["discount_rate_target"])
                    flyers[i] = float(p["flyer"])
                    promo_names[i] = p["promo_name"]

        df = pl.DataFrame({
            COL_DATE: dates,
            COL_ITEM_ID: item_id,
            "base_demand": base_demands,
            "actual_price": actual_prices,
            "flyer": flyers,
            "promo_name": promo_names
        })

        df = df.with_columns([
            ((item["list_price"] - pl.col("actual_price")) / item["list_price"]).alias("discount_rate")
        ])

        df = df.with_columns([
            (pl.col("base_demand") * (np.exp(3.8 * pl.col("discount_rate")) - 1.0)).alias("true_lift")
        ])

        df = df.with_columns([
            pl.when(pl.col("flyer") == 1.0).then(pl.col("true_lift") * 1.4).otherwise(pl.col("true_lift")).alias("true_lift")
        ])

        # Promo wear-out (saturation): the more promo days occurred in the recent
        # SATURATION_WINDOW, the more fatigued the response. We scale each day's
        # lift by (1 - strength * recent_promo_intensity), so frequent promos earn
        # diminishing returns rather than a constant per-event lift.
        is_promo_day = (df["discount_rate"] > 0.0).cast(pl.Float64)
        recent_intensity = (
            is_promo_day.shift(1, fill_value=0.0)
            .rolling_sum(window_size=SATURATION_WINDOW, min_samples=1)
            / SATURATION_WINDOW
        )
        df = df.with_columns(recent_intensity.alias("promo_intensity")).with_columns(
            (pl.col("true_lift") * (1.0 - SATURATION_STRENGTH * pl.col("promo_intensity")))
            .clip(lower_bound=0.0).alias("true_lift")
        )

        # Forward-buying (pantry loading): a share of each promo day's lift is
        # borrowed from future demand. We spread that borrowed quantity evenly
        # over the PULLFORWARD_DAYS that FOLLOW the lift (rolling sum of prior
        # lift, divided by the window), then subtract it from base_demand so the
        # baseline dips after a promo. true_base records the post-dip baseline so
        # decomposition validation reflects the realistic demand path.
        pullforward = (
            df["true_lift"]
            .shift(1, fill_value=0.0)
            .rolling_sum(window_size=PULLFORWARD_DAYS, min_samples=1)
            * (PULLFORWARD_FRAC / PULLFORWARD_DAYS)
        )
        df = df.with_columns(pullforward.alias("pullforward")).with_columns(
            (pl.col("base_demand") - pl.col("pullforward")).clip(lower_bound=0.0).alias("base_demand")
        )

        noise = np.random.normal(1.0, 0.03, num_days)
        df = df.with_columns([
            ((pl.col("base_demand") + pl.col("true_lift")) * noise).clip(lower_bound=0.0).round(1).alias("sales_volume")
        ])

        # Stockout: on a few non-promo days inventory runs out, censoring observed
        # sales below true demand. We flag these days so Step 1 can exclude them
        # from baseline estimation (a censored observation must not pull the base
        # down). Promo days are spared to keep the lift signal clean.
        stockout_flags = (np.random.random(num_days) < STOCKOUT_RATE).astype(int)
        df = df.with_columns(pl.Series(COL_STOCKOUT, stockout_flags)).with_columns(
            pl.when((pl.col(COL_STOCKOUT) == 1) & (pl.col("flyer") == 0.0))
            .then((pl.col("sales_volume") * STOCKOUT_CENSOR).round(1))
            .otherwise(pl.col("sales_volume"))
            .alias("sales_volume")
        ).with_columns(
            # only the censored (non-promo) days keep the stockout flag
            pl.when((pl.col(COL_STOCKOUT) == 1) & (pl.col("flyer") == 0.0)).then(1).otherwise(0).alias(COL_STOCKOUT)
        )

        pos_end = datetime(2025, 12, 31).date()

        actuals_pl = df.filter(pl.col(COL_DATE) <= pos_end).select([
            pl.col(COL_DATE).cast(pl.Date),
            pl.col(COL_ITEM_ID),
            pl.col("sales_volume"),
            pl.col("actual_price"),
            pl.col(COL_STOCKOUT),
        ])
        actuals_all.append(actuals_pl)

        truth_pl = df.select([
            pl.col(COL_DATE).cast(pl.Date),
            pl.col(COL_ITEM_ID),
            pl.col("base_demand").alias("true_base"),
            pl.col("true_lift")
        ])
        truth_all.append(truth_pl)

        calendar_all.append(pl.DataFrame(promo_events))

    pl.concat(actuals_all).write_csv(ACTUALS_FILE)
    pl.concat(calendar_all).write_csv(CALENDAR_FILE)
    pl.concat(truth_all).write_csv(TRUTH_FILE)
    logger.info("Step 0 complete: High-signal synthetic data saved.")

if __name__ == "__main__": generate_data()
