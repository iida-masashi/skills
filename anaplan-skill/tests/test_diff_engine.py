import polars as pl

from libs.model_analyzer.diff_engine import compare_dataframes


def test_compare_dataframes():
    base_df = pl.DataFrame([
        {"id": "1", "name": "A", "val": 10},
        {"id": "2", "name": "B", "val": 20}, # Modified
        {"id": "3", "name": "C", "val": 30}, # Removed
    ])
    comp_df = pl.DataFrame([
        {"id": "1", "name": "A", "val": 10}, # Unchanged
        {"id": "2", "name": "B", "val": 25}, # Modified
        {"id": "4", "name": "D", "val": 40}, # Added
    ])

    diff_df = compare_dataframes(
        base_df, comp_df,
        join_keys=["name"],
        compare_cols=["val"]
    )

    assert diff_df.height == 4
    assert "Diff_Status" in diff_df.columns

    # Assert Status
    status_map = dict(zip(diff_df["name"].to_list(), diff_df["Diff_Status"].to_list(), strict=True))
    assert status_map["A"] == "Unchanged"
    assert status_map["B"] == "Modified"
    assert status_map["C"] == "Removed"
    assert status_map["D"] == "Added"
