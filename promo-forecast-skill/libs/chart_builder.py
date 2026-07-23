"""
Professional SCM Visualization Library (Final Integrated Version).
Unified plotting interfaces for history, validation, and strategy.
"""
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import polars as pl

from .config import TIER_COLORS, map_promo_tier


def _date_to_epoch_ms(date_val: Any) -> int:
    """Converts date-like object to epoch milliseconds for Plotly compatibility."""
    return int(pd.Timestamp(date_val).value // 10**6)

def create_decomposition_chart(
    df: pl.DataFrame | pd.DataFrame,
    title: str,
    promo_blocks: pl.DataFrame | None = None,
    aggregation: str = "daily",
) -> go.Figure:
    """Standard history breakdown (Area) with optional promo annotations and aggregation."""
    if isinstance(df, pd.DataFrame):
        plot_df = pl.from_pandas(df)
    else:
        plot_df = df

    # Aggregation: truncate, group-sum, then plot
    if aggregation != "daily":
        interval = "1mo" if aggregation == "monthly" else "1w"
        plot_df = (
            plot_df.with_columns(pl.col("date").dt.truncate(interval).alias("date"))
            .group_by("date").agg([
                pl.col("estimated_base").sum(),
                pl.col("estimated_lift").sum(),
            ]).sort("date")
        )
    else:
        plot_df = plot_df.sort("date")

    dates = plot_df["date"].to_list()
    base = plot_df["estimated_base"].to_list()
    lift = plot_df["estimated_lift"].to_list()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=base, name="定番需要", stackgroup="one", line={"width": 0, "color": "#3498db"}, opacity=0.7, fillcolor="#3498db"))
    fig.add_trace(go.Scatter(x=dates, y=lift, name="特売リフト", stackgroup="one", line={"width": 0, "color": "#e74c3c"}, opacity=0.8, fillcolor="#e74c3c"))

    # Promo event annotations (only on daily view to avoid clutter)
    if promo_blocks is not None and not promo_blocks.is_empty() and aggregation == "daily":
        for row in promo_blocks.iter_rows(named=True):
            tier = row["tier"]
            color = TIER_COLORS.get(tier, "#95a5a6")
            fig.add_vrect(
                x0=row["start_date"], x1=row["end_date"],
                fillcolor=color, opacity=0.12, line_width=0, layer="below",
            )
            fig.add_annotation(
                x=row["start_date"], y=1.0, yref="paper",
                text=f"{tier[:1]} -{row['avg_discount_rate']*100:.0f}%",
                showarrow=False, font={"size": 9, "color": color},
                xanchor="left", yanchor="top",
            )

    fig.update_layout(title=title, height=500, hovermode="x unified", legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1})
    return fig

def create_strategic_breakdown_chart(
    history_df: pl.DataFrame | pd.DataFrame, backtest_df: pl.DataFrame | pd.DataFrame, future_df: pl.DataFrame | pd.DataFrame,
    actual_total: np.ndarray, full_dates: np.ndarray,
    title: str, name_prefix: str, color_base: str, today_date: Any | None = None
) -> go.Figure:
    """Complex 360-day view with historical context."""
    fig = go.Figure()
    # 1. 3-Year context
    fig.add_trace(go.Scatter(x=history_df["date"], y=history_df["sales_volume"], name="過去実績(POS)", line={"color": "rgba(150,150,150,0.3)", "width": 1}))
    # 2. Backtest stack
    fig.add_trace(go.Scatter(x=backtest_df["date"], y=backtest_df["base"], name=f"{name_prefix}定番(検証)", stackgroup="bt", line={"width": 0, "color": color_base}, opacity=0.6))
    fig.add_trace(go.Scatter(x=backtest_df["date"], y=backtest_df["lift"], name=f"{name_prefix}特売(検証)", stackgroup="bt", line={"width": 0, "color": "#e74c3c"}, opacity=0.8))
    # 3. Future stack
    if len(future_df) > 0:
        fig.add_trace(go.Scatter(x=future_df["date"], y=future_df["base"], name="将来定番", stackgroup="ft", line={"width": 1, "color": color_base, "dash": "dot"}))
        fig.add_trace(go.Scatter(x=future_df["date"], y=future_df["lift"], name="将来リフト", stackgroup="ft", line={"width": 1, "color": "#e74c3c", "dash": "dot"}))
    # 4. Actual overlay
    fig.add_trace(go.Scatter(x=full_dates, y=actual_total, name="実績(検証期間)", line={"color": "black", "width": 2, "dash": "dash"}))
    if today_date: fig.add_vline(x=_date_to_epoch_ms(today_date), line_dash="dash", line_color="red", annotation_text="本日")
    fig.update_layout(title=title, height=550, hovermode="x unified", legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1})
    return fig

def create_forecast_with_bands_chart(
    dates: np.ndarray, actual: np.ndarray, hybrid_base: np.ndarray, hybrid_lift: np.ndarray, hybrid_lower: np.ndarray, hybrid_upper: np.ndarray, title: str, today_date: Any | None = None
) -> go.Figure:
    """Probabilistic view with confidence bands."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=actual, name="実績(POS)", line={"color": "black", "width": 2}))
    # Bands
    fig.add_trace(go.Scatter(x=dates.tolist() + dates.tolist()[::-1], y=hybrid_upper.tolist() + hybrid_lower.tolist()[::-1], fill='toself', fillcolor='rgba(255, 165, 0, 0.15)', line={"color": 'rgba(0,0,0,0)'}, name="80%信頼区間", hoverinfo="skip"))
    # Point stacks
    fig.add_trace(go.Scatter(x=dates, y=hybrid_base, name="定番(Hybrid)", stackgroup="fc", line={"width": 0, "color": "#3498db"}, opacity=0.7))
    fig.add_trace(go.Scatter(x=dates, y=hybrid_lift, name="リフト(Hybrid)", stackgroup="fc", line={"width": 0, "color": "#e74c3c"}, opacity=0.9))
    if today_date: fig.add_vline(x=_date_to_epoch_ms(today_date), line_dash="dash", line_color="red", annotation_text="本日")
    fig.update_layout(title=title, height=550, hovermode="x unified", legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1})
    return fig

def create_forecast_comparison_chart(dates: np.ndarray, actual: np.ndarray, hybrid: np.ndarray, prophet: np.ndarray, lgbm: np.ndarray, title: str, today_date: Any | None = None) -> go.Figure:
    """Comparison chart for multiple model totals."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=actual, name="実績", line={"color": "black", "width": 2.5}))
    fig.add_trace(go.Scatter(x=dates, y=hybrid, name="Hybrid(提案)", line={"color": "orange", "width": 4}))
    fig.add_trace(go.Scatter(x=dates, y=prophet, name="Prophet Only", line={"dash": "dot", "color": "blue"}))
    fig.add_trace(go.Scatter(x=dates, y=lgbm, name="LGBM Only", line={"dash": "dot", "color": "green"}))
    if today_date: fig.add_vline(x=_date_to_epoch_ms(today_date), line_dash="dash", line_color="red", annotation_text="本日")
    fig.update_layout(title=title, height=500, hovermode="x unified", legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1})
    return fig

def create_roi_scatter_chart(df: pl.DataFrame | pd.DataFrame) -> go.Figure:
    """Scatter analysis for campaign ROI vs Cost."""
    if isinstance(df, pd.DataFrame):
        df = pl.from_pandas(df)

    plot_df = df.with_columns([
        pl.col("販促名").map_elements(map_promo_tier, return_dtype=pl.String).alias("ランク"),
        pl.col("増分粗利").clip(lower_bound=0).alias("size")
    ])

    try:
        fig = px.scatter(plot_df, x="販促費用", y="ROI (%)", size="size", color="ランク", hover_name="販促名", hover_data={"size": False, "増分粗利": ":,.0f"}, title="販促費用 vs ROI", color_discrete_map=TIER_COLORS)
    except Exception:
        fig = px.scatter(plot_df.to_pandas(), x="販促費用", y="ROI (%)", size="size", color="ランク", hover_name="販促名", hover_data={"size": False, "増分粗利": ":,.0f"}, title="販促費用 vs ROI", color_discrete_map=TIER_COLORS)

    fig.add_hline(y=0, line_dash="dash", line_color="black")
    return fig

def create_tier_performance_chart(df: pl.DataFrame | pd.DataFrame) -> go.Figure:
    """Rank-wise performance benchmarking."""
    fig = go.Figure()

    # Extract columns whether it's pandas or polars
    ranks = df["ランク"]
    gross_margin = df["総・増分粗利"]
    avg_roi = df["平均ROI"]

    if isinstance(df, pl.DataFrame):
        text_labels = df.select(pl.col("平均ROI").map_elements(lambda x: f"{x:.1f}%", return_dtype=pl.String))["平均ROI"].to_list()
    else:
        text_labels = df["平均ROI"].apply(lambda x: f"{x:.1f}%").tolist()

    fig.add_trace(go.Bar(x=ranks, y=gross_margin, name="総・増分粗利", marker_color="#34495e", yaxis="y1"))
    fig.add_trace(go.Scatter(x=ranks, y=avg_roi, name="平均ROI", mode="lines+markers+text", text=text_labels, line={"color": "#e67e22", "width": 3}, yaxis="y2"))
    fig.update_layout(title="施策ランク別の累計貢献度", yaxis={"title": "増分粗利(円)"}, yaxis2={"title": "ROI(%)", "side": "right", "overlaying": "y", "showgrid": False}, height=400, legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1})
    return fig

def create_simulator_impact_chart(dates: np.ndarray, baseline_vol: np.ndarray, plan_base: np.ndarray, plan_lift: np.ndarray, lower: np.ndarray, upper: np.ndarray, title: str, y_max: float | None = None) -> go.Figure:
    """Ultimate simulator impact visualization.

    y_max: 縦軸の上限を固定したい場合に渡す（省略時は自動スケール）。
           品目選択時に baseline_vol の最大値 * 2.0 を渡すと、
           スライダー操作でスケールが変わらない固定軸になる。
    """
    if y_max is None:
        y_max = float(np.nanmax(np.concatenate([upper, plan_base + plan_lift]))) * 1.1
        y_max = max(y_max, 1.0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates.tolist() + dates.tolist()[::-1], y=upper.tolist() + lower.tolist()[::-1], fill='toself', fillcolor='rgba(255, 165, 0, 0.1)', line={"color": 'rgba(0,0,0,0)'}, name="リスク幅", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=dates, y=baseline_vol, name="Baseline (販促なし)", fill='tozeroy', fillcolor='rgba(200, 200, 200, 0.3)', line={"color": 'grey', "width": 1, "dash": 'dot'}))
    fig.add_trace(go.Scatter(x=dates, y=plan_base, name="定番需要(実力値)", stackgroup="p", mode='lines', line={"width": 0, "color": "#3498db"}, fillcolor="#3498db"))
    fig.add_trace(go.Scatter(x=dates, y=plan_lift, name="施策効果(増分)", stackgroup="p", mode='lines', line={"width": 0, "color": "#e74c3c"}, fillcolor="#e74c3c"))
    fig.update_layout(
        title=title, height=550, hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        yaxis={"range": [0, y_max], "fixedrange": True}
    )
    return fig


def create_portfolio_scatter_chart(df: pl.DataFrame | pd.DataFrame) -> go.Figure:
    """Cross-item campaign scatter: x=cost, y=ROI, color=item_name, size=incremental profit."""
    if isinstance(df, pl.DataFrame):
        plot_df = df.with_columns(pl.col("増分粗利").clip(lower_bound=0).alias("size"))
    else:
        plot_df = pl.from_pandas(df).with_columns(pl.col("増分粗利").clip(lower_bound=0).alias("size"))

    try:
        fig = px.scatter(
            plot_df, x="販促費用", y="ROI (%)", size="size",
            color="item_name", hover_name="販促名",
            hover_data={"size": False, "増分粗利": ":,.0f"},
            title="全品目 販促費用 vs ROI",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
    except Exception:
        fig = px.scatter(
            plot_df.to_pandas(), x="販促費用", y="ROI (%)", size="size",
            color="item_name", hover_name="販促名",
            hover_data={"size": False, "増分粗利": ":,.0f"},
            title="全品目 販促費用 vs ROI",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
    fig.add_hline(y=0, line_dash="dash", line_color="black", annotation_text="損益分岐")
    fig.update_layout(height=500, hovermode="x unified", legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1})
    return fig


def create_item_contribution_chart(df: pl.DataFrame | pd.DataFrame) -> go.Figure:
    """Stacked bar: incremental profit by item and tier."""
    if isinstance(df, pd.DataFrame):
        df = pl.from_pandas(df)

    agg = (
        df.with_columns(
            pl.col("販促名").map_elements(map_promo_tier, return_dtype=pl.String).alias("ランク")
        )
        .group_by(["item_name", "ランク"]).agg(pl.col("増分粗利").sum())
        .sort("item_name")
    )

    fig = go.Figure()
    for tier in ["S: Deep Impact", "A: Standard", "B: Light", "L: Long-term", "Other"]:
        tier_data = agg.filter(pl.col("ランク") == tier)
        if tier_data.is_empty():
            continue
        fig.add_trace(go.Bar(
            x=tier_data["item_name"], y=tier_data["増分粗利"],
            name=tier, marker_color=TIER_COLORS.get(tier, "#95a5a6"),
        ))
    fig.update_layout(
        barmode="stack", title="品目別 増分粗利の施策ランク構成",
        yaxis_title="増分粗利 (円)", height=500,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return fig


def create_elasticity_curve_chart(df: pl.DataFrame | pd.DataFrame, optimal_price: float) -> go.Figure:
    """Price elasticity curve with dual Y-axes: profit (left) and quantity (right)."""
    if isinstance(df, pl.DataFrame):
        prices = df["price"].to_list()
        profit = df["incremental_profit"].to_list()
        quantity = df["total_quantity"].to_list()
    else:
        prices = df["price"].tolist()
        profit = df["incremental_profit"].tolist()
        quantity = df["total_quantity"].tolist()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=prices, y=profit, name="増分粗利 (円)",
        mode="lines+markers", line={"color": "#e74c3c", "width": 3},
        marker={"size": 8}, yaxis="y1",
    ))
    fig.add_trace(go.Scatter(
        x=prices, y=quantity, name="総需要数量",
        mode="lines+markers", line={"color": "#3498db", "width": 2, "dash": "dot"},
        marker={"size": 6}, yaxis="y2",
    ))
    fig.add_vline(
        x=optimal_price, line_dash="dash", line_color="#2ecc71", line_width=2,
        annotation_text=f"最適価格: {optimal_price:.0f}円",
        annotation_font_color="#2ecc71",
    )
    fig.add_hline(y=0, line_dash="dot", line_color="grey", line_width=1)
    fig.update_layout(
        title="価格弾力性カーブ (180日間シミュレーション)",
        xaxis_title="販売価格 (円)", height=500,
        yaxis={"title": {"text": "増分粗利 (円)", "font": {"color": "#e74c3c"}}},
        yaxis2={"title": {"text": "総需要数量", "font": {"color": "#3498db"}}, "side": "right", "overlaying": "y", "showgrid": False},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return fig


def create_calendar_gantt_chart(df: pl.DataFrame | pd.DataFrame, item_names: dict[int, str]) -> go.Figure:
    """Gantt-style chart showing promo events across items and time."""
    if isinstance(df, pl.DataFrame):
        pdf = df.to_pandas()
    else:
        pdf = df.copy()

    if pdf.empty:
        fig = go.Figure()
        fig.update_layout(title="販促カレンダー (データなし)", height=400)
        return fig

    # Map item_id to name if not already present
    if "item_name" not in pdf.columns and "item_id" in pdf.columns:
        pdf["item_name"] = pdf["item_id"].map(item_names)

    # Ensure datetime for px.timeline
    pdf["start_date"] = pd.to_datetime(pdf["start_date"])
    pdf["end_date"] = pd.to_datetime(pdf["end_date"])

    fig = px.timeline(
        pdf, x_start="start_date", x_end="end_date",
        y="item_name", color="promo_name",
        title="販促カレンダー",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        height=max(300, len(pdf["item_name"].unique()) * 80),
        yaxis_title="品目",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return fig
