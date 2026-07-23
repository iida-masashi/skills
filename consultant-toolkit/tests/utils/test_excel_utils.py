from pathlib import Path

import polars as pl
import pytest
from consultant_toolkit.excel_utils import convert_excel_to_csv


def test_convert_excel_to_csv(tmp_path: Path):
    # Setup: Create a dummy Excel file
    excel_path = tmp_path / "dummy.xlsx"
    csv_path = tmp_path / "output.csv"

    # Create sample DataFrame
    df_original = pl.DataFrame(
        {"ID": [1, 2, 3], "Category": ["A", "B", "C"], "Value": [10.5, 20.1, 30.0]}
    )

    # Save as Excel (needs xlsxwriter)
    df_original.write_excel(excel_path)

    # Execution: Convert Excel to CSV
    df_result = convert_excel_to_csv(excel_path=excel_path, csv_out_path=csv_path)

    # Verification
    assert df_result.shape == (3, 3)
    assert "Category" in df_result.columns
    assert csv_path.exists()

    # Read back CSV to check if it matches
    df_csv = pl.read_csv(csv_path)
    assert df_csv.shape == (3, 3)
    assert df_csv["Category"].to_list() == ["A", "B", "C"]


def test_convert_excel_to_csv_file_not_found():
    with pytest.raises(FileNotFoundError):
        convert_excel_to_csv("non_existent_file.xlsx")
