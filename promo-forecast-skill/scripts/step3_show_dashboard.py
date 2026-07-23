"""
Step 3: Strategic Dashboard.
100% Polars logic, Hot-Reload enabled, High-impact visualization.
8 tabs: 需要分解 / LGBM分析 / モデル対決 / 販促ROI / ポートフォリオ / シミュレーター / 弾力性 / カレンダー入力
"""
import importlib
import sys
from datetime import timedelta
from pathlib import Path

# 1. FORCE PROJECT ROOT & HOT-RELOAD
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))

import libs.chart_builder
import libs.config
import libs.data_utils
import libs.models

importlib.reload(libs.config); importlib.reload(libs.data_utils); importlib.reload(libs.chart_builder); importlib.reload(libs.models)

import logging

import numpy as np
import pandas as pd
import polars as pl
import streamlit as st

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from darts import TimeSeries
from darts.models import LightGBMModel
from libs.chart_builder import (
    create_calendar_gantt_chart,
    create_decomposition_chart,
    create_elasticity_curve_chart,
    create_forecast_with_bands_chart,
    create_item_contribution_chart,
    create_portfolio_scatter_chart,
    create_roi_scatter_chart,
    create_simulator_impact_chart,
    create_strategic_breakdown_chart,
    create_tier_performance_chart,
)
from libs.config import (
    BACKTEST_DAYS,
    CALENDAR_FILE,
    COL_DATE,
    COL_ITEM_ID,
    COL_SALES,
    FUTURE_DAYS,
    HISTORY_DAYS,
    ITEMS,
    map_promo_tier,
)
from libs.data_utils import (
    calculate_bias,
    calculate_metrics,
    get_all_items_campaign_summary,
    get_campaign_summary,
    get_promo_blocks,
    get_tier_efficiency_summary,
    load_data,
    sweep_price_elasticity,
    to_time_series,
)
from libs.models import add_temporal_features
from libs.models import get_tuned_sim_model as _get_tuned_sim_model

st.set_page_config(page_title="定番特売分離需要予測＆販促ROI分析", layout="wide")


@st.cache_resource
def get_tuned_sim_model(item_id: int, _decomposed_df: pl.DataFrame) -> tuple[LightGBMModel, TimeSeries, pl.DataFrame]:
    return _get_tuned_sim_model(item_id, _decomposed_df)


@st.cache_resource
def compute_elasticity_curve(
    item_id: int,
    _decomposed_df: pl.DataFrame,
    _forecast_df: pl.DataFrame,
    _today_date: object,
    unit_cost: float,
    list_price: float,
    flyer: bool,
) -> pl.DataFrame:
    """Cached price elasticity sweep."""
    # Reuse the cached sim model instead of re-fitting LightGBM here.
    model, lift_series, training_df = get_tuned_sim_model(item_id, _decomposed_df)
    item_fc = _forecast_df.filter(pl.col(COL_ITEM_ID) == item_id)
    base_demand = item_fc["forecast_hybrid_base"].tail(FUTURE_DAYS).to_numpy()
    return sweep_price_elasticity(
        model, lift_series, training_df, base_demand,
        _today_date, unit_cost, list_price, FUTURE_DAYS,
        step=10, flyer=flyer,
    )


# ---------------------------------------------------------------------------
# Default promo rank configs for calendar input form
# ---------------------------------------------------------------------------
RANK_DEFAULTS: dict[str, dict[str, object]] = {
    "激推しSALE": {"cost": 30000, "flyer": 1},
    "通常特売": {"cost": 15000, "flyer": 0},
    "週末プチ安": {"cost": 4000, "flyer": 0},
    "長期重点販売": {"cost": 40000, "flyer": 1},
}


def _render_guide_tab(unit_cost: float, list_price: float) -> None:
    """利用法・各タブの解説・モデルロジック・指標の読み方をまとめた解説タブ。"""
    st.header("📖 利用法・解説")
    st.markdown(
        "このダッシュボードは、消費財（CPG）の販売実績を **定番需要（Base）** と "
        "**特売リフト（Lift）** に分離し、需要予測・販促ROI・価格最適化を支援します。"
        "サイドバーで品目を切り替えると、全タブがその品目に追従します。"
    )

    st.subheader("クイックスタート")
    st.markdown(
        "1. サイドバーで **品目を選択**\n"
        "2. **需要分解** タブで定番/リフトの構造を確認\n"
        "3. **Hybrid予測** タブで将来需要と80%信頼区間を確認\n"
        "4. **販促ROI分析 / ポートフォリオ** で施策の費用対効果を評価\n"
        "5. **戦略シミュレーター / 価格弾力性** で価格・チラシを試算\n"
        "6. **販促カレンダー入力** で計画を編集 → 予測を再実行"
    )

    st.subheader("各タブの役割")
    st.table({
        "タブ": [
            "需要分解", "LGBM 360日展望", "Hybrid予測", "販促ROI分析",
            "品目横断ポートフォリオ", "戦略シミュレーター", "価格弾力性カーブ", "販促カレンダー入力",
        ],
        "用途": [
            "定番(青)/特売(赤)の分解と販促イベントの可視化",
            "LGBM単体の360日展望（過去検証＋未来予測）",
            "Hybridモデルの予測＋キャリブレーション済み80%信頼区間",
            "品目内キャンペーンの費用対効果（ROI）",
            "全品目横断の費用vsROI・ランク別貢献・ROIマトリックス",
            "価格・チラシ変更による増分粗利のリアルタイム試算",
            "10円刻みの価格スイープで粗利最大の最適価格を算出",
            "カレンダー編集・新規プラン追加→予測パイプライン再実行",
        ],
    })

    st.subheader("モデルのしくみ")
    st.markdown(
        """
**需要分解（Step 1）**
- 非特売日の売上だけから **曜日別の移動平均** で定番需要を推定（特売日はマスクして汚染を防止）
- リフト = 売上 − 定番。**特売日のみ** に計上し、非特売日のリフトは 0（ノイズの偽リフトを排除）

**Hybrid予測（Step 2）**
- 価格・チラシ・値引き率を共変量に LightGBM を学習 → 総需要を予測
- 「定価・チラシなし・値引き0」の **中立条件で再予測** して定番需要を抽出
- リフト = 総予測 − 定番予測（≥0）

**信頼区間（キャリブレーション済み）**
- バックテスト期間の **実際の予測誤差（残差）** の経験分位点から80%区間を構成（split-conformal方式）
- モデル自身の楽観的な分散ではなく「実際にどれだけ外したか」で幅を決める
"""
    )

    st.subheader("精度指標の読み方")
    st.table({
        "指標": ["MAPE", "WAPE", "RMSE", "バイアス"],
        "意味": [
            "正の実績に対する平均絶対誤差率（%）",
            "総量ベースの絶対誤差率（%）。ゼロが多い系列に頑健",
            "二乗平均平方根誤差（実数量スケール）",
            "誤差の方向。+ = 過大予測（過剰在庫リスク） / − = 過小予測（欠品リスク）",
        ],
    })
    st.info(
        "**バイアスが重要な理由**: WAPE/MAPE は誤差の大きさだけを測り、方向を打ち消します。"
        "同じWAPEでも、常に多めに外す予測（過剰在庫）と少なめに外す予測（欠品）は経営インパクトが正反対です。"
        "バイアスがその方向を示します（0に近いほど偏りのない予測）。"
    )

    st.subheader("増分粗利の計算式（シミュレーター）")
    st.markdown(
        f"""
```
値引き率   = (定価 - 販売価格) / 定価
総需要     = 定番需要(Hybrid) + 販促リフト(LightGBM)
増分粗利   = (販売価格 - 原価) × 総需要  −  (定価 - 原価) × 定番需要
```
選択中の品目: 原価 {int(unit_cost)}円 / 定価 {int(list_price)}円
（注: チラシ印刷費等のキャンペーンコストは含みません。ROI分析タブと併せて判断してください）
"""
    )

    with st.expander("既知の限界・注意点", expanded=False):
        st.markdown(
            "- **信頼区間は期間一律のキャリブレーション**: 特売日は誤差が大きいため、本来は条件付きの幅が理想。\n"
            "- **将来カバレッジ**: 区間はバックテスト残差で較正するため、表示の80%は将来期間でやや低めに出ることがある。\n"
            "- **フォワードバイイング/カニバリゼーション**: 買いだめ反動・品目間競合は現状未考慮（BACKLOG参照）。\n"
            "- 詳細は `docs/REQUIREMENTS.md`（仕様）・`docs/walkthrough.md`（利用法）・`docs/BACKLOG.md`（残作業）を参照。"
        )


def show_dashboard() -> None:
    st.title("定番特売分離需要予測 & 販促ROI分析")
    if st.sidebar.button("キャッシュクリア"):
        st.cache_data.clear(); st.cache_resource.clear(); st.rerun()

    try:
        master_df, decomposed_df, forecast_df = load_data()
    except Exception as e:
        st.error(f"Prediction data not ready: {e}"); st.stop()

    today_date = decomposed_df.filter(pl.col(COL_SALES).is_not_null())[COL_DATE].max()

    # --- Cross-item data (computed BEFORE item filter, for portfolio tab) ---
    all_items_campaign_df = get_all_items_campaign_summary(
        decomposed_df.filter(pl.col(COL_SALES).is_not_null()), master_df,
    )

    # --- Per-item selection ---
    selected_item_name = st.sidebar.selectbox("品目を選択", master_df["item_name"].to_list())
    selected_item_id = master_df.filter(pl.col("item_name") == selected_item_name)["item_id"][0]
    item_master_df = master_df.filter(pl.col(COL_ITEM_ID) == selected_item_id)
    list_price, unit_cost = item_master_df["list_price"][0], item_master_df["unit_cost"][0]

    item_decomposed_df = decomposed_df.filter(pl.col(COL_ITEM_ID) == selected_item_id)
    history_df = item_decomposed_df.filter(
        (pl.col(COL_DATE) <= today_date) & (pl.col(COL_DATE) >= today_date - pl.duration(days=HISTORY_DAYS))
    )
    item_forecast_df = forecast_df.filter(pl.col(COL_ITEM_ID) == selected_item_id)

    # Shared data for simulator + elasticity tabs
    base_demand_future = item_forecast_df["forecast_hybrid_base"].tail(FUTURE_DAYS).to_numpy()

    # ======================================================================
    # TABS
    # ======================================================================
    # The guide tab is unpacked separately so the existing tabs[0..7] indices
    # below stay untouched while the guide still renders first.
    guide_tab, *tabs = st.tabs([
        "📖 利用法・解説",
        "需要分解", "LGBM 360日展望", "Hybrid予測", "販促ROI分析",
        "品目横断ポートフォリオ", "戦略シミュレーター", "価格弾力性カーブ", "販促カレンダー入力",
    ])

    with guide_tab:
        _render_guide_tab(unit_cost, list_price)

    # ------------------------------------------------------------------
    # Tab 0: 需要分解 (Feature 1: annotations + aggregation)
    # ------------------------------------------------------------------
    with tabs[0]:
        st.markdown(
            "過去3年間の販売実績を**定番需要（青）**と**特売リフト（赤）**に分解した面グラフです。"
            "定番需要の上にリフトが積み上がり、合計が実際の販売数量に近似します。"
            "背景の色帯は販促実施期間で、ラベルはランク（S/A/B/L）と値引き率を示します。"
        )
        agg_mode = st.radio("集計単位", ["日次", "週次", "月次"], horizontal=True)
        agg_map = {"日次": "daily", "週次": "weekly", "月次": "monthly"}
        promo_blocks = get_promo_blocks(history_df)
        st.plotly_chart(
            create_decomposition_chart(
                history_df.to_pandas(), "過去の実績分解",
                promo_blocks=promo_blocks, aggregation=agg_map[agg_mode],
            ),
            use_container_width=True,
        )

    # ------------------------------------------------------------------
    # Tab 1: LGBM分析 (unchanged)
    # ------------------------------------------------------------------
    with tabs[1]:
        st.markdown(
            "LightGBM単体モデルによる**360日展望**です。"
            "過去180日の検証期間（バックテスト）で精度を評価し、未来180日の予測を定番/リフトに分解して表示します。"
            "灰色の線は過去3年間の実績コンテキスト、黒破線は検証期間の実績です。"
        )
        backtest_df = item_forecast_df.head(BACKTEST_DAYS)
        lgbm_total = (backtest_df["forecast_lgbm_base"] + backtest_df["forecast_lgbm_lift"]).to_numpy()
        lgbm_actual = backtest_df["actual_total"].to_numpy()
        mape, wape, rmse = calculate_metrics(lgbm_actual, lgbm_total)
        bias = calculate_bias(lgbm_actual, lgbm_total)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("検証 MAPE", f"{mape:.2f}%")
        c2.metric("検証 WAPE", f"{wape:.2f}%")
        c3.metric("検証 RMSE", f"{rmse:.2f}")
        c4.metric("検証 バイアス", f"{bias:+.1f}%", help="正=過大予測(過剰在庫リスク) / 負=過小予測(欠品リスク)")
        backtest_pandas_df = item_forecast_df.head(BACKTEST_DAYS).rename(
            {"forecast_lgbm_base": "base", "forecast_lgbm_lift": "lift"}
        ).to_pandas()
        future_pandas_df = item_forecast_df.tail(FUTURE_DAYS).rename(
            {"forecast_lgbm_base": "base", "forecast_lgbm_lift": "lift"}
        ).to_pandas()
        st.plotly_chart(
            create_strategic_breakdown_chart(
                history_df.to_pandas(), backtest_pandas_df, future_pandas_df,
                item_forecast_df["actual_total"].to_numpy(),
                item_forecast_df[COL_DATE].to_numpy(),
                "LGBM分析", "LGBM", "#2ecc71", today_date,
            ),
            use_container_width=True,
        )

    # ------------------------------------------------------------------
    # Tab 2: モデル対決 (unchanged)
    # ------------------------------------------------------------------
    with tabs[2]:
        st.markdown(
            "**Hybridモデル**（中立共変量カウンターファクチュアル方式）の予測結果です。"
            "単一のLightGBMで学習し、販促なしの中立条件で再予測することで定番需要を抽出します。"
            "オレンジの帯は**80%信頼区間**（10%/90%分位点）で、実績がこの範囲に収まる確率の目安です。"
        )
        st.subheader("Hybrid予測（Base + Lift）の精度")
        hybrid_total = (backtest_df["forecast_hybrid_base"] + backtest_df["forecast_hybrid_lift"]).to_numpy()
        hybrid_actual = backtest_df["actual_total"].to_numpy()
        hybrid_mape, hybrid_wape, hybrid_rmse = calculate_metrics(hybrid_actual, hybrid_total)
        hybrid_bias = calculate_bias(hybrid_actual, hybrid_total)
        hc1, hc2, hc3, hc4 = st.columns(4)
        hc1.metric("Hybrid 検証 MAPE", f"{hybrid_mape:.2f}%")
        hc2.metric("Hybrid 検証 WAPE", f"{hybrid_wape:.2f}%")
        hc3.metric("Hybrid 検証 RMSE", f"{hybrid_rmse:.2f}")
        hc4.metric("Hybrid 検証 バイアス", f"{hybrid_bias:+.1f}%", help="正=過大予測(過剰在庫リスク) / 負=過小予測(欠品リスク)")
        st.plotly_chart(
            create_forecast_with_bands_chart(
                item_forecast_df[COL_DATE].to_numpy(),
                item_forecast_df["actual_total"].to_numpy(),
                item_forecast_df["forecast_hybrid_base"].to_numpy(),
                item_forecast_df["forecast_hybrid_lift"].to_numpy(),
                item_forecast_df["forecast_hybrid_lower"].to_numpy(),
                item_forecast_df["forecast_hybrid_upper"].to_numpy(),
                "Hybrid予測の不確実性(360日展望)", today_date,
            ),
            use_container_width=True,
        )

    # ------------------------------------------------------------------
    # Tab 3: 販促ROI分析 (unchanged)
    # ------------------------------------------------------------------
    with tabs[3]:
        st.markdown(
            "選択品目の過去キャンペーンを個別に集計し、**費用対効果（ROI）**を分析します。"
            "左の散布図はキャンペーン費用とROIの関係（バブルサイズ=増分粗利）、"
            "右の棒グラフはランク別（S/A/B/L）の累計貢献度と平均ROIです。"
            "下の表で各キャンペーンの詳細数値を確認できます。"
        )
        campaign_summary_df = get_campaign_summary(
            item_decomposed_df.filter(pl.col(COL_SALES).is_not_null())
        )
        if not campaign_summary_df.is_empty():
            tier_summary_df = get_tier_efficiency_summary(campaign_summary_df)
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(create_roi_scatter_chart(campaign_summary_df.to_pandas()), use_container_width=True)
            with col2:
                st.plotly_chart(create_tier_performance_chart(tier_summary_df.to_pandas()), use_container_width=True)
            st.dataframe(
                campaign_summary_df.to_pandas().style.format({
                    "増分数量": "{:,.1f}", "増分粗利": "{:,.0f}",
                    "販促費用": "{:,.0f}", "ROI (%)": "{:.1f}%",
                }),
                use_container_width=True,
            )
        else:
            st.warning("販促実績なし")

    # ------------------------------------------------------------------
    # Tab 4: 品目横断ポートフォリオ (Feature 3)
    # ------------------------------------------------------------------
    with tabs[4]:
        st.header("品目横断ポートフォリオビュー")
        st.markdown(
            "全5品目のキャンペーン実績を**1つのビュー**で俯瞰します。"
            "左の散布図で品目ごとの費用対効果を比較し、右の積み上げ棒グラフでどのランクの施策が利益に貢献しているかを把握できます。"
            "下のマトリックスは品目xランク別の平均ROIで、**販促予算の配分判断**に活用してください。"
        )
        if all_items_campaign_df.is_empty():
            st.warning("販促実績なし")
        else:
            all_with_tier = all_items_campaign_df.with_columns(
                pl.col("販促名").map_elements(map_promo_tier, return_dtype=pl.String).alias("ランク")
            )
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(create_portfolio_scatter_chart(all_with_tier), use_container_width=True)
            with col2:
                st.plotly_chart(create_item_contribution_chart(all_with_tier), use_container_width=True)

            # Item x Tier ROI matrix
            st.subheader("品目 x ランク 平均ROI マトリックス")
            pivot = (
                all_with_tier.group_by(["item_name", "ランク"])
                .agg(pl.col("ROI (%)").mean())
                .pivot(on="ランク", index="item_name", values="ROI (%)")
                .fill_null(0)
            )
            # Format numeric columns as percentages
            numeric_cols = [c for c in pivot.columns if c != "item_name"]
            st.dataframe(
                pivot.to_pandas().style.format(
                    dict.fromkeys(numeric_cols, "{:.1f}%")
                ),
                use_container_width=True,
            )

    # ------------------------------------------------------------------
    # Tab 5: 戦略シミュレーター (unchanged logic, reads custom calendar)
    # ------------------------------------------------------------------
    with tabs[5]:
        st.header("販促戦略シミュレーター (向こう180日間)")
        st.markdown(
            "価格とチラシ配布を変更して**今後180日間の増分粗利**をリアルタイムに試算します。"
            "青=定番需要（変わらない）、赤=販促リフト（スライダーで変化）、オレンジ帯=リスク幅です。"
        )

        with st.expander("このシミュレーターの計算ロジック", expanded=False):
            st.markdown(f"""
**目的** -- 「この価格で販売し、チラシを配るとどれだけ売れて、いくら儲かるか」を180日分まとめて試算します。

---

#### Step 1 | 入力変数の設定

| 変数 | 内容 |
|------|------|
| 想定販売価格 | スライダーで設定。原価 ~ 定価（{int(unit_cost)}円 ~ {int(list_price)}円）の範囲で指定 |
| チラシ配布フラグ | ON=1 / OFF=0 として特徴量に渡す |
| 値引き率 | `(定価 - 販売価格) / 定価` で自動計算 |

---

#### Step 2 | 販促リフトの予測（LightGBM）

過去の販売実績から学習した **LightGBMモデル** に特徴量を入力し、今後180日分の **販促リフト（増分数量）** を予測します。

モデルは **分位点回帰**（10%/50%/90%）で学習しており、50%点（中央値）をリフトの予測値として使用します。

---

#### Step 3 | 総需要の合成

```
総需要 = 定番需要（Hybrid LGBM） + 販促リフト（LightGBM）
```

---

#### Step 4 | 増分粗利の計算

```
増分粗利 = (販売価格 - 原価) x 総需要  -  (定価 - 原価) x 定番需要
```

> **注意**: キャンペーンコスト（チラシ印刷費等）は含みません。ROI分析タブと組み合わせてご判断ください。
""")

        # Pre-populate from custom calendar if available
        default_price = int(list_price * 0.8)
        default_flyer = True
        custom_cal = st.session_state.get("custom_calendar")
        if custom_cal is not None and not custom_cal.is_empty():
            item_events = custom_cal.filter(pl.col("item_id") == selected_item_id)
            if not item_events.is_empty():
                first = item_events.row(0, named=True)
                default_price = int(first.get("target_price", default_price))
                default_flyer = bool(first.get("flyer", 1))
                st.info("カレンダー入力タブの計画値を反映中")

        col_s1, col_s2 = st.columns([1, 2])
        with col_s1:
            sim_price = st.slider(
                "想定販売価格", min_value=int(unit_cost), max_value=int(list_price),
                value=default_price, step=5,
            )
            sim_flyer = st.checkbox("チラシ配布あり", value=default_flyer)
            discount_pct = (list_price - sim_price) / list_price * 100
            st.caption(f"値引き率: **{discount_pct:.1f}%**  原価: {int(unit_cost)}円  定価: {int(list_price)}円")
            placeholder = st.empty()
        with col_s2:
            simulator_model, lift_series, training_df = get_tuned_sim_model(selected_item_id, decomposed_df)
            sim_start_date = today_date + timedelta(days=1)
            sim_end_date = today_date + timedelta(days=FUTURE_DAYS)
            sim_dates = pl.date_range(sim_start_date, sim_end_date, interval="1d", eager=True)
            simulation_discount_rate = (list_price - sim_price) / list_price
            simulation_covariate_df = add_temporal_features(pl.DataFrame({
                COL_DATE: sim_dates,
                "actual_price": [float(sim_price)] * FUTURE_DAYS,
                "flyer": [1 if sim_flyer else 0] * FUTURE_DAYS,
                "discount_rate": [simulation_discount_rate] * FUTURE_DAYS,
            }))
            cov_cols = ["actual_price", "flyer", "discount_rate", "day_of_week", "month", "year", "time_idx"]
            schema = training_df.select(cov_cols).schema
            simulation_covariate_df = simulation_covariate_df.cast(schema)
            full_covariate_df = pl.concat([
                training_df.select(cov_cols + [COL_DATE]),
                simulation_covariate_df.select(cov_cols + [COL_DATE]),
            ])
            full_covariate_series = to_time_series(full_covariate_df, COL_DATE, cov_cols)
            simulation_forecast = simulator_model.predict(
                FUTURE_DAYS, series=lift_series,
                future_covariates=full_covariate_series, num_samples=100,
            )
            promo_lift = simulation_forecast.quantile(0.5).values().flatten().clip(min=0)
            total_demand = base_demand_future + promo_lift
            # Risk band from the model's actual lift quantiles (10%/90%), not a
            # flat +/-10%. Base demand is held fixed; only the promo lift carries
            # the simulated uncertainty.
            lift_low = simulation_forecast.quantile(0.1).values().flatten().clip(min=0)
            lift_high = simulation_forecast.quantile(0.9).values().flatten().clip(min=0)
            band_lower = base_demand_future + lift_low
            band_upper = base_demand_future + lift_high
            incremental_profit = (
                (sim_price - unit_cost) * np.sum(total_demand)
                - (list_price - unit_cost) * np.sum(base_demand_future)
            )
            with placeholder.container():
                st.metric("予測増分数量", f"+{np.sum(promo_lift):,.0f} 個")
                st.metric("推定増分粗利", f"{incremental_profit:,.0f} 円")
            sim_y_max = float(base_demand_future.max()) * 1.5
            st.plotly_chart(
                create_simulator_impact_chart(
                    sim_dates.to_numpy(), base_demand_future, base_demand_future,
                    promo_lift, band_lower, band_upper,
                    "戦略インパクト予測", y_max=sim_y_max,
                ),
                use_container_width=True,
            )

    # ------------------------------------------------------------------
    # Tab 6: 価格弾力性カーブ (Feature 2)
    # ------------------------------------------------------------------
    with tabs[6]:
        st.header("価格弾力性カーブ (180日間シミュレーション)")
        st.markdown(
            "原価から定価まで**10円刻み**で価格を変えた場合の180日間の増分粗利と総需要をプロットします。"
            "赤線（左軸）が増分粗利、青線（右軸）が総需要数量です。"
            "緑の縦線が**粗利を最大化する最適価格**を示します。チラシの有無で曲線が大きく変わります。"
        )
        flyer_toggle = st.checkbox("チラシ配布あり", value=True, key="elasticity_flyer")

        with st.spinner("価格弾力性を計算中..."):
            elasticity_df = compute_elasticity_curve(
                selected_item_id, decomposed_df, forecast_df,
                today_date, float(unit_cost), float(list_price), flyer_toggle,
            )

        optimal_row = elasticity_df.sort("incremental_profit", descending=True).row(0, named=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("最適価格", f"{optimal_row['price']:,.0f} 円")
        c2.metric("最大増分粗利", f"{optimal_row['incremental_profit']:,.0f} 円")
        c3.metric("値引き率", f"{optimal_row['discount_rate'] * 100:.1f}%")

        st.plotly_chart(
            create_elasticity_curve_chart(elasticity_df, optimal_row["price"]),
            use_container_width=True,
        )

        with st.expander("詳細データ"):
            display_df = elasticity_df.with_columns([
                pl.col("price").cast(pl.Int64),
                (pl.col("discount_rate") * 100).round(1).alias("値引率 (%)"),
                pl.col("total_lift").round(0).alias("増分数量"),
                pl.col("total_quantity").round(0).alias("総数量"),
                pl.col("incremental_profit").round(0).alias("増分粗利"),
            ]).select(["price", "値引率 (%)", "増分数量", "総数量", "増分粗利"])
            st.dataframe(display_df.to_pandas(), use_container_width=True)

    # ------------------------------------------------------------------
    # Tab 7: 販促カレンダー入力 (Feature 4)
    # ------------------------------------------------------------------
    with tabs[7]:
        st.header("販促カレンダー入力")
        st.markdown(
            "上段で**既存の販促カレンダー**（promo_calendar.csv）を直接編集できます。"
            "「保存 & 予測を再実行」を押すと、カレンダー変更 → 需要分解 → 予測のパイプラインが自動で走り、"
            "他のタブの予測結果に反映されます（数分かかります）。"
            "下段のフォームからは**新規プラン**を追加し、シミュレータータブに即時連携できます。"
        )

        # --- Existing calendar ---
        st.subheader("既存の販促カレンダー")
        if CALENDAR_FILE.exists():
            existing_cal = pl.read_csv(CALENDAR_FILE)
            # Join with master for item_name (for display)
            existing_with_name = existing_cal.join(
                master_df.select([COL_ITEM_ID, "item_name"]), on=COL_ITEM_ID, how="left",
            )
            st.plotly_chart(
                create_calendar_gantt_chart(existing_with_name, ITEMS),
                use_container_width=True,
            )

            # Editable table for existing calendar
            edit_cols = [
                "item_id", "promo_name", "start_date", "end_date",
                "campaign_cost", "discount_rate_target", "flyer",
            ]
            edited_existing = st.data_editor(
                existing_cal.select(edit_cols).to_pandas(),
                num_rows="dynamic",
                use_container_width=True,
                key="existing_cal_editor",
            )
            col_save, col_rerun = st.columns(2)
            with col_save:
                if st.button("既存カレンダーを保存"):
                    save_df = pl.from_pandas(edited_existing)
                    save_df.write_csv(CALENDAR_FILE)
                    st.success(f"保存しました: {CALENDAR_FILE.name}")
                    st.cache_data.clear()
                    st.rerun()
            with col_rerun:
                if st.button("保存 & 予測を再実行"):
                    save_df = pl.from_pandas(edited_existing)
                    save_df.write_csv(CALENDAR_FILE)
                    with st.spinner("Step 1: 需要分解を実行中..."):
                        from scripts.step1_decompose_demand import decompose_demand
                        decompose_demand()
                    with st.spinner("Step 2: 予測を実行中 (数分かかります)..."):
                        from scripts.step2_run_forecast import run_forecast
                        run_forecast(n_trials=1)
                    st.cache_data.clear()
                    st.cache_resource.clear()
                    st.success("カレンダー保存 → 需要分解 → 予測が完了しました。ページを再読み込みします。")
                    st.rerun()
        else:
            st.info("既存の販促カレンダーがありません。")

        st.divider()

        # --- New plan input ---
        # Initialize session state
        if "promo_plan" not in st.session_state:
            st.session_state.promo_plan = pd.DataFrame(columns=[
                "item_id", "item_name", "promo_name", "start_date", "end_date",
                "target_price", "campaign_cost", "discount_rate_target", "flyer",
            ])

        st.subheader("新規販促プランの追加")
        with st.form("promo_input_form", clear_on_submit=True):
            form_cols = st.columns([2, 2, 2, 1])
            with form_cols[0]:
                form_item = st.selectbox("品目", master_df["item_name"].to_list(), key="form_item")
                form_item_id = master_df.filter(pl.col("item_name") == form_item)["item_id"][0]
                form_item_master = master_df.filter(pl.col(COL_ITEM_ID) == form_item_id)
                form_lp = float(form_item_master["list_price"][0])
                form_uc = float(form_item_master["unit_cost"][0])
            with form_cols[1]:
                form_rank = st.selectbox("販促ランク", list(RANK_DEFAULTS.keys()))
                form_price = st.number_input(
                    "想定販売価格 (円)", min_value=int(form_uc), max_value=int(form_lp),
                    value=int(form_lp * 0.85), step=5,
                )
            with form_cols[2]:
                form_start = st.date_input("開始日", value=today_date + timedelta(days=7))
                form_end = st.date_input("終了日", value=today_date + timedelta(days=14))
            with form_cols[3]:
                rank_def = RANK_DEFAULTS[form_rank]
                form_cost = st.number_input("販促費用 (円)", value=int(rank_def["cost"]), step=1000)
                form_flyer = st.checkbox("チラシ", value=bool(rank_def["flyer"]))

            submitted = st.form_submit_button("追加")
            if submitted:
                disc_rate = (form_lp - form_price) / form_lp
                new_row = pd.DataFrame([{
                    "item_id": int(form_item_id),
                    "item_name": form_item,
                    "promo_name": form_rank,
                    "start_date": form_start,
                    "end_date": form_end,
                    "target_price": float(form_price),
                    "campaign_cost": float(form_cost),
                    "discount_rate_target": round(disc_rate, 4),
                    "flyer": 1 if form_flyer else 0,
                }])
                st.session_state.promo_plan = pd.concat(
                    [st.session_state.promo_plan, new_row], ignore_index=True,
                )
                st.success(f"{form_item} - {form_rank} を追加しました")

        # --- Editable table for new plan ---
        if not st.session_state.promo_plan.empty:
            st.subheader("新規販促計画")
            edited_plan = st.data_editor(
                st.session_state.promo_plan,
                num_rows="dynamic",
                use_container_width=True,
                key="plan_editor",
            )
            st.session_state.promo_plan = edited_plan

            # Gantt chart for new plan
            st.plotly_chart(
                create_calendar_gantt_chart(
                    st.session_state.promo_plan, ITEMS,
                ),
                use_container_width=True,
            )

            # Actions
            col_export, col_sim = st.columns(2)
            with col_export:
                export_df = pl.from_pandas(st.session_state.promo_plan).select([
                    "item_id", "promo_name", "start_date", "end_date",
                    "campaign_cost", "discount_rate_target", "flyer",
                ])
                csv_bytes = export_df.write_csv().encode("utf-8")
                st.download_button(
                    "CSV ダウンロード",
                    data=csv_bytes,
                    file_name="promo_calendar_plan.csv",
                    mime="text/csv",
                )
            with col_sim:
                if st.button("シミュレーター連携"):
                    st.session_state.custom_calendar = pl.from_pandas(
                        st.session_state.promo_plan
                    )
                    st.success("シミュレーターに反映しました。戦略シミュレータータブで確認してください。")
        else:
            st.info("上のフォームから販促プランを追加してください。")


if __name__ == "__main__":
    show_dashboard()
