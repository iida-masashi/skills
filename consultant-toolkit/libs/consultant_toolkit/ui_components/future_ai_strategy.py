import os

import plotly.graph_objects as go
import streamlit as st
from google import genai

from consultant_toolkit.gemini_client import (
    DEFAULT_MODEL,
    create_gemini_client,
    handle_gemini_api_error,
)
from consultant_toolkit.ui_components.ui_helpers import load_base_financials


def render_ai_strategy(
    target_ticker,
    target_company_name,
    load_financial_data,
    get_val_safe,
    DAYS_PER_YEAR=365,
):
    """
    サブタブ 3.4: AI SCM戦略提案 (AI Consultant)
    """
    st.header("3.4 🤖 AI SCM戦略提案 (AI Consultant)")
    st.markdown(
        "現在の財務・SCM・キャッシュフローデータをもとに、Gemini AIが用途や目的に合わせた具体的な経営・SCM改善策を提示します。"
    )

    api_key_strat = st.text_input(
        "Gemini API Key (AI Consultant)",
        type="password",
        value=os.getenv("GOOGLE_API_KEY", ""),
        key="ai_consultant_api_key_v3",
    )

    # AIコンサルタント内での用途別タブ分け
    ai_purpose_tabs = st.tabs(
        [
            "📊 利益・効率改善インパクト試算",
            "🧠 戦略立案アドバイザリー",
            "📉 SCMリスク・レジリエンス診断",
        ]
    )

    # --- 共通データの取得 ---
    fin = load_base_financials(target_ticker, load_financial_data, get_val_safe)
    has_data = fin.has_real_data

    current_revenue_ai = fin.revenue
    current_cogs_ai = fin.cogs
    current_oi_ai = fin.operating_income
    current_inventory_ai = fin.inventory
    current_oi_margin_ai = fin.oi_margin
    current_ccc_ai = fin.ccc

    balance_sheet_ai = fin.raw_balance_sheet
    latest_year_ai = fin.latest_year

    # === 1. 利益・効率改善インパクト試算 ===
    with ai_purpose_tabs[0]:
        st.subheader("🎯 改善目標設定 & インパクト予測")
        col_target1, col_target2 = st.columns(2)
        with col_target1:
            cogs_red = st.slider(
                "売上原価率 削減目標 (%)", 0.0, 10.0, 2.0, 0.5, key="ai_cogs_red_v3"
            )
        with col_target2:
            ccc_red = st.slider(
                "CCC 改善目標 (日)", 0, 60, 15, 5, key="ai_ccc_red_v3"
            )

        if has_data:
            # --- ROIC計算 (共通) ---
            equity_ai = get_val_safe(
                balance_sheet_ai,
                ["Stockholders Equity", "Total Equity Gross Minority Interest"],
                latest_year_ai,
            )
            debt_ai = get_val_safe(balance_sheet_ai, ["Total Debt"], latest_year_ai)
            invested_cap_ai = equity_ai + debt_ai
            current_nopat_ai = current_oi_ai * 0.7
            current_roic_ai = (
                (current_nopat_ai / invested_cap_ai * 100)
                if invested_cap_ai > 0
                else 0
            )

            # シミュレーション計算
            sim_oi_margin_ai = current_oi_margin_ai + cogs_red
            working_cap_reduction = (ccc_red / DAYS_PER_YEAR) * current_cogs_ai
            sim_invested_cap = max(
                invested_cap_ai * 0.1, invested_cap_ai - working_cap_reduction
            )
            sim_oi_ai = current_revenue_ai * sim_oi_margin_ai / 100
            sim_roic_ai = (
                (sim_oi_ai * 0.7 / sim_invested_cap * 100)
                if sim_invested_cap > 0
                else 0
            )

            col_ba1, col_ba2 = st.columns(2)
            with col_ba1:
                st.markdown("### 📉 Before（現状）")
                c1, c2, c3 = st.columns(3)
                c1.metric("営業利益率", f"{current_oi_margin_ai:.1f}%")
                c2.metric("CCC", f"{current_ccc_ai:.0f}日")
                c3.metric("ROIC", f"{current_roic_ai:.2f}%")
            with col_ba2:
                st.markdown("### 📈 After（改善後）")
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "営業利益率", f"{sim_oi_margin_ai:.1f}%", f"{cogs_red:+.1f}pp"
                )
                c2.metric(
                    "CCC",
                    f"{current_ccc_ai - ccc_red:.0f}日",
                    f"{-ccc_red:.0f}日",
                    delta_color="inverse",
                )
                c3.metric(
                    "ROIC",
                    f"{sim_roic_ai:.2f}%",
                    f"{sim_roic_ai - current_roic_ai:+.2f}pp",
                )

            st.info(
                f"💡 CCC {ccc_red}日の短縮により、約 **{working_cap_reduction / 1e6:,.1f}M** の運転資本が解放される見込みよ。"
            )

            # ビジュアル: 水平棒グラフ
            fig_ba = go.Figure()
            fig_ba.add_trace(
                go.Bar(
                    name="現状",
                    y=["営業利益率 (%)"],
                    x=[current_oi_margin_ai],
                    orientation="h",
                    marker_color="#ff7f0e",
                )
            )
            fig_ba.add_trace(
                go.Bar(
                    name="改善後",
                    y=["営業利益率 (%)"],
                    x=[sim_oi_margin_ai],
                    orientation="h",
                    marker_color="#2ca02c",
                )
            )
            fig_ba.update_layout(
                title="利益率改善インパクト",
                barmode="group",
                height=300,
                template="plotly_white",
            )
            st.plotly_chart(fig_ba, use_container_width=True)
        else:
            st.info("分析データを読み込んでください。")

    # === 2. 戦略立案アドバイザリー ===
    with ai_purpose_tabs[1]:
        st.subheader("🧠 経営課題に適合した戦略的提言")
        advisory_mode = st.selectbox(
            "分析・提言の重点テーマを選択",
            [
                "総合経営診断",
                "収益性改善（原価・販管費の構造改革）",
                "運転資本最適化（在庫・キャッシュフロー最大化）",
                "投資戦略と事業ポートフォリオ再構築",
            ],
            key="ai_mode_v4",
        )

        st.subheader("📋 分析パラメータ")
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        col_opt1.checkbox("SCM・運転資本分析", value=True, key="ai_inc_scm_v3")
        col_opt2.checkbox("CAPEX・投資効率分析", value=True, key="ai_inc_capex_v3")
        col_opt3.checkbox(
            "事業ポートフォリオ(PPM)分析", value=True, key="ai_inc_ppm_v3"
        )

        if st.button(
            "🤖 戦略的提言の生成を開始",
            type="primary",
            use_container_width=True,
            key="ai_gen_btn_v4",
        ):
            if not api_key_strat:
                st.error("API Keyを入力してください。")
            else:
                with st.spinner(
                    f"AIが『{advisory_mode}』の観点から戦略を策定中です..."
                ):
                    try:
                        client = create_gemini_client(api_key=api_key_strat)
                        prompt = f"""あなたは大手戦略コンサルティングファームのマネージング・ディレクターです。
                        対象企業 {target_company_name} ({target_ticker}) に対し、『{advisory_mode}』というテーマで経営戦略の提言を行ってください。

                        【要件】:
                        1. 文体は極めてプロフェッショナルかつ客観的、かつ実行可能な具体性を持ってください。
                        2. 財務データに基づいた冷徹な現状分析から入り、価値創造に向けた戦略的プライオリティを明示してください。
                        3. 形式はエグゼクティブ・サマリー形式とし、定量的目標（KPI）の設定を含めてください。
                        """
                        response = client.models.generate_content(
                            model=DEFAULT_MODEL, contents=prompt
                        )
                        st.markdown("---")
                        st.markdown(response.text)
                    except genai.errors.APIError as e:
                        st.error(handle_gemini_api_error(e))
                    except (ConnectionError, TimeoutError, RuntimeError) as e:
                        st.error(f"分析プロセスでエラーが発生しました: {e}")

    # === 3. SCMリスク・レジリエンス診断 ===
    with ai_purpose_tabs[2]:
        st.subheader("⚠️ 供給網リスク・インパクト評価 & レジリエンス診断")
        st.markdown(
            "外部マクロ環境の変化がサプライチェーンおよび財務健全性に与える影響を、AIが定量的・構造的に診断します。"
        )

        # 診断履歴・チャット履歴の初期化
        if "risk_diag_report" not in st.session_state:
            st.session_state.risk_diag_report = None
        if "risk_chat_history" not in st.session_state:
            st.session_state.risk_chat_history = []

        risk_type = st.radio(
            "診断対象リスク",
            [
                "為替ボラティリティ（購買コスト・輸出採算）",
                "地政学的リスク（グローバル物流の遮断・リードタイム延長）",
                "原材料およびエネルギー価格の構造的高騰",
                "需要ショック（主要市場の急激な景気減速）",
            ],
            key="ai_risk_type_v5",
        )

        risk_severity = st.select_slider(
            "リスク・シナリオの強度",
            options=[
                "軽微な変動（一時的）",
                "中程度のストレス（1〜2四半期）",
                "極めて深刻（構造的・長期的）",
            ],
            value="中程度のストレス（1〜2四半期）",
            key="ai_risk_severity_v5",
        )

        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            run_diag = st.button(
                "🚨 リスク・シミュレーションを実行",
                type="primary",
                use_container_width=True,
                key="ai_risk_btn_v5",
            )
        with col_btn2:
            if st.button(
                "🗑️ 履歴をリセット", use_container_width=True, key="ai_risk_clear_v5"
            ):
                st.session_state.risk_diag_report = None
                st.session_state.risk_chat_history = []
                st.rerun()

        if run_diag:
            if not api_key_strat:
                st.error("API Keyを入力してください。")
            elif not has_data:
                st.error("分析に必要な財務データが読み込まれていません。")
            else:
                with st.spinner(
                    f"『{risk_type}』に対するレジリエンス・モデリングを実行中..."
                ):
                    try:
                        client = create_gemini_client(api_key=api_key_strat)

                        risk_context = f"""
                        【対象企業】: {target_company_name} ({target_ticker})
                        【診断リスク】: {risk_type}
                        【シナリオ強度】: {risk_severity}
                        【現状指標】: 営業利益率 {current_oi_margin_ai:.1f}%, CCC {current_ccc_ai:.0f}日, 在庫 {current_inventory_ai / 1e6:,.0f}M
                        """

                        prompt = f"""あなたはサプライチェーン・リスク管理専門のコンサルタントです。
                        {risk_context}
                        に基づいて、財務インパクト、レジリエンス評価、短期的緩和策、長期的転換案を詳細に診断してください。
                        文体はプロフェッショナルなコンサルティング・トーンとします。
                        """

                        response = client.models.generate_content(
                            model=DEFAULT_MODEL, contents=prompt
                        )
                        st.session_state.risk_diag_report = response.text
                        # google-genai SDK 形式 (parts: [{'text': ...}]) で履歴を保持
                        st.session_state.risk_chat_history = [
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "text": f"{risk_type} ({risk_severity}) のリスク診断を実行してください。"
                                    }
                                ],
                            },
                            {"role": "model", "parts": [{"text": response.text}]},
                        ]
                    except genai.errors.APIError as e:
                        st.error(handle_gemini_api_error(e))
                    except (ConnectionError, TimeoutError, RuntimeError) as e:
                        st.error(f"リスク診断でエラーが発生しました: {e}")

        # --- 診断結果の表示 & 対話インターフェース ---
        if st.session_state.risk_diag_report:
            st.markdown("---")
            for message in st.session_state.risk_chat_history:
                role = message["role"]
                # 表示用に text を抽出
                content = message["parts"][0]["text"]
                with st.chat_message(role):
                    st.markdown(content)

            # 追加質問
            if follow_up_q := st.chat_input(
                "この診断結果について深掘りする（例：具体的な代替調達先の検討ステップは？）"
            ):
                # 履歴に追加 (SDK形式)
                st.session_state.risk_chat_history.append(
                    {"role": "user", "parts": [{"text": follow_up_q}]}
                )

                # 再描画を促すため、ここでは spinner と生成を行う
                with st.chat_message("user"):
                    st.markdown(follow_up_q)

                with st.chat_message("model"):
                    with st.spinner("追加分析中..."):
                        try:
                            client = create_gemini_client(api_key=api_key_strat)
                            # SDK形式の履歴をそのまま渡す
                            response = client.models.generate_content(
                                model=DEFAULT_MODEL,
                                contents=st.session_state.risk_chat_history,
                            )
                            answer = response.text
                            st.markdown(answer)
                            # 履歴に追加
                            st.session_state.risk_chat_history.append(
                                {"role": "model", "parts": [{"text": answer}]}
                            )
                            st.rerun()
                        except genai.errors.APIError as e:
                            st.error(handle_gemini_api_error(e))
                        except (ConnectionError, TimeoutError, RuntimeError) as e:
                            st.error(f"対話エラー: {e}")
