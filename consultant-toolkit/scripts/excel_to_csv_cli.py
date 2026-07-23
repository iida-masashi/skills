"""
CLI tool for converting Excel files to CSV.
Useful for SCM data processing and ingestion pipelines.
"""

import argparse
import sys

from consultant_toolkit.excel_utils import convert_excel_to_csv


def main():
    parser = argparse.ArgumentParser(
        description="Convert Excel files to CSV using Polars."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=str,
        help="Path to input Excel file (.xlsx, .xls)",
    )
    parser.add_argument(
        "-o", "--output", required=True, type=str, help="Path to output CSV file"
    )
    parser.add_argument(
        "-s",
        "--sheet",
        type=str,
        default=None,
        help="Name of the sheet to convert (optional)",
    )

    args = parser.parse_args()

    try:
        df = convert_excel_to_csv(
            excel_path=args.input, csv_out_path=args.output, sheet_name=args.sheet
        )
        print(f"✅ Conversion complete. Data shape: {df.shape}")
        print(f"📊 Preview:\n{df.head(3)}")
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
