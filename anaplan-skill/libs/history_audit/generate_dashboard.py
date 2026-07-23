from libs.common.audit_html import AuditDashboardGenerator

"""
Generate HTML Dashboard from Anaplan History Audit CSV Files
"""
import sys
from pathlib import Path

import polars as pl


def main():
    """Main execution"""
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
    else:
        # Find the most recent summary CSV
        audit_folder = Path("./HistoryAudit")
        csv_files = list(audit_folder.glob("*all_summary.csv"))

        if not csv_files:
            print("No summary CSV files found in HistoryAudit folder")
            print("Usage: python generate_dashboard.py [path_to_csv]")
            return

        csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
        print(f"Using most recent CSV: {csv_path.name}")

    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return

    generator = AuditDashboardGenerator(pl.read_csv(csv_path), csv_path)
    dashboard_path = generator.generate()

    print("\nSuccess!")
    print("Open the dashboard in your browser:")
    print(f"   {dashboard_path.absolute()}")


if __name__ == "__main__":
    main()
