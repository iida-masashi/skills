"""
Advanced Peer Company Suggestion Engine

yfinance API + AI を活用した高度な競合企業提案システム
"""

import json
import logging
from pathlib import Path
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)


def get_company_info(ticker: str) -> dict[str, Any] | None:
    """
    企業情報を取得（業界、時価総額、地域など）

    Args:
        ticker: ティッカーシンボル

    Returns:
        企業情報辞書、取得失敗時はNone
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "name": info.get("longName", ticker),
            "industry": info.get("industry", "Unknown"),
            "sector": info.get("sector", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "country": info.get("country", "Unknown"),
            "currency": info.get("currency", "Unknown"),
        }
    except (ConnectionError, TimeoutError, KeyError, ValueError) as e:
        logger.warning(f"Failed to fetch info for {ticker}: {e}")
        return None


def suggest_peers_basic(target_ticker: str) -> list[str]:
    """
    業界別に競合企業を提案（基本版 - industry_peers.json使用）

    Args:
        target_ticker: 対象企業のティッカーシンボル

    Returns:
        推奨される競合企業のリスト
    """
    config_path = Path(__file__).parent.parent / "config" / "industry_peers.json"

    if not config_path.exists():
        logger.warning(f"industry_peers.json not found at {config_path}")
        return []

    try:
        with open(config_path, encoding="utf-8") as f:
            industry_config = json.load(f)

        # ティッカーシンボルから業界を推定
        ticker_base = target_ticker.replace(".T", "").replace(".DE", "")

        for _industry, config in industry_config.items():
            if any(keyword in ticker_base for keyword in config.get("keywords", [])):
                # 日本企業（.T）が対象の場合は domestic_peers を先に返す
                is_japan = target_ticker.endswith(".T")
                if is_japan:
                    peers = config.get("domestic_peers", []) + config.get(
                        "global_peers", []
                    )
                else:
                    peers = config.get("global_peers", []) + config.get(
                        "domestic_peers", []
                    )
                logger.info(
                    f"🌐 Industry: {config.get('description')} - Suggested peers: {peers}"
                )
                return [p for p in peers if p != target_ticker]

        return []
    except (json.JSONDecodeError, KeyError, OSError) as e:
        logger.error(f"Error loading industry_peers.json: {e}")
        return []


def suggest_peers_advanced(
    target_ticker: str,
    max_peers: int = 5,
    prefer_same_country: bool = True,
    size_tolerance: float = 5.0,
) -> list[str]:
    """
    高度な競合企業提案エンジン

    yfinance APIを使用して、業界・時価総額・地域を考慮した競合を自動提案

    Args:
        target_ticker: 対象企業のティッカーシンボル
        max_peers: 最大提案数
        prefer_same_country: 同じ国の企業を優先するか
        size_tolerance: 時価総額の許容倍率（例: 5.0 = 0.2x ~ 5x の範囲）

    Returns:
        推奨される競合企業のリスト（優先度順）
    """
    logger.info(f"🔍 Advanced peer suggestion for {target_ticker}...")

    # 1. 対象企業の情報を取得
    target_info = get_company_info(target_ticker)
    if not target_info:
        logger.warning(
            "Failed to get target company info. Falling back to basic suggestion."
        )
        return suggest_peers_basic(target_ticker)

    target_industry = target_info["industry"]
    target_sector = target_info["sector"]
    target_market_cap = target_info["market_cap"]
    target_country = target_info["country"]

    logger.info(f"📊 Target: {target_info['name']}")
    logger.info(f"   Industry: {target_industry}, Sector: {target_sector}")
    logger.info(f"   Market Cap: ${target_market_cap:,.0f}, Country: {target_country}")

    # 2. 候補企業リストを構築（industry_peers.json + グローバル検索）
    candidate_peers = suggest_peers_basic(target_ticker)

    # 3. セクターベースの有名企業を追加（フォールバック用）
    sector_fallback = _get_sector_fallback_peers(target_sector, target_country)
    for peer in sector_fallback:
        if peer not in candidate_peers and peer != target_ticker:
            candidate_peers.append(peer)

    if not candidate_peers:
        logger.warning("No candidate peers found.")
        return []

    # 4. 各候補のスコアリング
    scored_peers = []

    for peer_ticker in candidate_peers:
        peer_info = get_company_info(peer_ticker)
        if not peer_info:
            continue

        score = _calculate_peer_score(
            target_info, peer_info, prefer_same_country, size_tolerance
        )

        scored_peers.append(
            {
                "ticker": peer_ticker,
                "name": peer_info["name"],
                "score": score,
                "industry": peer_info["industry"],
                "market_cap": peer_info["market_cap"],
            }
        )

    # 5. スコア順にソート
    scored_peers.sort(key=lambda x: x["score"], reverse=True)

    # 6. 上位を返す
    top_peers = [p["ticker"] for p in scored_peers[:max_peers]]

    logger.info(f"✅ Top {len(top_peers)} peers suggested:")
    for i, p_dict in enumerate(scored_peers[:max_peers], 1):
        logger.info(
            f"   {i}. {p_dict['ticker']} - {p_dict['name']} (Score: {p_dict['score']:.2f})"
        )

    return top_peers


def _calculate_peer_score(
    target: dict[str, Any],
    peer: dict[str, Any],
    prefer_same_country: bool,
    size_tolerance: float,
) -> float:
    """
    競合企業のスコアを計算

    スコアリング基準:
    - 業界一致: +50点
    - セクター一致: +30点
    - 同じ国: +20点（prefer_same_country=True時）
    - 時価総額の近さ: 最大+30点

    Args:
        target: 対象企業情報
        peer: 候補企業情報
        prefer_same_country: 同じ国を優先するか
        size_tolerance: 時価総額の許容倍率

    Returns:
        スコア（0-130点）
    """
    score = 0.0

    # 業界一致（最重要）
    if peer["industry"] == target["industry"] and peer["industry"] != "Unknown":
        score += 50.0

    # セクター一致
    if peer["sector"] == target["sector"] and peer["sector"] != "Unknown":
        score += 30.0

    # 同じ国
    if prefer_same_country and peer["country"] == target["country"]:
        score += 20.0

    # 時価総額の近さ（最大30点）
    if target["market_cap"] > 0 and peer["market_cap"] > 0:
        ratio = peer["market_cap"] / target["market_cap"]

        if 1 / size_tolerance <= ratio <= size_tolerance:
            # 近いほど高得点
            distance = abs(1.0 - ratio)
            proximity_score = max(0, 30.0 * (1.0 - distance))
            score += proximity_score

    return score


def _get_sector_fallback_peers(sector: str, country: str) -> list[str]:
    """
    セクター別のフォールバック競合リスト

    Args:
        sector: セクター名
        country: 国名

    Returns:
        フォールバック競合リスト
    """
    # 日本企業向け
    japan_fallback = {
        "Consumer Cyclical": ["7203.T", "7267.T", "7201.T"],  # 自動車
        "Industrials": ["6301.T", "6305.T", "6326.T"],  # 機械
        "Technology": ["6758.T", "6902.T", "6971.T"],  # 電気機器
        "Healthcare": ["4502.T", "4503.T", "4568.T"],  # 医薬品
        "Financial Services": ["8306.T", "8316.T", "8411.T"],  # 銀行
    }

    # グローバル企業向け
    global_fallback = {
        "Consumer Cyclical": ["TSLA", "F", "GM", "TM"],
        "Industrials": ["BA", "GE", "CAT", "HON"],
        "Technology": ["AAPL", "MSFT", "GOOGL", "META"],
        "Healthcare": ["JNJ", "PFE", "UNH", "ABBV"],
        "Financial Services": ["JPM", "BAC", "WFC", "C"],
        "Communication Services": ["META", "GOOGL", "DIS", "NFLX"],
        "Consumer Defensive": ["PG", "KO", "PEP", "WMT"],
        "Energy": ["XOM", "CVX", "COP", "SLB"],
        "Basic Materials": ["LIN", "APD", "ECL", "SHW"],
        "Real Estate": ["AMT", "PLD", "CCI", "EQIX"],
        "Utilities": ["NEE", "DUK", "SO", "D"],
    }

    if country == "Japan":
        return japan_fallback.get(sector, [])
    else:
        return global_fallback.get(sector, [])


def suggest_peers_with_ai(
    target_ticker: str, api_key: str | None = None, max_peers: int = 5
) -> list[str]:
    """
    AI（Gemini）を使用した動的競合提案

    Args:
        target_ticker: 対象企業のティッカーシンボル
        api_key: Gemini API Key
        max_peers: 最大提案数

    Returns:
        AIが提案した競合企業リスト
    """
    try:
        from consultant_toolkit.env_loader import get_api_key as get_env_key

        if not api_key:
            api_key = get_env_key("GOOGLE_API_KEY") or get_env_key("GEMINI_API_KEY")

        if not api_key:
            logger.warning("No API key for AI suggestion. Falling back to advanced.")
            return suggest_peers_advanced(target_ticker, max_peers)

        # 対象企業情報を取得
        target_info = get_company_info(target_ticker)
        if not target_info:
            return suggest_peers_advanced(target_ticker, max_peers)

        # AIプロンプト作成
        prompt = f"""
あなたは金融アナリストです。以下の企業の競合企業を{max_peers}社提案してください。

【対象企業】
- ティッカー: {target_ticker}
- 企業名: {target_info["name"]}
- 業界: {target_info["industry"]}
- セクター: {target_info["sector"]}
- 国: {target_info["country"]}

【提案基準】
1. 同じ業界・セクターの企業を優先
2. 時価総額が近い企業を優先
3. グローバル企業と国内企業のバランス

【出力形式】
ティッカーシンボルのみをカンマ区切りで出力してください。
例: AAPL,MSFT,GOOGL

出力:
"""

        from consultant_toolkit.gemini_client import DEFAULT_MODEL, create_gemini_client

        client = create_gemini_client(api_key=api_key)
        response = client.models.generate_content(
            model=DEFAULT_MODEL, contents=prompt
        )

        if response.text:
            # ティッカーシンボルを抽出
            tickers = [t.strip().upper() for t in response.text.split(",") if t.strip()]
            # 対象企業を除外
            tickers = [t for t in tickers if t != target_ticker]

            logger.info(f"🤖 AI suggested peers: {tickers}")
            return tickers[:max_peers]

    except (ImportError, ConnectionError, ValueError, KeyError) as e:
        logger.warning(f"AI suggestion failed: {e}. Falling back to advanced.")

    return suggest_peers_advanced(target_ticker, max_peers)
