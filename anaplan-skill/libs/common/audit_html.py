import logging
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)

class AuditDashboardGenerator:
    """Generates HTML dashboard from audit results"""

    def __init__(self, df: pl.DataFrame, csv_path: Path | None = None):
        self.df = df
        self.csv_path = csv_path

    def generate(self, output_path: Path, timestamp: str | None = None, failed_models: list | None = None) -> Path:
        """Generate HTML dashboard with statistics"""
        if timestamp is None:
            timestamp = datetime.now(UTC).strftime('%Y%m%d%H%M')

        if self.df is not None and not self.df.is_empty():
            total_users = len(self.df)
            total_actions = self.df["ID"].sum()
            models = self.df["Model"].unique().to_list()
        else:
            total_users = 0
            total_actions = 0
            models = []

        html_content = self._generate_html(timestamp, total_users, total_actions, models, failed_models or [])

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Dashboard generated: {output_path}")
        return output_path

    def _generate_html(self, timestamp: str, total_users: int, total_actions: int, models: list, failed_models: list) -> str:
        """Generate complete HTML content"""
        file_info_html = f'<div class="file-info">データソース: {self.csv_path.name}</div>' if self.csv_path else ''

        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Anaplan History Audit Dashboard - {timestamp}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px; min-height: 100vh;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{
            background: white; padding: 30px; border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;
        }}
        .header h1 {{ color: #333; font-size: 2em; margin-bottom: 10px; }}
        .header .subtitle {{ color: #666; font-size: 1.1em; }}
        .stats-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px; margin-bottom: 20px;
        }}
        .stat-card {{
            background: white; padding: 25px; border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.3s ease;
        }}
        .stat-card:hover {{ transform: translateY(-5px); box-shadow: 0 6px 12px rgba(0,0,0,0.15); }}
        .stat-card .label {{
            color: #666; font-size: 0.9em; text-transform: uppercase;
            letter-spacing: 1px; margin-bottom: 10px;
        }}
        .stat-card .value {{ color: #333; font-size: 2.5em; font-weight: bold; }}
        .stat-card.purple .value {{ color: #667eea; }}
        .stat-card.green .value {{ color: #48bb78; }}
        .stat-card.blue .value {{ color: #4299e1; }}
        .table-container {{
            background: white; padding: 30px; border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); overflow-x: auto; margin-bottom: 20px;
        }}
        .table-container h2 {{ color: #333; margin-bottom: 20px; font-size: 1.5em; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 15px; text-align: left; font-weight: 600;
        }}
        td {{ padding: 12px 15px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f8f9fa; }}
        .model-badge {{
            display: inline-block; padding: 5px 12px; border-radius: 20px;
            font-size: 0.85em; font-weight: 600; background: #667eea; color: white;
        }}
        .activity-bar {{
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            height: 20px; border-radius: 10px; transition: width 0.3s ease;
        }}
        .activity-cell {{ min-width: 150px; }}
        .error-badge {{
            display: inline-block; padding: 5px 12px; border-radius: 20px;
            font-size: 0.85em; font-weight: 600; background: #e53e3e; color: white;
        }}
        .error-container {{
            background: #fff5f5; border-left: 4px solid #e53e3e;
            padding: 15px; margin-bottom: 10px; border-radius: 5px;
        }}
        .error-title {{
            font-weight: 600; color: #e53e3e; margin-bottom: 5px;
            display: flex; align-items: center; gap: 10px;
        }}
        .error-message {{
            color: #666; font-size: 0.9em; margin-top: 5px;
            font-family: monospace; background: white;
            padding: 10px; border-radius: 3px;
        }}
        .alert-icon {{ font-size: 1.2em; }}
        .file-info {{
            background: rgba(0,0,0,0.05);
            padding: 10px 15px;
            border-radius: 5px;
            color: #666;
            margin-top: 10px;
            font-size: 0.9em;
        }}
        .footer {{ text-align: center; color: white; margin-top: 20px; padding: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Anaplan History Audit Dashboard</h1>
            <div class="subtitle">Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}</div>
            {file_info_html}
        </div>
        <div class="stats-grid">
            <div class="stat-card purple">
                <div class="label">Total Users</div>
                <div class="value">{total_users:,}</div>
            </div>
            <div class="stat-card green">
                <div class="label">Total Actions</div>
                <div class="value">{int(total_actions):,}</div>
            </div>
            <div class="stat-card blue">
                <div class="label">Models</div>
                <div class="value">{len(models)}</div>
            </div>
        </div>
        {self._generate_failed_models_section(failed_models)}
        <div class="table-container">
            <h2>Model Summary</h2>
            {self._generate_model_summary_table()}
        </div>
        <div class="table-container">
            <h2>Top 20 Active Users</h2>
            {self._generate_user_activity_table()}
        </div>
        <div class="footer">
            <p>Anaplan History Audit System | Optimized with Chunked Processing</p>
            <p style="margin-top: 5px; font-size: 0.9em;">Powered by Polars & Python (Gemini 3 Architecture)</p>
        </div>
    </div>
</body>
</html>"""

    def _generate_failed_models_section(self, failed_models: list) -> str:
        """Generate failed models section"""
        if not failed_models:
            return ""

        error_items = []
        for failed in failed_models:
            model_name = failed.get('model_name', 'Unknown')
            error_type = failed.get('error_type', 'Error')
            error_msg = failed.get('error', 'Unknown error')

            error_items.append(f"""
            <div class="error-container">
                <div class="error-title">
                    <span class="alert-icon">&#9888;</span>
                    <span class="error-badge">{error_type}</span>
                    <span>{model_name}</span>
                </div>
                <div class="error-message">{error_msg}</div>
            </div>
            """)

        return f"""
        <div class="table-container" style="background: #fffaf0; border-left: 4px solid #e53e3e;">
            <h2 style="color: #e53e3e;">Failed Models ({len(failed_models)})</h2>
            {''.join(error_items)}
        </div>
        """

    def _generate_model_summary_table(self) -> str:
        """Generate model summary table"""
        if self.df is None or self.df.is_empty():
            return "<p style='color: #999; text-align: center; padding: 20px;'>No successful models to display</p>"

        user_col = "User" if "User" in self.df.columns else self.df.columns[0]
        # Polars way to aggregate
        summary = self.df.group_by("Model").agg([
            pl.col("ID").sum().alias("Total Actions"),
            pl.col(user_col).count().alias("Total Users")
        ])

        rows = [f"""<tr>
            <td><span class="model-badge">{row['Model']}</span></td>
            <td>{int(row['Total Actions']):,}</td>
            <td>{int(row['Total Users']):,}</td>
        </tr>""" for row in summary.to_dicts()]

        return f"""<table>
            <thead><tr><th>Model</th><th>Actions</th><th>Users</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>"""

    def _generate_user_activity_table(self) -> str:
        """Generate user activity table"""
        if self.df is None or self.df.is_empty():
            return "<p style='color: #999; text-align: center; padding: 20px;'>No user activity data to display</p>"

        # Polars way to get top N
        top_users = self.df.sort("ID", descending=True).head(20)
        max_actions = top_users["ID"].max() if not top_users.is_empty() else 1
        user_col = "User" if "User" in top_users.columns else top_users.columns[0]

        rows = []
        for row in top_users.to_dicts():
            user = row.get(user_col, "N/A")
            actions = int(row["ID"])
            first_name = row.get("First Name", "N/A")
            last_name = row.get("Last Name", "N/A")
            model = row.get("Model", "N/A")
            bar_width = (actions / max_actions * 100) if max_actions > 0 else 0

            name_str = f"{first_name} {last_name}" if first_name != "N/A" or last_name != "N/A" else "N/A"
            rows.append(f"""<tr>
                <td>{user}</td>
                <td>{name_str}</td>
                <td><span class="model-badge">{model}</span></td>
                <td>{actions:,}</td>
                <td class="activity-cell">
                    <div class="activity-bar" style="width: {bar_width}%;"></div>
                </td>
            </tr>""")

        return f"""<table>
            <thead><tr><th>User</th><th>Name</th><th>Model</th><th>Actions</th><th>Activity</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>"""
