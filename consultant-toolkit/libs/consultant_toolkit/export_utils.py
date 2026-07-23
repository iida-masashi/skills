"""
Export utility functions for dashboard

Provides PDF, Excel, and data export capabilities.
"""

import base64
from datetime import datetime
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go


def to_excel_bytes(
    dataframes: dict[str, pd.DataFrame], sheet_names: list[str] | None = None
) -> bytes:
    """
    複数のDataFrameをExcelファイル（bytes）に変換

    Args:
        dataframes: {sheet_name: DataFrame} の辞書
        sheet_names: シート名のリスト（Noneの場合は dataframes のキーを使用）

    Returns:
        bytes: Excelファイルのバイナリデータ

    Example:
        >>> dfs = {"Metrics": df_metrics, "Historical": df_history}
        >>> excel_bytes = to_excel_bytes(dfs)
    """
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if sheet_names:
            for sheet_name, df_key in zip(sheet_names, dataframes.keys(), strict=False):
                dataframes[df_key].to_excel(writer, sheet_name=sheet_name, index=False)
        else:
            for sheet_name, df in dataframes.items():
                # Excel sheet name limit: 31 characters
                safe_sheet_name = sheet_name[:31]
                df.to_excel(writer, sheet_name=safe_sheet_name, index=False)

    return output.getvalue()


def plotly_to_image_bytes(
    fig: go.Figure,
    format: str = "png",
    width: int = 1920,
    height: int = 1080,
    scale: int = 2,
) -> bytes:
    """
    Plotly図をPNG/SVGバイト列に変換

    Args:
        fig: Plotly Figure
        format: 'png' or 'svg'
        width: 画像幅
        height: 画像高さ
        scale: 解像度スケール（2 = 2x）

    Returns:
        bytes: 画像バイナリデータ
    """
    try:
        if format == "svg":
            img_bytes = fig.to_image(format="svg", width=width, height=height)
        else:
            img_bytes = fig.to_image(
                format="png", width=width, height=height, scale=scale
            )
        return img_bytes
    except (ValueError, OSError):
        # Fallback to HTML if image conversion fails (e.g. kaleido not installed)
        return fig.to_html().encode("utf-8")


def generate_pdf_report(
    company_name: str,
    ticker: str,
    metrics_data: pd.DataFrame,
    charts: list[go.Figure],
    analysis_text: str | None = None,
) -> bytes:
    """
    PDF分析レポートを生成（簡易版）

    Args:
        company_name: 企業名
        ticker: ティッカーシンボル
        metrics_data: メトリクスDataFrame
        charts: Plotly図のリスト
        analysis_text: AI分析テキスト

    Returns:
        bytes: PDFバイナリデータ

    Note:
        本格的なPDF生成にはreportlabが必要。
        この簡易版はHTMLベースの代替案を提供。
    """
    try:
        from io import StringIO

        from weasyprint import HTML

        # HTMLレポート生成
        html = StringIO()
        html.write(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Arial', sans-serif;
                    margin: 40px;
                }}
                h1 {{
                    color: #e00078;
                    border-bottom: 3px solid #e00078;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #333;
                    margin-top: 30px;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 20px 0;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                th {{
                    background-color: #e00078;
                    color: white;
                }}
                .metric {{
                    background-color: #f9f9f9;
                    padding: 15px;
                    margin: 10px 0;
                    border-left: 4px solid #e00078;
                }}
            </style>
        </head>
        <body>
            <h1>財務・SCM分析レポート</h1>
            <div class="metric">
                <strong>企業名:</strong> {company_name}<br>
                <strong>ティッカー:</strong> {ticker}<br>
                <strong>生成日時:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            </div>

            <h2>財務メトリクス</h2>
            {metrics_data.to_html(index=False, classes="data-table")}
        """)

        if analysis_text:
            analysis_html = analysis_text.replace("\n", "<br>")
            html.write(f"""
            <h2>AI分析</h2>
            <div class="metric">
                {analysis_html}
            </div>
            """)

        html.write("""
        </body>
        </html>
        """)

        # WeasyPrint で PDF 生成
        pdf_bytes = HTML(string=html.getvalue()).write_pdf()
        return pdf_bytes

    except ImportError:
        # WeasyPrint がない場合は HTML をそのまま返す
        html_content = f"""
        <html>
        <head><title>{company_name} Analysis Report</title></head>
        <body>
            <h1>{company_name} ({ticker}) - Analysis Report</h1>
            <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            {metrics_data.to_html()}
        </body>
        </html>
        """
        return html_content.encode("utf-8")


def generate_markdown_report(
    company_name: str,
    ticker: str,
    metrics_data: pd.DataFrame,
    analysis_text: str | None = None,
) -> str:
    """
    Markdown形式のレポートを生成

    Args:
        company_name: 企業名
        ticker: ティッカーシンボル
        metrics_data: メトリクスDataFrame
        analysis_text: AI分析テキスト

    Returns:
        str: Markdownテキスト
    """
    report = f"""# {company_name} ({ticker}) - 財務・SCM分析レポート

**生成日時**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## 財務メトリクス

{metrics_data.to_markdown(index=False)}

"""

    if analysis_text:
        report += f"""
---

## AI分析

{analysis_text}
"""

    return report


def create_download_link(
    data: bytes, filename: str, mime_type: str, link_text: str = "Download"
) -> str:
    """
    ダウンロードリンクHTMLを生成

    Args:
        data: バイナリデータ
        filename: ファイル名
        mime_type: MIMEタイプ
        link_text: リンクテキスト

    Returns:
        str: HTML download link
    """
    b64 = base64.b64encode(data).decode()
    return (
        f'<a href="data:{mime_type};base64,{b64}" download="{filename}">{link_text}</a>'
    )
