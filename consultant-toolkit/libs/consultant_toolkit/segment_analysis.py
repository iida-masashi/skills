"""
Business Segment Revenue Analysis Module

事業セグメント別の収益分析機能を提供

Approaches:
    1. Manual Segment Mapping (手動セグメント定義)
    2. AI-based Segment Extraction (AI抽出)
    3. Geographic Revenue Split (地域別分析)
"""

import json
import logging

import pandas as pd
import yfinance as yf
from google.genai import types

logger = logging.getLogger(__name__)

# ========================================
# Manual Segment Mapping
# ========================================

# 主要企業のセグメント定義（手動マッピング）
SEGMENT_MAPPINGS = {
    "AAPL": {
        "company_name": "Apple Inc.",
        "segments": {
            "iPhone": {"percentage": 0.52, "description": "Smartphone hardware"},
            "Services": {
                "percentage": 0.22,
                "description": "App Store, iCloud, Apple Music",
            },
            "Mac": {"percentage": 0.08, "description": "Desktop and laptop computers"},
            "iPad": {"percentage": 0.08, "description": "Tablet computers"},
            "Wearables": {
                "percentage": 0.10,
                "description": "Apple Watch, AirPods, accessories",
            },
        },
        "fiscal_year": 2023,
        "source": "Apple 10-K Filing",
    },
    "MSFT": {
        "company_name": "Microsoft Corporation",
        "segments": {
            "Intelligent Cloud": {
                "percentage": 0.42,
                "description": "Azure, Server products",
            },
            "Productivity": {
                "percentage": 0.34,
                "description": "Office, LinkedIn, Dynamics",
            },
            "Personal Computing": {
                "percentage": 0.24,
                "description": "Windows, Xbox, Surface",
            },
        },
        "fiscal_year": 2023,
        "source": "Microsoft 10-K Filing",
    },
    "GOOGL": {
        "company_name": "Alphabet Inc.",
        "segments": {
            "Google Services": {
                "percentage": 0.88,
                "description": "Search, YouTube, Android",
            },
            "Google Cloud": {
                "percentage": 0.10,
                "description": "Cloud services, Workspace",
            },
            "Other Bets": {"percentage": 0.02, "description": "Verily, Waymo, X"},
        },
        "fiscal_year": 2023,
        "source": "Alphabet 10-K Filing",
    },
    "AMZN": {
        "company_name": "Amazon.com Inc.",
        "segments": {
            "Online Stores": {"percentage": 0.42, "description": "E-commerce retail"},
            "AWS": {"percentage": 0.16, "description": "Cloud computing services"},
            "Third-party Seller": {
                "percentage": 0.24,
                "description": "Marketplace fees",
            },
            "Advertising": {"percentage": 0.08, "description": "Digital advertising"},
            "Other": {
                "percentage": 0.10,
                "description": "Physical stores, subscriptions",
            },
        },
        "fiscal_year": 2023,
        "source": "Amazon 10-K Filing",
    },
    "7203.T": {
        "company_name": "トヨタ自動車株式会社",
        "segments": {
            "自動車": {"percentage": 0.90, "description": "乗用車・商用車の製造販売"},
            "金融": {"percentage": 0.07, "description": "Toyota Financial Services"},
            "その他": {"percentage": 0.03, "description": "住宅、船舶など"},
        },
        "fiscal_year": 2023,
        "source": "トヨタ有価証券報告書",
    },
    "6758.T": {
        "company_name": "ソニーグループ株式会社",
        "segments": {
            "ゲーム＆ネットワーク": {
                "percentage": 0.30,
                "description": "PlayStation, ゲームソフト",
            },
            "音楽": {"percentage": 0.11, "description": "レコード、音楽配信"},
            "映画": {"percentage": 0.12, "description": "映画制作、配給"},
            "エレクトロニクス": {
                "percentage": 0.25,
                "description": "テレビ、カメラ、オーディオ",
            },
            "イメージング＆センシング": {
                "percentage": 0.13,
                "description": "イメージセンサー",
            },
            "金融": {"percentage": 0.09, "description": "生命保険、損保"},
        },
        "fiscal_year": 2023,
        "source": "ソニー有価証券報告書",
    },
}


def get_segment_data_manual(ticker: str) -> dict | None:
    """
    手動マッピングから事業セグメントデータを取得

    Args:
        ticker: ティッカーシンボル

    Returns:
        セグメント情報辞書、見つからない場合はNone
    """
    ticker_upper = ticker.upper()
    return SEGMENT_MAPPINGS.get(ticker_upper)


def calculate_segment_revenue(
    ticker: str, total_revenue: float
) -> pd.DataFrame | None:
    """
    総収益からセグメント別収益を計算

    Args:
        ticker: ティッカーシンボル
        total_revenue: 総収益額

    Returns:
        セグメント別収益DataFrame
    """
    segment_data = get_segment_data_manual(ticker)
    if not segment_data:
        return None

    segments = []
    for seg_name, seg_info in segment_data["segments"].items():
        revenue = total_revenue * seg_info["percentage"]
        segments.append(
            {
                "Segment": seg_name,
                "Revenue": revenue,
                "Percentage": seg_info["percentage"] * 100,
                "Description": seg_info["description"],
            }
        )

    df = pd.DataFrame(segments)
    df = df.sort_values("Revenue", ascending=False)
    return df


# ========================================
# AI-based Segment Extraction
# ========================================


def extract_segments_with_ai(ticker: str, company_name: str) -> dict | None:
    """
    Gemini AIを使って企業の事業セグメント情報を抽出

    Args:
        ticker: ティッカーシンボル
        company_name: 企業名

    Returns:
        抽出されたセグメント情報辞書
    """
    from consultant_toolkit.env_loader import get_api_key

    api_key = get_api_key("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        from consultant_toolkit.gemini_client import DEFAULT_MODEL, create_gemini_client

        client = create_gemini_client(api_key=api_key)

        prompt = f"""
企業名: {company_name} (ティッカー: {ticker})

この企業の最新の事業セグメント構成を教えてください。

以下の形式でJSON形式で回答してください:
{{
    "segments": {{
        "セグメント名1": {{"percentage": 割合(0-1), "description": "説明"}},
        "セグメント名2": {{"percentage": 割合(0-1), "description": "説明"}}
    }},
    "fiscal_year": 年度,
    "source": "情報源"
}}

注意:
- percentage の合計は1.0になるようにしてください
- 最新の有価証券報告書または10-K Filingの情報を使用してください
- セグメント名は日本企業は日本語、米国企業は英語で記載してください
"""

        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1, response_mime_type="application/json"
            ),
        )

        text = response.text
        if not text:
            return None
        segment_info = json.loads(text)
        segment_info["company_name"] = company_name

        return segment_info

    except (ConnectionError, ValueError, KeyError, json.JSONDecodeError) as e:
        logger.error(f"AI segment extraction error: {e}")
        return None


# ========================================
# Geographic Revenue Analysis
# ========================================

GEOGRAPHIC_MAPPINGS = {
    "AAPL": {
        "Americas": 0.42,
        "Europe": 0.25,
        "Greater China": 0.19,
        "Japan": 0.07,
        "Rest of Asia Pacific": 0.07,
    },
    "MSFT": {
        "United States": 0.51,
        "Europe": 0.28,
        "Asia Pacific": 0.15,
        "Other": 0.06,
    },
    "GOOGL": {
        "United States": 0.48,
        "EMEA": 0.31,
        "APAC": 0.17,
        "Other Americas": 0.04,
    },
    "7203.T": {
        "日本": 0.23,
        "北米": 0.27,
        "欧州": 0.10,
        "アジア": 0.31,
        "その他": 0.09,
    },
}


def get_geographic_revenue(ticker: str, total_revenue: float) -> pd.DataFrame | None:
    """
    地域別収益を計算

    Args:
        ticker: ティッカーシンボル
        total_revenue: 総収益額

    Returns:
        地域別収益DataFrame
    """
    ticker_upper = ticker.upper()
    geo_data = GEOGRAPHIC_MAPPINGS.get(ticker_upper)

    if not geo_data:
        return None

    regions = []
    for region, percentage in geo_data.items():
        revenue = total_revenue * percentage
        regions.append(
            {"Region": region, "Revenue": revenue, "Percentage": percentage * 100}
        )

    df = pd.DataFrame(regions)
    df = df.sort_values("Revenue", ascending=False)
    return df


# ========================================
# Unified Interface
# ========================================


def get_segment_analysis(
    ticker: str, use_ai: bool = False
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, str]:
    """
    セグメント分析の統合インターフェース

    Args:
        ticker: ティッカーシンボル
        use_ai: AI抽出を使用するか（True=AI, False=手動マッピング）

    Returns:
        (事業セグメントDF, 地域セグメントDF, データソース)
    """
    # 財務データ取得
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        company_name = info.get("longName", ticker)

        # 総収益取得（直近年度）
        financials = stock.financials
        if financials.empty:
            return None, None, "No financial data available"

        total_revenue = financials.loc["Total Revenue"].iloc[0]

    except (ConnectionError, KeyError, ValueError) as e:
        return None, None, f"Error fetching data: {e}"

    # 事業セグメント分析
    segment_df = None
    source = "Unknown"

    if use_ai:
        # AI抽出モード
        segment_info = extract_segments_with_ai(ticker, company_name)
        if segment_info:
            segment_df = calculate_segment_revenue_from_ai(segment_info, total_revenue)
            source = f"AI-extracted from {segment_info.get('source', 'Unknown')}"

    if segment_df is None:
        # 手動マッピングモード（フォールバック）
        segment_df = calculate_segment_revenue(ticker, total_revenue)
        if segment_df is not None:
            manual_data = get_segment_data_manual(ticker)
            if manual_data:
                source = f"Manual mapping (FY{manual_data['fiscal_year']})"
            else:
                source = "Manual mapping"
        else:
            source = "No segment data available"

    # 地域別セグメント分析
    geo_df = get_geographic_revenue(ticker, total_revenue)

    return segment_df, geo_df, source


def calculate_segment_revenue_from_ai(
    segment_info: dict, total_revenue: float
) -> pd.DataFrame:
    """
    AI抽出されたセグメント情報から収益を計算

    Args:
        segment_info: AI抽出されたセグメント情報
        total_revenue: 総収益額

    Returns:
        セグメント別収益DataFrame
    """
    segments = []
    for seg_name, seg_data in segment_info["segments"].items():
        revenue = total_revenue * seg_data["percentage"]
        segments.append(
            {
                "Segment": seg_name,
                "Revenue": revenue,
                "Percentage": seg_data["percentage"] * 100,
                "Description": seg_data.get("description", ""),
            }
        )

    df = pd.DataFrame(segments)
    df = df.sort_values("Revenue", ascending=False)
    return df


# ========================================
# Utility Functions
# ========================================


def add_segment_mapping(
    ticker: str,
    company_name: str,
    segments: dict[str, dict],
    fiscal_year: int,
    source: str = "Custom",
):
    """
    カスタムセグメントマッピングを追加

    Args:
        ticker: ティッカーシンボル
        company_name: 企業名
        segments: セグメント辞書
        fiscal_year: 会計年度
        source: データソース
    """
    SEGMENT_MAPPINGS[ticker.upper()] = {
        "company_name": company_name,
        "segments": segments,
        "fiscal_year": fiscal_year,
        "source": source,
    }


def get_available_tickers() -> list[str]:
    """
    セグメントデータが利用可能なティッカーリストを取得

    Returns:
        ティッカーシンボルのリスト
    """
    return list(SEGMENT_MAPPINGS.keys())


def segment_growth_analysis(ticker: str, years: int = 3) -> pd.DataFrame | None:
    """
    セグメント別成長率分析（将来実装予定）

    Args:
        ticker: ティッカーシンボル
        years: 分析年数

    Returns:
        セグメント別成長率DataFrame
    """
    # TODO: 複数年のセグメント推移を分析
    # 現状は単年度のみ対応
    return None
