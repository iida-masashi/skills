"""
Excel utilities for Consultant Toolkit.
Handles loading Excel data using Polars for high-performance SCM/Finance operations.
"""

from pathlib import Path

import polars as pl


def convert_excel_to_csv(
    excel_path: str | Path,
    csv_out_path: str | Path | None = None,
    sheet_name: str | None = None,
) -> pl.DataFrame:
    """
    Excelファイルを読み込み、必要に応じてCSVに保存し、Polars DataFrameとして返す。

    Args:
        excel_path: 入力となるExcelファイルのパス
        csv_out_path: 出力先CSVのパス（省略可能）
        sheet_name: 読み込むシート名（省略可能）

    Returns:
        読み込んだデータの Polars DataFrame
    """
    input_path = Path(excel_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Excel file not found: {input_path}")

    print(f"🔄 Reading Excel: {input_path}")

    # 読み込み (calamineエンジンを利用)
    try:
        # polars >= 0.19.0 では source 引数に渡す
        if sheet_name:
            df = pl.read_excel(
                source=input_path, sheet_name=sheet_name, engine="calamine"
            )
        else:
            df = pl.read_excel(source=input_path, engine="calamine")
    except (OSError, ModuleNotFoundError, ValueError) as e:
        raise RuntimeError(f"Failed to read Excel file '{input_path}'. Error: {e}") from e

    # CSVとして保存
    if csv_out_path:
        out_path = Path(csv_out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"💾 Saving to CSV: {out_path}")
        df.write_csv(out_path)

    return df
