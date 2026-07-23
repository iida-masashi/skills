"""
Universal Company Analysis CLI

任意の企業・業界で財務・SCM分析を実行するコマンドラインツール。

主な機能:
    - 業界別自動競合提案（industry_peers.json参照）
    - ROIC, CCC, DIO/DSO/DPO 自動計算
    - AI分析（Gemini → OpenAI 自動フォールバック）
    - Polars による高速データ処理

使用方法:
    # 自動競合提案付き分析
    $ python analyze_company_cli.py --target 5988.T --auto-peers

    # 手動で競合指定
    $ python analyze_company_cli.py --target 7203.T --competitors 7267.T,7201.T

    # 自動提案と手動指定の併用
    $ python analyze_company_cli.py --target 5988.T --competitors 5949.T --auto-peers

環境変数:
    GOOGLE_API_KEY または GEMINI_API_KEY: Gemini API Key（優先）
    OPENAI_API_KEY: OpenAI API Key（フォールバック用）

依存パッケージ:
    yfinance, polars, pandas, google-genai, openai

出力形式:
    - 財務・SCMメトリクスの比較表（Polars DataFrame）
    - AI による詳細分析レポート

作成者: consultant-toolkit project
最終更新: 2026-02-22
バージョン: 2.0.0（企業特化コード削除・汎用化完了）
"""

import argparse
import logging
import sys

import polars as pl

# Import utility modules
from consultant_toolkit.env_loader import get_api_key, load_environment
from consultant_toolkit.finance_data import fetch_financial_data, get_safe_value
from consultant_toolkit.financial_metrics import calculate_ccc, calculate_financial_metrics
from consultant_toolkit.peer_suggestion import (
    suggest_peers_advanced,
    suggest_peers_basic,
    suggest_peers_with_ai,
)

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Windows encoding fix
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore


def fetch_financial_metrics(
    ticker_symbol: str,
) -> dict[str, str | float] | None:
    """
    Fetches financial data and calculates SCM/Financial metrics using utility modules.
    Returns a dictionary of metrics or None if data is unavailable.
    """
    try:
        logger.info(f"Fetching data for: {ticker_symbol}")

        # Use unified data fetching
        data = fetch_financial_data(ticker_symbol)
        if not data:
            logger.error(f"Data empty for {ticker_symbol}")
            return None

        # Get latest available date
        latest_date = data.balance_sheet.columns[0]
        prev_date = (
            data.balance_sheet.columns[1]
            if len(data.balance_sheet.columns) > 1
            else None
        )

        # Calculate financial metrics using unified functions
        financial_metrics = calculate_financial_metrics(
            data.financials, data.balance_sheet, latest_date
        )

        ccc_metrics = calculate_ccc(data.financials, data.balance_sheet, latest_date)

        # Calculate revenue growth
        revenue = financial_metrics["revenue"]
        prev_revenue = (
            get_safe_value(
                data.financials, ["Total Revenue", "Operating Revenue"], prev_date, 0.0
            )
            if prev_date
            else 0.0
        )
        revenue_growth = (
            ((revenue - prev_revenue) / prev_revenue) * 100 if prev_revenue else 0.0
        )

        metrics: dict[str, str | float] = {
            "Symbol": ticker_symbol,
            "Name": str(data.info.get("longName", ticker_symbol)),
            "Revenue": float(revenue) if revenue is not None else 0.0,
            "Revenue Growth (%)": float(revenue_growth) if revenue_growth is not None else 0.0,
            "Operating Income": float(financial_metrics["operating_income"]) if isinstance(financial_metrics, dict) and "operating_income" in financial_metrics else 0.0,
            "ROIC (%)": float(financial_metrics["roic"] * 100) if isinstance(financial_metrics, dict) and "roic" in financial_metrics else 0.0,
            "CCC (Days)": float(ccc_metrics.get("ccc", 0.0)) if isinstance(ccc_metrics, dict) else 0.0,
            "DIO (Inventory Days)": float(ccc_metrics.get("dio", 0.0)) if isinstance(ccc_metrics, dict) else 0.0,
            "DSO (Receivable Days)": float(ccc_metrics.get("dso", 0.0)) if isinstance(ccc_metrics, dict) else 0.0,
            "DPO (Payable Days)": float(ccc_metrics.get("dpo", 0.0)) if isinstance(ccc_metrics, dict) else 0.0,
        }

        return metrics

    except (ConnectionError, TimeoutError) as e:
        logger.error(f"Network error fetching {ticker_symbol}: {e}", exc_info=True)
        return None
    except KeyError as e:
        logger.error(
            f"Data structure error for {ticker_symbol}: missing key {e}", exc_info=True
        )
        return None
    except ValueError as e:
        logger.error(f"Invalid data for {ticker_symbol}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching {ticker_symbol}: {e}")
        return None


def suggest_peers(target_ticker: str, mode: str = "advanced") -> list[str]:
    """
    業界別に競合企業を提案する汎用関数（強化版）

    Args:
        target_ticker: 対象企業のティッカーシンボル
        mode: 提案モード ("basic", "advanced", "ai")

    Returns:
        推奨される競合企業のリスト
    """
    if mode == "ai":
        return suggest_peers_with_ai(target_ticker, max_peers=8)
    elif mode == "advanced":
        return suggest_peers_advanced(target_ticker, max_peers=8)
    else:
        return suggest_peers_basic(target_ticker)


def _generate_analysis_prompt(
    target_name: str, target_ticker: str, df: pl.DataFrame
) -> str:
    """
    AI分析用プロンプトを生成

    Args:
        target_name: 対象企業名
        target_ticker: 対象ティッカー
        df: 財務データフレーム

    Returns:
        生成されたプロンプト文字列
    """
    markdown_table = df.to_pandas().to_markdown(index=False, floatfmt=".2f")

    return f"""
    あなたは、**超辛口かつ論理的な「SCM戦略コンサルタント（20代女性、自信家）」** です。
    以下の財務・SCMデータに基づき、対象企業「{target_name} ({target_ticker})」を競合と比較し、経営課題を鋭く指摘してください。

    **分析データ:**
    {markdown_table}

    **分析要件:**
    1.  **Financial Health (財務健全性)**:
            *   ROIC（投下資本利益率）はどう？ 資本コストを上回ってる？
            *   成長性 (Revenue Growth) と利益率のバランスは？ 「張りぼての成長」じゃない？

    2.  **SCM Efficiency (サプライチェーン効率)**:
            *   CCC (Cash Conversion Cycle) は競合より短い？ 長いなら何がボトルネック？
            *   DIO (在庫回転日数) が高すぎない？ 過剰在庫でキャッシュ寝かせてない？

    3.  **Strategic Positioning (戦略的位置づけ)**:
            *   PPM分析的にどこ？ (Star, Cash Cow, Dog, Question Mark)
            *   「負け犬」なら撤退すべき？ 「金のなる木」ならもっと投資すべき？

    4.  **Actionable Plan (具体的な殲滅プラン)**:
            *   **在庫削減**: 具体的に何日減らす？ そのために必要な施策は？（SKU削減、需要予測精度向上など）
            *   **キャッシュフロー改善**: DPO延長交渉？ ファクタリング？ 具体策を提示しなさい。
            *   **ポートフォリオ**: 低収益製品をどう処分する？

    **トーン＆マナー:**
    *   一人称は「私」。語尾は「〜わよ」「〜なさい」「〜じゃない？」等の強気な口調。
    *   曖昧な表現は禁止。「〜と思われる」ではなく「〜だ」と断定すること。
    *   数字を使って論理的に詰めること。
    *   最後に必ず「分かったらさっさと実行に移しなさい！」と叱咤激励すること。
    """


def _call_gemini_api(api_key: str, prompt: str) -> str | None:
    """
    Gemini APIを呼び出し

    Args:
        api_key: Gemini API Key
        prompt: 分析プロンプト

    Returns:
        生成されたテキスト、失敗時はNone
    """
    try:
        from consultant_toolkit.gemini_client import DEFAULT_MODEL, create_gemini_client

        client = create_gemini_client(api_key=api_key)
        response = client.models.generate_content(
            model=DEFAULT_MODEL, contents=prompt
        )
        return response.text if response.text else None

    except ImportError as e:
        logger.error(f"Gemini SDK not installed: {e}")
    except ValueError as e:
        logger.error(f"Invalid API key or model configuration: {e}")
    except ConnectionError as e:
        logger.error(f"Network error connecting to Gemini: {e}")
    except Exception as e:
        logger.exception(f"Gemini SDK execution failed: {e}")

    return None


def _call_openai_api(api_key: str, prompt: str) -> str | None:
    """
    OpenAI APIを呼び出し

    Args:
        api_key: OpenAI API Key
        prompt: 分析プロンプト

    Returns:
        生成されたテキスト、失敗時はNone
    """
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert SCM Consultant."},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content

    except ImportError as e:
        logger.error(f"OpenAI SDK not installed: {e}")
    except ValueError as e:
        logger.error(f"Invalid OpenAI API key or configuration: {e}")
    except ConnectionError as e:
        logger.error(f"Network error connecting to OpenAI: {e}")
    except Exception as e:
        logger.exception(f"OpenAI execution failed: {e}")

    return None


def analyze_with_ai(df: pl.DataFrame, target_ticker: str) -> None:
    """
    AI分析を実行（Gemini → OpenAI fallback）

    Args:
        df: 財務データフレーム
        target_ticker: 対象企業のティッカーシンボル

    Strategy:
        1. Try Google Gemini - Best for long context/reasoning
        2. Fallback to OpenAI (GPT-4o) - Reliable alternative
    """
    # 対象企業データを抽出
    target_row = df.filter(pl.col("Symbol") == target_ticker).to_dicts()
    if not target_row:
        logger.error(f"Target ticker {target_ticker} not found in data.")
        return

    target_name = target_row[0]["Name"]
    prompt = _generate_analysis_prompt(target_name, target_ticker, df)

    # Try Gemini
    google_key = get_api_key("GOOGLE_API_KEY") or get_api_key("GEMINI_API_KEY")
    if google_key:
        result = _call_gemini_api(google_key, prompt)
        if result:
            print(
                f"\n{'=' * 60}\n--- AI Analysis for {target_name} (Gemini) ---\n{result}\n{'=' * 60}\n"
            )
            return
    else:
        logger.warning("No GOOGLE_API_KEY found. Skipping Gemini.")

    # Fallback to OpenAI
    logger.info("Falling back to OpenAI (GPT-4o)...")
    openai_key = get_api_key("OPENAI_API_KEY")
    if not openai_key:
        logger.error("No API keys found for AI analysis")
        return

    result = _call_openai_api(openai_key, prompt)
    if result:
        print(
            f"\n{'=' * 60}\n--- AI Analysis for {target_name} (OpenAI) ---\n{result}\n{'=' * 60}\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SCM & Financial Analysis CLI (Universal)"
    )
    parser.add_argument(
        "--target", required=True, help="Target Ticker Symbol (e.g., 7203.T, 2229.T)"
    )
    parser.add_argument(
        "--competitors",
        required=False,
        help="Competitor Ticker Symbols (comma separated, e.g., 7267.T,7201.T)",
    )
    parser.add_argument(
        "--auto-peers", action="store_true", help="Auto-suggest industry peers"
    )
    parser.add_argument(
        "--suggestion-mode",
        choices=["basic", "advanced", "ai"],
        default="advanced",
        help="Peer suggestion mode: basic (config-based), advanced (industry+size), ai (AI-powered)",
    )

    args = parser.parse_args()

    target_ticker = args.target.strip()
    competitors = []

    if args.competitors:
        competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]

    # 🌐 Auto-suggest industry peers
    if args.auto_peers or not competitors:
        suggested_peers = suggest_peers(target_ticker, mode=args.suggestion_mode)
        if suggested_peers:
            for peer in suggested_peers:
                if peer not in competitors:
                    competitors.append(peer)
            logger.info(
                f"🌐 Auto-suggested peers ({args.suggestion_mode} mode): {suggested_peers}"
            )

    if not competitors:
        logger.warning(
            "No competitors specified. Analysis will be limited to target company only."
        )

    load_environment()

    # 1. Fetch Data
    tickers = [target_ticker] + competitors
    all_metrics: list[dict[str, str | float]] = []

    for t in tickers:
        m = fetch_financial_metrics(t)
        if m:
            all_metrics.append(m)
        else:
            logger.warning(f"Skipping {t} due to missing data.")

    if not all_metrics:
        logger.error("No data available to analyze.")
        sys.exit(1)

    # 2. Process with Polars
    df = pl.DataFrame(all_metrics)

    # Display Data
    print("\n--- Financial & SCM Metrics ---")
    # Select columns for display
    display_cols = [
        "Symbol",
        "Name",
        "ROIC (%)",
        "CCC (Days)",
        "DIO (Inventory Days)",
        "Revenue Growth (%)",
    ]

    # Check if columns exist (in case of empty data structure issues)
    valid_cols = [c for c in display_cols if c in df.columns]

    # Polars formatting for display
    with pl.Config(tbl_formatting="ASCII_MARKDOWN", float_precision=2):
        print(df.select(valid_cols))
    print("\n")

    # 3. AI Analysis
    analyze_with_ai(df, target_ticker)


if __name__ == "__main__":
    main()
