"""
Step 4: HTML Report Export (Final Fixed).
Generates a static report using standardized plotting logic.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.absolute()
if str(ROOT_DIR) not in sys.path: sys.path.insert(0, str(ROOT_DIR))

import logging

import polars as pl
from libs.chart_builder import create_decomposition_chart
from libs.config import REPORT_DIR, REPORT_FILE
from libs.data_utils import get_campaign_summary, load_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def generate_report() -> None:
    master_df, decomposed_df, _ = load_data()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    html_body = "<h1>🚀 販促需要分析 エグゼクティブ・サマリー</h1>"

    for item in master_df.to_dicts():
        item_id, item_name = item["item_id"], item["item_name"]
        logger.info(f"Adding: {item_name}")

        item_decomposed_df = decomposed_df.filter(pl.col("item_id") == item_id)
        campaign_summary_df = get_campaign_summary(item_decomposed_df)

        avg_roi = campaign_summary_df["ROI (%)"].mean() if not campaign_summary_df.is_empty() else 0
        html_body += f"<h2>品目: {item_name} (平均ROI: {avg_roi:.1f}%)</h2>"

        item_pandas_df = item_decomposed_df.to_pandas()
        fig = create_decomposition_chart(item_pandas_df, f"{item_name}: 需要構造分解")
        html_body += fig.to_html(full_html=False, include_plotlyjs='cdn')

    final_html = f"<html><body style='font-family:sans-serif; margin:40px;'>{html_body}</body></html>"
    with open(REPORT_FILE, "w", encoding="utf-8") as f: f.write(final_html)
    logger.info(f"Report saved: {REPORT_FILE}")

if __name__ == "__main__": generate_report()
