from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def generate_weekly_report(
    input_file: str | Path = "templates/ERP_Project_Issue_Log_Template.xlsx",
    output_dir: str | Path = "reports",
) -> None:
    """
    Generates a weekly project status report in Markdown format from the Issue Log Excel file.
    """
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: Input file '{input_file}' not found.")
        return

    try:
        df = pd.read_excel(input_path, sheet_name="Issue Log")
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    # Basic Stats
    total_issues = len(df)
    open_issues = df[df["Status"] == "Open"].shape[0]
    resolved_issues = df[df["Status"] == "Resolved"].shape[0]
    closed_issues = df[df["Status"] == "Closed"].shape[0]
    in_progress_issues = df[df["Status"] == "In Progress"].shape[0]

    # Critical & High Priority Open Issues
    critical_high_df = df[
        (df["Status"].isin(["Open", "In Progress"])) & (df["Priority"].isin(["Critical", "High"]))
    ]

    # Delayed Issues
    today = pd.Timestamp.today()
    delayed_df = df[(df["Status"].isin(["Open", "In Progress"])) & (df["Due Date"] < today)]

    # Generate Report Content
    now_utc = datetime.now(UTC)
    report_date = now_utc.strftime("%Y-%m-%d")
    report_content = f"""# Project Weekly Status Report ({report_date})

## 1. Executive Summary
- **Total Issues Tracked:** {total_issues}
- **Open Issues:** {open_issues}
- **In Progress:** {in_progress_issues}
- **Resolved/Closed:** {resolved_issues + closed_issues}

## 2. Key Attention Items (Critical/High Priority)
The following issues require immediate attention:

| Issue ID | Description | Priority | Owner | Due Date |
| :--- | :--- | :--- | :--- | :--- |
"""

    if not critical_high_df.empty:
        for _index, row in critical_high_df.iterrows():
            due_date = (
                row["Due Date"].strftime("%Y-%m-%d") if pd.notnull(row["Due Date"]) else "N/A"
            )
            report_content += f"| {row['Issue ID']} | {row['Description']} | **{row['Priority']}** | {row['Owner']} | {due_date} |\n"
    else:
        report_content += "No critical or high priority open issues.\n"

    report_content += """
## 3. Delayed Tasks
The following tasks are past their due date:

| Issue ID | Description | Owner | Due Date |
| :--- | :--- | :--- | :--- |
"""

    if not delayed_df.empty:
        for _index, row in delayed_df.iterrows():
            due_date = (
                row["Due Date"].strftime("%Y-%m-%d") if pd.notnull(row["Due Date"]) else "N/A"
            )
            report_content += (
                f"| {row['Issue ID']} | {row['Description']} | {row['Owner']} | **{due_date}** |\n"
            )
    else:
        report_content += "No delayed tasks.\n"

    # Save Report
    out_dir_path = Path(output_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    output_filename = f"Weekly_Report_{now_utc.strftime('%Y%m%d')}.md"
    output_path = out_dir_path / output_filename

    output_path.write_text(report_content, encoding="utf-8")

    print(f"Weekly Report generated successfully at: {output_path.resolve()}")


if __name__ == "__main__":
    # Adjust input path if running from root or scripts dir
    default_input_path = Path("templates/ERP_Project_Issue_Log_Template.xlsx")
    alt_input_path = Path("../templates/ERP_Project_Issue_Log_Template.xlsx")
    if not default_input_path.exists() and alt_input_path.exists():
        default_input_path = alt_input_path

    generate_weekly_report(input_file=default_input_path)
