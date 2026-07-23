"""
Step 5: Taipy Strategic Dashboard.
100% Polars logic with Taipy GUI and Core.
"""
import logging
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import taipy as tp
from taipy.gui import Gui, State, notify

# 1. FORCE PROJECT ROOT & HOT-RELOAD
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))

from libs.chart_builder import create_simulator_impact_chart
from libs.config import COL_DATE, COL_ITEM_ID, COL_SALES, FUTURE_DAYS
from libs.data_utils import load_data, to_time_series
from libs.models import add_temporal_features, get_tuned_sim_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# INITIAL DATA LOADING
# ------------------------------------------------------------------------------
try:
    master_df, decomposed_df, forecast_df = load_data()
    today_date = decomposed_df.filter(pl.col(COL_SALES).is_not_null())[COL_DATE].max()
    item_names = master_df["item_name"].to_list()
    # Use first item as default
    default_item_name = item_names[0]
except Exception as e:
    logger.error(f"Failed to load data: {e}")
    sys.exit(1)

# ------------------------------------------------------------------------------
# 1. CORE LOGIC (SCM Simulation)
# ------------------------------------------------------------------------------

def simulate_promo_impact(item_name: str, sim_price: int, sim_flyer: bool) -> tuple[pd.DataFrame, float, float]:
    """
    Executes the LightGBM simulator model and calculates incremental profit.
    Returns: DataFrame for plotting, Incremental Qty, Incremental Profit.
    """
    logger.info(f"Running simulation for {item_name} at price {sim_price}, flyer={sim_flyer}")
    # Get item master data
    selected_item_id = master_df.filter(pl.col("item_name") == item_name)["item_id"][0]
    item_master_df = master_df.filter(pl.col(COL_ITEM_ID) == selected_item_id)
    list_price = float(item_master_df["list_price"][0])
    unit_cost = float(item_master_df["unit_cost"][0])

    # Load the trained model
    simulator_model, lift_series, training_df = get_tuned_sim_model(selected_item_id, decomposed_df)

    sim_start_date, sim_end_date = today_date + timedelta(days=1), today_date + timedelta(days=FUTURE_DAYS)
    sim_dates = pl.date_range(sim_start_date, sim_end_date, interval="1d", eager=True)

    simulation_discount_rate = (list_price - sim_price) / list_price

    simulation_covariate_df = add_temporal_features(pl.DataFrame({
        COL_DATE: sim_dates,
        "actual_price": [float(sim_price)]*FUTURE_DAYS,
        "flyer": [1 if sim_flyer else 0]*FUTURE_DAYS,
        "discount_rate": [simulation_discount_rate]*FUTURE_DAYS
    }))

    cov_cols = ["actual_price", "flyer", "discount_rate", "day_of_week", "month", "year", "time_idx"]
    schema = training_df.select(cov_cols).schema
    simulation_covariate_df = simulation_covariate_df.cast(schema)

    full_covariate_df = pl.concat([
        training_df.select(cov_cols + [COL_DATE]),
        simulation_covariate_df.select(cov_cols + [COL_DATE])
    ])
    full_covariate_series = to_time_series(full_covariate_df, COL_DATE, cov_cols)

    # Predict lift
    simulation_forecast = simulator_model.predict(FUTURE_DAYS, series=lift_series, future_covariates=full_covariate_series, num_samples=100)

    # Base demand
    item_forecast_df = forecast_df.filter(pl.col(COL_ITEM_ID) == selected_item_id)
    base_demand = item_forecast_df["forecast_hybrid_base"].tail(FUTURE_DAYS).to_numpy()

    promo_lift = simulation_forecast.quantile(0.5).values().flatten().clip(min=0)
    total_demand = base_demand + promo_lift

    incremental_profit = ((sim_price - unit_cost) * np.sum(total_demand)) - ((list_price - unit_cost) * np.sum(base_demand))
    incremental_qty = float(np.sum(promo_lift))

    # Package for Taipy Plotly chart
    plot_df = pd.DataFrame({
        "Date": sim_dates.to_numpy(),
        "Base Demand": base_demand,
        "Total Demand": total_demand,
        "Promo Lift": promo_lift,
        "Lower Band": total_demand * 0.9,
        "Upper Band": total_demand * 1.1
    })

    return plot_df, incremental_qty, float(incremental_profit)

# ------------------------------------------------------------------------------
# 2. TAIPY CORE CONFIGURATION (DAG & Scenarios)
# ------------------------------------------------------------------------------

# Input Nodes
item_name_cfg = tp.Config.configure_data_node(id="item_name", default_data=default_item_name)
sim_price_cfg = tp.Config.configure_data_node(id="sim_price", default_data=150)
sim_flyer_cfg = tp.Config.configure_data_node(id="sim_flyer", default_data=True)

# Output Nodes
sim_plot_df_cfg = tp.Config.configure_data_node(id="sim_plot_df")
sim_inc_qty_cfg = tp.Config.configure_data_node(id="sim_inc_qty")
sim_inc_profit_cfg = tp.Config.configure_data_node(id="sim_inc_profit")

# Task Configuration
simulate_task_cfg = tp.Config.configure_task(
    id="simulate_promo_task",
    function=simulate_promo_impact,
    input=[item_name_cfg, sim_price_cfg, sim_flyer_cfg],
    output=[sim_plot_df_cfg, sim_inc_qty_cfg, sim_inc_profit_cfg],
    skippable=True
)

# Scenario Configuration
scenario_cfg = tp.Config.configure_scenario(
    id="promo_simulation_scenario",
    task_configs=[simulate_task_cfg]
)

# ------------------------------------------------------------------------------
# 3. TAIPY GUI (The Visual Dashboard)
# ------------------------------------------------------------------------------

# UI State Variables
selected_scenario = None
item_input = default_item_name
price_input = 150
flyer_input = True
chart_fig = None
inc_qty = 0.0
inc_profit = 0.0
y_max = 500.0

def build_chart(plot_df: pd.DataFrame, current_y_max: float):
    if plot_df.empty:
        return None
    # Re-use our chart builder
    fig = create_simulator_impact_chart(
        dates=plot_df["Date"].values,
        baseline_vol=plot_df["Base Demand"].values,
        plan_base=plot_df["Base Demand"].values,
        plan_lift=plot_df["Promo Lift"].values,
        lower=plot_df["Lower Band"].values,
        upper=plot_df["Upper Band"].values,
        title=f"戦略インパクト予測 ({FUTURE_DAYS}日間)",
        y_max=current_y_max
    )
    return fig

# Page Layout
page_md = """
# 🎯 販促戦略シミュレーター (Taipy Edition)

<|layout|columns=1 3|
<|
### 🎛️ シナリオコントロール
**シナリオを選択:**
<|{selected_scenario}|scenario_selector|>

**対象商品:**
<|{item_input}|selector|lov={item_names}|on_change=update_scenario_params|>

**想定販売価格:**
<|{price_input}|slider|min=50|max=300|step=5|on_change=update_scenario_params|>

**チラシ配布あり:**
<|{flyer_input}|toggle|on_change=update_scenario_params|>

<br/><br/>
**予測増分数量:** <|{inc_qty}|format=+,.0f|> 個<br/>
**推定増分粗利:** ¥<|{inc_profit}|format=+,.0f|>
|>

<|
### 📈 戦略インパクト予測
<|{chart_fig}|chart|figure={chart_fig}|height=600px|>
|>
|>
"""

# Callbacks
def update_scenario_params(state: State):
    """Triggered when user changes inputs."""
    if state.selected_scenario:
        # 1. Update Taipy Core Inputs
        state.selected_scenario.item_name.write(state.item_input)
        state.selected_scenario.sim_price.write(state.price_input)
        state.selected_scenario.sim_flyer.write(state.flyer_input)

        notify(state, "info", "シミュレーション実行中...")

        # 2. Run the DAG
        tp.submit(state.selected_scenario)

        # 3. Read Outputs
        plot_df = state.selected_scenario.sim_plot_df.read()

        # Keep Y axis stable based on base demand max * 1.5
        max_base = plot_df["Base Demand"].max()
        state.y_max = float(max_base) * 1.5

        state.chart_fig = build_chart(plot_df, state.y_max)
        state.inc_qty = float(state.selected_scenario.sim_inc_qty.read())
        state.inc_profit = float(state.selected_scenario.sim_inc_profit.read())

        notify(state, "success", "シミュレーションが更新されました！")
    else:
        notify(state, "warning", "最初にシナリオを選択（作成）してください。")

# ------------------------------------------------------------------------------
# 4. ENTRY POINT
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # 1. Start Taipy Core
    tp.Core().run()

    # 2. Create default scenario
    scenarios = tp.get_scenarios()
    if not scenarios:
        default_scenario = tp.create_scenario(scenario_cfg, name="ベースライン販促")
    else:
        default_scenario = scenarios[0]

    default_scenario.item_name.write(default_item_name)
    default_scenario.sim_price.write(150)
    default_scenario.sim_flyer.write(True)
    tp.submit(default_scenario)

    # Generate initial plot
    initial_plot_df = default_scenario.sim_plot_df.read()
    chart_fig = build_chart(initial_plot_df, 500.0)
    inc_qty = float(default_scenario.sim_inc_qty.read())
    inc_profit = float(default_scenario.sim_inc_profit.read())

    # 3. Start GUI
    Gui(page=page_md).run(title="Taipy SCM Simulator", port=8502, debug=False)
