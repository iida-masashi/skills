import polars as pl
import pytest
from libs.model_analyzer.user_activity import (
    create_user_app_page_matrix,
    parse_activity_log,
    generate_synthesized_app_page_log,
)


def test_create_user_app_page_matrix_count():
    df = pl.DataFrame({
        "userId": ["user1_id", "user1_id", "user2_id"],
        "user": ["user1@example.com", "user1@example.com", "user2@example.com"],
        "appId": ["APP01", "APP01", "APP02"],
        "appName": ["Sales App", "Sales App", "Finance App"],
        "pageId": ["PG01", "PG02", "PG01"],
        "pageName": ["Revenue Page", "Discount Page", "Budget Page"],
        "timestamp": ["2026-08-01 10:00:00", "2026-08-02 11:00:00", "2026-08-03 12:00:00"],
        "action": ["Open Page", "Edit Cell", "Open Page"]
    })

    # name_and_id format
    pivot = create_user_app_page_matrix(df, col_format="name_and_id", value_mode="count")
    assert not pivot.is_empty()
    assert "User (UserID / Email)" in pivot.columns
    cols = pivot.columns
    assert any("Sales App" in c and "Revenue Page" in c for c in cols)

    # name_only format
    pivot_name = create_user_app_page_matrix(df, col_format="name_only", value_mode="count")
    assert "Sales App > Revenue Page" in pivot_name.columns
    assert "Finance App > Budget Page" in pivot_name.columns

    # id_only format
    pivot_id = create_user_app_page_matrix(df, col_format="id_only", value_mode="count")
    assert "APP01 / PG01" in pivot_id.columns
    assert "APP02 / PG01" in pivot_id.columns


def test_create_user_app_page_matrix_flag():
    df = pl.DataFrame({
        "userId": ["u1", "u2"],
        "user": ["u1@test.com", "u2@test.com"],
        "appId": ["A1", "A2"],
        "appName": ["App1", "App2"],
        "pageId": ["P1", "P2"],
        "pageName": ["Page1", "Page2"],
    })
    pivot = create_user_app_page_matrix(df, col_format="name_only", value_mode="flag")
    assert not pivot.is_empty()
    u1_row = pivot.filter(pl.col("User (UserID / Email)").str.contains("u1@test.com"))
    assert u1_row["App1 > Page1"][0] == "✅"
    assert u1_row["App2 > Page2"][0] == ""


def test_parse_activity_log_app_page_csv():
    csv_data = """userId,email,appId,appName,pageId,pageName,timestamp,action
u123,user1@test.com,APP01,Demand App,PG101,Forecast Grid,2026-08-10 10:00:00,View
u456,user2@test.com,APP02,Supply App,PG201,Order Matrix,2026-08-11 11:00:00,Edit
"""
    df = parse_activity_log(csv_data)
    assert df.height == 2
    assert "userId" in df.columns
    assert "appId" in df.columns
    assert "appName" in df.columns
    assert "pageId" in df.columns
    assert "pageName" in df.columns
    assert df["appName"][0] == "Demand App"
    assert df["pageName"][0] == "Forecast Grid"


def test_generate_synthesized_app_page_log():
    users_df = pl.DataFrame({
        "userId": ["u1", "u2"],
        "email": ["userA@test.com", "userB@test.com"]
    })
    modules_df = pl.DataFrame({"name": ["Module 1", "Module 2"]})

    log_df = generate_synthesized_app_page_log(users_df, modules_df, days=30, seed=123)
    assert not log_df.is_empty()
    assert set(log_df.columns) == {"userId", "user", "appId", "appName", "pageId", "pageName", "timestamp", "action"}
    assert all(u in ["userA@test.com", "userB@test.com"] for u in log_df["user"].unique())
