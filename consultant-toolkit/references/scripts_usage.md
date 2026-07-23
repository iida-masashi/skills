## Available Scripts

The following scripts are available in the `scripts/` directory.

### Prerequisites

```bash
# Install the package (editable mode)
pip install -e .

# Or with uv
uv pip install -e .
```

### Dashboards (Streamlit)

- **Financial & SCM**: `streamlit run scripts/app_finance.py`
- **ERP PMO (Backlog)**: `streamlit run scripts/app_backlog.py`
- **Global Market**: `streamlit run scripts/app_market_watch.py`
- **Marketing & Sentiment**: `streamlit run scripts/app_marketing.py`

### CLI Tools

- **Deep Analysis**: `python scripts/analyze_company_cli.py --target <ticker> --auto-peers`
- **Finance Data**: `python scripts/fetch_finance_data.py --ticker <ticker> [--trends]`
- **Excel to CSV**: `python scripts/excel_to_csv_cli.py -i <input.xlsx> -o <output.csv>`
- **RFP Package**: `python scripts/generate_rfp_package.py --industry medical`
- **Weekly Report**: `python scripts/generate_report.py`
- **Data Analyzer**: `python scripts/data_analyzer.py --input <csv_path>`

### Environment Variables

Set in `.env` at the project root:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here  # Optional (fallback)
```
