import polars as pl


def compare_dataframes(base_df: pl.DataFrame, comp_df: pl.DataFrame, join_keys: list[str], compare_cols: list[str]) -> pl.DataFrame:
    """
    2つのPolars DataFrameを結合キーで比較し、追加・削除・変更の差分を計算する。
    """
    if base_df.is_empty() and comp_df.is_empty():
        return pl.DataFrame()

    # join_keysとcompare_colsのみに絞る
    b_cols = [c for c in base_df.columns if c in join_keys + compare_cols]
    c_cols = [c for c in comp_df.columns if c in join_keys + compare_cols]

    b_df = base_df.select(b_cols).with_columns(pl.lit("BASE").alias("_source"))
    c_df = comp_df.select(c_cols).with_columns(pl.lit("COMP").alias("_source"))

    # Outer join
    joined = b_df.join(c_df, on=join_keys, how="full", suffix="_comp")

    # Coalesce join keys
    for key in join_keys:
        if f"{key}_comp" in joined.columns:
            joined = joined.with_columns(
                pl.coalesce(pl.col(key), pl.col(f"{key}_comp")).alias(key)
            ).drop(f"{key}_comp")

    # 差分ステータス判定用の式を構築
    # how="full" in polars gives nulls for missing rows in respective sides.
    # In newer polars, full join keys are coalesced. But we need to know where it came from.
    # We can check `_source` and `_source_comp`.

    status_expr = (
        pl.when(pl.col("_source").is_not_null() & pl.col("_source_comp").is_null())
        .then(pl.lit("Removed"))
        .when(pl.col("_source").is_null() & pl.col("_source_comp").is_not_null())
        .then(pl.lit("Added"))
        .otherwise(pl.lit("Unchanged"))
    )

    diff_df = joined.with_columns(status_expr.alias("Diff_Status"))

    # Check for modifications
    if compare_cols:
        mod_conditions = []
        for col in compare_cols:
            if col in b_cols and col in c_cols:
                comp_col = f"{col}_comp"
                # Both not null but different
                mod_conditions.append(
                    (pl.col("Diff_Status") == "Unchanged") &
                    (pl.col(col) != pl.col(comp_col))
                )

        if mod_conditions:
            combined_mod = mod_conditions[0]
            for cond in mod_conditions[1:]:
                combined_mod = combined_mod | cond

            diff_df = diff_df.with_columns(
                pl.when(combined_mod)
                .then(pl.lit("Modified"))
                .otherwise(pl.col("Diff_Status"))
                .alias("Diff_Status")
            )

    # クリーンアップとソート
    if "_source" in diff_df.columns:
        diff_df = diff_df.drop(["_source"])
    if "_source_comp" in diff_df.columns:
        diff_df = diff_df.drop(["_source_comp"])

    if join_keys:
        diff_df = diff_df.sort(join_keys)

    return diff_df
