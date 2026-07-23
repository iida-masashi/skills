"""
AI Analytics Utilities

Prophet-based forecasting, anomaly detection, and natural language query processing.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def forecast_revenue_prophet(
    historical_data: pd.DataFrame, periods: int = 4, freq: str = "Q"
) -> pd.DataFrame | None:
    """
    Prophet を使用して売上予測を実行

    Args:
        historical_data: 履歴データ (columns: 'ds', 'y')
        periods: 予測期間数
        freq: 頻度 ('D', 'M', 'Q', 'Y')

    Returns:
        DataFrame: 予測結果 (columns: 'ds', 'yhat', 'yhat_lower', 'yhat_upper')

    Example:
        >>> df = pd.DataFrame({'ds': dates, 'y': revenues})
        >>> forecast = forecast_revenue_prophet(df, periods=4, freq='Q')
    """
    try:
        from prophet import Prophet

        if historical_data.empty or len(historical_data) < 2:
            logger.warning("Insufficient data for forecasting")
            return None

        # Prophet モデル作成
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=False,
            yearly_seasonality=True if freq in ["M", "Q"] else False,
        )

        # モデル訓練
        model.fit(historical_data)

        # 未来データフレーム作成
        future = model.make_future_dataframe(periods=periods, freq=freq)

        # 予測
        forecast = model.predict(future)

        return forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]

    except ImportError:
        logger.error("Prophet not installed. Run: pip install prophet")
        return None
    except ValueError as e:
        logger.error(f"Forecasting value error: {e}")
        return None


def detect_anomalies_isolation_forest(
    metrics_df: pd.DataFrame, feature_columns: list[str], contamination: float = 0.1
) -> pd.DataFrame:
    """
    Isolation Forest を使用して異常値を検出

    Args:
        metrics_df: メトリクスDataFrame
        feature_columns: 分析対象の列名リスト
        contamination: 異常値の割合（0.0 ~ 0.5）

    Returns:
        DataFrame: 元のDataFrame + 'anomaly' 列 (-1: 異常, 1: 正常)

    Example:
        >>> result = detect_anomalies_isolation_forest(
        ...     df,
        ...     ['ROIC', 'CCC', 'Revenue Growth'],
        ...     contamination=0.1
        ... )
    """
    try:
        from sklearn.ensemble import IsolationForest

        if metrics_df.empty:
            return metrics_df

        # 特徴量抽出
        features = metrics_df[feature_columns].fillna(0)

        # Isolation Forest モデル
        model = IsolationForest(contamination=contamination, random_state=42)
        anomalies = model.fit_predict(features)

        # 結果を追加
        result_df = metrics_df.copy()
        result_df["anomaly"] = anomalies
        result_df["is_anomaly"] = anomalies == -1

        return result_df

    except ImportError:
        logger.error("scikit-learn not installed. Run: pip install scikit-learn")
        return metrics_df
    except ValueError as e:
        logger.error(f"Anomaly detection failed: {e}")
        return metrics_df


def analyze_query_with_llm(
    query: str, metrics_data: pd.DataFrame, api_key: str | None = None
) -> str:
    """
    自然言語クエリを解析してデータから回答を生成

    Args:
        query: ユーザーのクエリ（例: "ROICが15%以上の企業を表示"）
        metrics_data: メトリクスDataFrame
        api_key: Gemini API Key

    Returns:
        str: 分析結果テキスト

    Example:
        >>> result = analyze_query_with_llm(
        ...     "ROICが最も高い企業は？",
        ...     df_metrics,
        ...     api_key
        ... )
    """
    try:
        if not api_key:
            from consultant_toolkit.env_loader import get_api_key

            api_key = get_api_key("GOOGLE_API_KEY") or get_api_key("GEMINI_API_KEY")

        if not api_key:
            return "❌ API Key が設定されていません。環境変数 GOOGLE_API_KEY を設定してください。"

        # データのサマリーを作成
        data_summary = metrics_data.head(20).to_string()

        # プロンプト作成
        prompt = f"""
あなたは財務データ分析のエキスパートです。以下のデータに基づいてユーザーの質問に答えてください。

【データサマリー】
{data_summary}

【利用可能な列】
{", ".join(metrics_data.columns)}

【ユーザーの質問】
{query}

【回答】
データを分析し、簡潔かつ具体的に回答してください。必要に応じて数値を示してください。
"""

        # Gemini API 呼び出し
        from consultant_toolkit.gemini_client import DEFAULT_MODEL, create_gemini_client

        client = create_gemini_client(api_key=api_key)
        response = client.models.generate_content(
            model=DEFAULT_MODEL, contents=prompt
        )

        return response.text if response.text else "❌ 応答がありませんでした。"

    except ImportError:
        return "❌ Google Generative AI SDK がインストールされていません。\npip install google-generativeai"
    except (ConnectionError, TimeoutError, ValueError) as e:
        logger.error(f"LLM query failed: {e}")
        return f"❌ エラーが発生しました: {str(e)}"


def calculate_growth_rates(
    historical_df: pd.DataFrame, value_column: str, date_column: str = "Year"
) -> pd.DataFrame:
    """
    成長率を計算

    Args:
        historical_df: 履歴データDataFrame
        value_column: 値の列名
        date_column: 日付の列名

    Returns:
        DataFrame: 成長率が追加されたDataFrame

    Example:
        >>> df_with_growth = calculate_growth_rates(df, 'Revenue')
    """
    df = historical_df.copy()
    df = df.sort_values(date_column)

    # YoY成長率
    df[f"{value_column}_YoY_Growth"] = df[value_column].pct_change() * 100

    # CAGR（複利成長率）計算用のヘルパー
    if len(df) >= 2:
        first_value = df[value_column].iloc[0]
        last_value = df[value_column].iloc[-1]
        years = len(df) - 1

        if first_value > 0:
            cagr = ((last_value / first_value) ** (1 / years) - 1) * 100
            df[f"{value_column}_CAGR"] = cagr

    return df


def generate_insights(metrics_df: pd.DataFrame) -> list[str]:
    """
    メトリクスから自動的にインサイトを生成

    Args:
        metrics_df: メトリクスDataFrame

    Returns:
        List[str]: インサイトのリスト

    Example:
        >>> insights = generate_insights(df_metrics)
        >>> for insight in insights:
        ...     print(f"💡 {insight}")
    """
    insights = []

    # ROIC 分析
    if "ROIC" in metrics_df.columns:
        avg_roic = metrics_df["ROIC"].mean()
        max_roic_company = (
            metrics_df.loc[metrics_df["ROIC"].idxmax(), "Company"]
            if "Company" in metrics_df.columns
            else "N/A"
        )
        max_roic = metrics_df["ROIC"].max()

        insights.append(
            f"平均ROIC: {avg_roic:.2%}、最高は {max_roic_company} ({max_roic:.2%})"
        )

        if avg_roic < 0.05:
            insights.append(
                "⚠️ 平均ROICが5%を下回っています。資本効率の改善が必要です。"
            )

    # CCC 分析
    if "CCC" in metrics_df.columns:
        avg_ccc = metrics_df["CCC"].mean()
        min_ccc_company = (
            metrics_df.loc[metrics_df["CCC"].idxmin(), "Company"]
            if "Company" in metrics_df.columns
            else "N/A"
        )
        min_ccc = metrics_df["CCC"].min()

        insights.append(
            f"平均CCC: {avg_ccc:.1f}日、最短は {min_ccc_company} ({min_ccc:.1f}日)"
        )

        if avg_ccc > 90:
            insights.append(
                "⚠️ 平均CCCが90日を超えています。運転資本効率を改善してください。"
            )

    # 流動比率分析
    if "current_ratio" in metrics_df.columns:
        avg_current_ratio = metrics_df["current_ratio"].mean()

        if avg_current_ratio < 1.0:
            insights.append(
                "⚠️ 流動比率が1.0未満です。短期的な支払い能力に懸念があります。"
            )
        elif avg_current_ratio > 2.0:
            insights.append("✅ 流動比率が健全です（2.0以上）。")

    return insights
