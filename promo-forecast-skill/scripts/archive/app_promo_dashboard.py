"""
Interactive Streamlit Dashboard for Promotion Analysis and Hybrid Forecasting.
Provides visualization of demand decomposition, model comparison, and What-If simulation.
"""

import logging
from pathlib import Path
from typing import Final

import pandas as pd
import plotly.graph_objects as go
import polars as pl
import streamlit as st
from darts import TimeSeries
from darts.models import LightGBMModel, Prophet

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
DATA_DIR: Final[Path] = Path("promo_poc_data")
ITEM_MASTER_FILE: Final[Path] = DATA_DIR / "item_master.csv"
DECOMPOSED_DATA_FILE: Final[Path] = DATA_DIR / "decomposed_transactions.csv"

# Page config
st.set_page_config(page_title="特売需要分析ダッシュボード", layout="wide")


@st.cache_resource
def load_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Loads item master and decomposed transaction data.

    Returns:
        A tuple of (item_master, transactions) DataFrames.
    """
    if not ITEM_MASTER_FILE.exists() or not DECOMPOSED_DATA_FILE.exists():
        st.error(f"Required data files not found in {DATA_DIR}")
        st.stop()

    item_master = pl.read_csv(ITEM_MASTER_FILE)
    df = pl.read_csv(DECOMPOSED_DATA_FILE)
    df = df.with_columns(pl.col("date").str.to_datetime().dt.date())
    return item_master, df


@st.cache_resource
def get_predictions(
    _b_train: TimeSeries, _l_train: TimeSeries, _cov: TimeSeries, horizon: int = 30
) -> tuple[TimeSeries, TimeSeries, TimeSeries, TimeSeries]:
    """
    Generates forecasts for Base and Lift using Prophet and LightGBM.

    Args:
        _b_train: Base demand training series.
        _l_train: Lift demand training series.
        _cov: Future covariates (price, flyer).
        horizon: Forecasting horizon in days.

    Returns:
        A tuple of (Prophet_Base, Prophet_Lift, LGBM_Base, LGBM_Lift) TimeSeries.
    """
    logger.info(f"Running forecasts for horizon={horizon}")

    # Prophet Models
    m_p_b = Prophet()
    m_p_b.fit(_b_train)
    p_p_b = m_p_b.predict(horizon)

    m_p_l = Prophet()
    m_p_l.fit(_l_train, future_covariates=_cov)
    p_p_l = m_p_l.predict(horizon, future_covariates=_cov)

    # LightGBM Models
    m_l_b = LightGBMModel(lags=14, output_chunk_length=1)
    m_l_b.fit(_b_train)
    p_l_b = m_l_b.predict(horizon)

    m_l_l = LightGBMModel(lags=7, lags_future_covariates=(0, 1), output_chunk_length=1)
    m_l_l.fit(_l_train, future_covariates=_cov)
    p_l_l = m_l_l.predict(horizon, future_covariates=_cov)

    return p_p_b, p_p_l, p_l_b, p_l_l


def main() -> None:
    """Main function to render the Streamlit dashboard."""
    st.title("🍫 特売需要分析 & ハイブリッド予測ダッシュボード")
    st.markdown(
        """
    実績データを「定番（Base）」と「特売リフト（Lift）」に分解し、
    それぞれの特性に最適なモデル（Prophet/LightGBM）を検証します。
    """
    )

    # 1. Load Data
    item_master, df = load_data()

    # Sidebar: Item Selection
    st.sidebar.header("分析設定")
    item_names: list[str] = item_master["item_name"].to_list()
    selected_item_name: str = st.sidebar.selectbox("品目を選択", item_names)
    selected_item_id: int = item_master.filter(pl.col("item_name") == selected_item_name)[
        "item_id"
    ][0]

    item_df = df.filter(pl.col("item_id") == selected_item_id)

    # 2. Demand Decomposition Visualization
    st.header(f"📊 需要分解結果: {selected_item_name}")
    col1, col2 = st.columns([3, 1])

    with col1:
        fig_decomp = go.Figure()
        # Actual
        fig_decomp.add_trace(
            go.Scatter(
                x=item_df["date"],
                y=item_df["sales_volume"],
                name="実績(Total)",
                line={"color": "gray", "width": 1, "dash": "dot"},
            )
        )
        # Base (Estimated)
        fig_decomp.add_trace(
            go.Scatter(
                x=item_df["date"],
                y=item_df["estimated_base"],
                name="定番需要(Base)",
                fill="tozeroy",
                line={"color": "blue"},
            )
        )
        # Lift (Estimated)
        fig_decomp.add_trace(
            go.Scatter(
                x=item_df["date"],
                y=item_df["estimated_lift"],
                name="特売リフト(Lift)",
                line={"color": "red"},
            )
        )
        fig_decomp.update_layout(
            title="実績の需要分解 (Base vs Lift)",
            xaxis_title="日付",
            yaxis_title="数量",
            hovermode="x unified",
        )
        st.plotly_chart(fig_decomp, use_container_width=True)

    with col2:
        list_price: float = item_master.filter(pl.col("item_id") == selected_item_id)[
            "list_price"
        ][0]
        threshold: float = item_master.filter(pl.col("item_id") == selected_item_id)[
            "promo_discount_threshold"
        ][0]
        st.metric("定価", f"¥{list_price}")
        st.metric("特売判定閾値", f"{threshold * 100}%")
        st.write("---")
        avg_base: float = item_df["estimated_base"].mean()
        avg_lift: float = (
            item_df.filter(pl.col("is_promo_detected") == 1)["estimated_lift"].mean()
            or 0.0
        )
        st.write(f"平均定番需要: {avg_base:.1f}")
        st.write(f"平均特売リフト: {avg_lift:.1f}")

    # 3. Model Comparison
    st.header("🔬 モデル特性の比較 (Prophet vs LightGBM)")
    st.info("最後の1ヶ月をテストデータとして予測を実行します。")

    # Data splitting
    train_end = item_df["date"].max() - pd.Timedelta(days=30)
    item_pd = item_df.to_pandas()

    base_ts = TimeSeries.from_dataframe(item_pd, "date", "estimated_base", freq="D")
    lift_ts = TimeSeries.from_dataframe(item_pd, "date", "estimated_lift", freq="D")
    cov_ts = TimeSeries.from_dataframe(item_pd, "date", ["actual_price", "flyer"], freq="D")

    base_train, base_val = base_ts.split_before(pd.Timestamp(train_end))
    lift_train, lift_val = lift_ts.split_before(pd.Timestamp(train_end))

    p_p_b, p_p_l, p_l_b, p_l_l = get_predictions(base_train, lift_train, cov_ts)

    tab1, tab2 = st.tabs(["🏠 定番需要(Base)の予測比較", "🚀 特売需要(Lift)の予測比較"])

    with tab1:
        fig_base = go.Figure()
        fig_base.add_trace(
            go.Scatter(
                x=base_val.time_index,
                y=base_val.values().flatten(),
                name="分解実績(Base)",
                line={"color": "black", "width": 2},
            )
        )
        fig_base.add_trace(
            go.Scatter(
                x=p_p_b.time_index,
                y=p_p_b.values().flatten(),
                name="Prophet予測",
                line={"color": "blue"},
            )
        )
        fig_base.add_trace(
            go.Scatter(
                x=p_l_b.time_index,
                y=p_l_b.values().flatten(),
                name="LightGBM予測",
                line={"color": "green"},
            )
        )
        fig_base.update_layout(title="定番需要に対するモデル比較")
        st.plotly_chart(fig_base, use_container_width=True)

    with tab2:
        fig_lift = go.Figure()
        fig_lift.add_trace(
            go.Scatter(
                x=lift_val.time_index,
                y=lift_val.values().flatten(),
                name="分解実績(Lift)",
                line={"color": "black", "width": 2},
            )
        )
        fig_lift.add_trace(
            go.Scatter(
                x=p_p_l.time_index,
                y=p_p_l.values().flatten(),
                name="Prophet予測",
                line={"color": "blue"},
            )
        )
        fig_lift.add_trace(
            go.Scatter(
                x=p_l_l.time_index,
                y=p_l_l.values().flatten(),
                name="LightGBM予測",
                line={"color": "red"},
            )
        )
        fig_lift.update_layout(title="特売需要に対するモデル比較")
        st.plotly_chart(fig_lift, use_container_width=True)

    # 4. Hybrid Forecasting Demo
    st.header("💡 ハイブリッド予測 (Best of Both Worlds)")
    hybrid_pred = p_p_b + p_l_l
    actual_total = item_df.filter(pl.col("date") > train_end)["sales_volume"].to_numpy()

    fig_hybrid = go.Figure()
    fig_hybrid.add_trace(
        go.Scatter(
            x=p_p_b.time_index, y=actual_total, name="実績(Total)", line={"color": "black", "width": 2}
        )
    )
    fig_hybrid.add_trace(
        go.Scatter(
            x=p_p_b.time_index,
            y=p_p_b.values().flatten(),
            name="予測: 定番(Prophet)",
            fill="tozeroy",
            line={"color": "blue"},
        )
    )
    fig_hybrid.add_trace(
        go.Scatter(
            x=p_l_l.time_index,
            y=p_l_l.values().flatten(),
            name="予測: 特売(LightGBM)",
            line={"color": "red"},
        )
    )
    fig_hybrid.add_trace(
        go.Scatter(
            x=hybrid_pred.time_index,
            y=hybrid_pred.values().flatten(),
            name="最終予測(Hybrid)",
            line={"color": "orange", "width": 3},
        )
    )
    fig_hybrid.update_layout(title="ハイブリッドモデルによる需要予測", hovermode="x unified")
    st.plotly_chart(fig_hybrid, use_container_width=True)

    # 5. What-If Simulation
    st.header("🎯 What-If シミュレーション (来週の施策検討)")
    col_sim1, col_sim2 = st.columns([1, 2])

    with col_sim1:
        st.subheader("🛠️ 施策条件の設定")
        sim_actual_price = st.slider(
            "販売単価 (Actual Price)",
            min_value=int(list_price * 0.5),
            max_value=int(list_price),
            value=int(list_price * 0.8),
            step=5,
        )
        sim_flyer = st.checkbox("チラシを打つ (Flyer)", value=True)

        discount_rate = (list_price - sim_actual_price) / list_price * 100
        st.write(f"値引き率: **{discount_rate:.1f}%**")

        if (list_price - sim_actual_price) / list_price > threshold:
            st.success("✅ 特売判定（リフトが発生します）")
        else:
            st.warning("⚠️ 定番価格帯（リフトは限定的です）")

    with col_sim2:
        # Create simulation covariates
        sim_base = p_p_b.slice_n_points(7)
        sim_cov_df = pd.DataFrame(
            {
                "date": sim_base.time_index,
                "actual_price": [float(sim_actual_price)] * 7,
                "flyer": [1.0 if sim_flyer else 0.0] * 7,
            }
        )
        sim_cov_ts = TimeSeries.from_dataframe(
            sim_cov_df, "date", ["actual_price", "flyer"], freq="D"
        )

        # Rerun LightGBM Lift prediction for simulation
        m_l_l_sim = LightGBMModel(lags=7, lags_future_covariates=(0, 1), output_chunk_length=1)
        m_l_l_sim.fit(lift_train, future_covariates=cov_ts)
        sim_lift = m_l_l_sim.predict(7, future_covariates=sim_cov_ts)

        sim_total = sim_base + sim_lift

        fig_sim = go.Figure()
        fig_sim.add_trace(
            go.Bar(
                x=sim_base.time_index,
                y=sim_base.values().flatten(),
                name="定番予測(Prophet)",
                marker_color="blue",
                opacity=0.6,
            )
        )
        fig_sim.add_trace(
            go.Bar(
                x=sim_lift.time_index,
                y=sim_lift.values().flatten(),
                name="特売リフト(LightGBM)",
                marker_color="red",
                opacity=0.8,
            )
        )
        fig_sim.add_trace(
            go.Scatter(
                x=sim_total.time_index,
                y=sim_total.values().flatten(),
                name="合計予測数量",
                line={"color": "orange", "width": 3},
            )
        )
        fig_sim.update_layout(
            title=f"来週の需要シミュレーション: {selected_item_name}",
            barmode="stack",
            yaxis_range=[0, df.filter(pl.col("item_id") == selected_item_id)["sales_volume"].max() * 1.2],
        )
        st.plotly_chart(fig_sim, use_container_width=True)


if __name__ == "__main__":
    main()
