---
name: consultant-toolkit
description: A comprehensive toolkit for management consultants to automate tedious tasks such as financial data retrieval, AI-powered SCM/Financial dashboards, and ERP PMO automation.
---

# Consultant Toolkit

This skill provides a suite of tools for management consultants to streamline analysis and reporting workflows.

## Key Capabilities

- **Financial & SCM Intelligence**: Real-time data retrieval and interactive dashboards (ROIC tree, Strategy proposal).
- **Deep-Dive Company Analysis**: Automated "Consultant Quality" report generation against competitors.
- **ERP PMO Automation**: Project structure generation, issue log templates, and automated backlog reporting for ERP implementation.

## Architecture

```
libs/consultant_toolkit/     # Core library (pip install -e .)
  constants.py               # Single source of truth for all constants
  financial_metrics.py       # ROIC, CCC, DIO/DSO/DPO
  finance_data.py            # yfinance data fetching
  ai_analytics.py            # Prophet, anomaly detection, LLM query
  peer_suggestion.py         # 3-tier peer suggestion engine
  company_search.py          # 829+ company name -> ticker mapping
  segment_analysis.py        # Business segment analysis
  simulation_logic.py        # What-If simulation
  config/                    # YAML/JSON configuration
  ui_components/             # Streamlit-only UI renderers

scripts/                     # Entry points
  app_finance.py             # Financial & SCM dashboard
  app_backlog.py             # ERP PMO dashboard
  app_market_watch.py        # Market analysis dashboard
  app_marketing.py           # Brand reputation dashboard
  analyze_company_cli.py     # CLI company analysis
  fetch_finance_data.py      # CLI data fetcher
```

## Progressive Disclosure (When to use what)
To keep the initial context window clean and fast, detailed CLI usage instructions and setup are stored in external reference files. **DO NOT GUESS CLI COMMANDS.**

- **If you need to run a dashboard, a deep analysis script, or an ERP PMO tool**, you MUST first read `references/scripts_usage.md` to get the exact command and arguments.
- **Example**: `read_file("Skills/consultant-toolkit/references/scripts_usage.md")`
