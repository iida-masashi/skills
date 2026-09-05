from __future__ import annotations

import io
import logging
from datetime import UTC, datetime, timedelta
import random
from typing import Any, Literal
import polars as pl
import requests

from libs.model_analyzer.analyzer import AnaplanConfig, AnaplanAuthenticator

logger = logging.getLogger(__name__)


def fetch_all_workspaces(config: AnaplanConfig) -> list[dict[str, str]]:
    """ユーザーが所属するワークスペース一覧を取得する"""
    authenticator = AnaplanAuthenticator(config)
    token = authenticator.get_token()
    headers = {"Authorization": f"AnaplanAuthToken {token}", "Accept": "application/json"}
    try:
        res = requests.get("https://api.anaplan.com/2/0/workspaces", headers=headers, timeout=20)
        if res.status_code == 200:
            return res.json().get("workspaces", [])
    except Exception as e:
        logger.warning(f"Failed to fetch workspaces: {e}")
    return []


def fetch_all_models(config: AnaplanConfig) -> list[dict[str, Any]]:
    """ユーザーが所属する全モデル一覧を取得する"""
    authenticator = AnaplanAuthenticator(config)
    token = authenticator.get_token()
    headers = {"Authorization": f"AnaplanAuthToken {token}", "Accept": "application/json"}
    try:
        res = requests.get("https://api.anaplan.com/2/0/models", headers=headers, timeout=20)
        if res.status_code == 200:
            return res.json().get("models", [])
    except Exception as e:
        logger.warning(f"Failed to fetch models: {e}")
    return []


def fetch_modules_for_model(config: AnaplanConfig, model_id: str) -> list[dict[str, Any]]:
    """指定されたモデルIDのモジュール一覧を取得する"""
    authenticator = AnaplanAuthenticator(config)
    token = authenticator.get_token()
    headers = {"Authorization": f"AnaplanAuthToken {token}", "Accept": "application/json"}
    try:
        res = requests.get(f"https://api.anaplan.com/2/0/models/{model_id}/modules", headers=headers, timeout=20)
        if res.status_code == 200:
            return res.json().get("modules", [])
    except Exception as e:
        logger.warning(f"Failed to fetch modules for model {model_id}: {e}")
    return []


def fetch_tenant_active_users(config: AnaplanConfig, days_limit: int = 30) -> pl.DataFrame:
    """Anaplan API (/2/0/users) から過去指定日数以内にログインしたユーザーを取得する"""
    authenticator = AnaplanAuthenticator(config)
    token = authenticator.get_token()
    headers = {"Authorization": f"AnaplanAuthToken {token}", "Accept": "application/json"}

    all_users: list[dict[str, Any]] = []
    offset = 0
    limit = 100

    while True:
        try:
            res = requests.get(
                "https://api.anaplan.com/2/0/users",
                headers=headers,
                params={"limit": limit, "offset": offset},
                timeout=20
            )
            if res.status_code != 200:
                break
            users = res.json().get("users", [])
            if not users:
                break
            all_users.extend(users)
            if len(users) < limit:
                break
            offset += limit
        except Exception:
            break

    if not all_users:
        return pl.DataFrame(schema={
            "userId": pl.Utf8, "email": pl.Utf8, "name": pl.Utf8, "lastLoginDate": pl.Utf8, "active": pl.Boolean
        })

    rows = []
    cutoff = datetime.now(UTC) - timedelta(days=days_limit)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    for u in all_users:
        last_login = u.get("lastLoginDate")
        first_name = u.get("firstName", "") or ""
        last_name = u.get("lastName", "") or ""
        name = f"{first_name} {last_name}".strip() or u.get("email", "")
        rows.append({
            "userId": u.get("id", ""),
            "email": u.get("email", ""),
            "name": name,
            "lastLoginDate": last_login,
            "active": u.get("active", True)
        })

    df = pl.DataFrame(rows)
    return df.sort("lastLoginDate", descending=True, nulls_last=True)


def parse_activity_log(file_content: bytes | str, filename: str = "") -> pl.DataFrame:
    """アップロードされた監査ログまたは履歴TSV/CSVをパースし、
    [userId, user, appId, appName, pageId, pageName, timestamp, action] の標準スキーマに変換する"""
    if isinstance(file_content, str):
        buf = io.BytesIO(file_content.encode("utf-8"))
    else:
        buf = io.BytesIO(file_content)

    separator = "\t" if filename.endswith(".tsv") else ","
    try:
        raw_df = pl.read_csv(buf, separator=separator, infer_schema_length=5000, ignore_errors=True)
    except Exception:
        buf.seek(0)
        raw_df = pl.read_csv(buf, separator=",", infer_schema_length=5000, ignore_errors=True)

    cols = {c.lower(): c for c in raw_df.columns}

    # ユーザー列判定
    uid_col = cols.get("userid") or cols.get("user_id") or cols.get("principalid") or cols.get("principal_id")
    email_col = cols.get("email") or cols.get("user_email") or cols.get("user") or cols.get("username")
    
    if not uid_col and not email_col:
        return pl.DataFrame(schema={
            "userId": pl.Utf8, "user": pl.Utf8, "appId": pl.Utf8, "appName": pl.Utf8,
            "pageId": pl.Utf8, "pageName": pl.Utf8, "timestamp": pl.Utf8, "action": pl.Utf8
        })

    # App 列判定
    app_id_col = cols.get("appid") or cols.get("app_id") or cols.get("applicationid") or cols.get("application_id")
    app_name_col = cols.get("appname") or cols.get("app_name") or cols.get("app") or cols.get("application")

    # Page 列判定
    page_id_col = cols.get("pageid") or cols.get("page_id") or cols.get("viewid") or cols.get("screenid")
    page_name_col = cols.get("pagename") or cols.get("page_name") or cols.get("page") or cols.get("screen") or cols.get("module") or cols.get("dashboard") or cols.get("object")

    time_col = cols.get("timestamp") or cols.get("date") or cols.get("time") or cols.get("lastlogindate")
    action_col = cols.get("action") or cols.get("event") or cols.get("type")

    select_exprs = []
    
    # User ID & Email
    if uid_col:
        select_exprs.append(pl.col(uid_col).cast(pl.Utf8).alias("userId"))
    elif email_col:
        select_exprs.append(pl.col(email_col).cast(pl.Utf8).alias("userId"))
    else:
        select_exprs.append(pl.lit("").alias("userId"))

    if email_col:
        select_exprs.append(pl.col(email_col).cast(pl.Utf8).alias("user"))
    elif uid_col:
        select_exprs.append(pl.col(uid_col).cast(pl.Utf8).alias("user"))
    else:
        select_exprs.append(pl.lit("").alias("user"))

    # App ID & App Name
    if app_id_col:
        select_exprs.append(pl.col(app_id_col).cast(pl.Utf8).alias("appId"))
    else:
        select_exprs.append(pl.lit("APP-001").alias("appId"))

    if app_name_col:
        select_exprs.append(pl.col(app_name_col).cast(pl.Utf8).alias("appName"))
    elif app_id_col:
        select_exprs.append(pl.col(app_id_col).cast(pl.Utf8).alias("appName"))
    else:
        select_exprs.append(pl.lit("Main Planning App").alias("appName"))

    # Page ID & Page Name
    if page_id_col:
        select_exprs.append(pl.col(page_id_col).cast(pl.Utf8).alias("pageId"))
    else:
        select_exprs.append(pl.lit("PG-001").alias("pageId"))

    if page_name_col:
        select_exprs.append(pl.col(page_name_col).cast(pl.Utf8).alias("pageName"))
    elif page_id_col:
        select_exprs.append(pl.col(page_id_col).cast(pl.Utf8).alias("pageName"))
    else:
        select_exprs.append(pl.lit("Dashboard Page").alias("pageName"))

    # Timestamp & Action
    if time_col:
        select_exprs.append(pl.col(time_col).cast(pl.Utf8).alias("timestamp"))
    else:
        select_exprs.append(pl.lit("").alias("timestamp"))

    if action_col:
        select_exprs.append(pl.col(action_col).cast(pl.Utf8).alias("action"))
    else:
        select_exprs.append(pl.lit("Open Page").alias("action"))

    df = raw_df.select(select_exprs)
    return df.filter(
        (pl.col("userId").is_not_null() & (pl.col("userId") != "")) |
        (pl.col("user").is_not_null() & (pl.col("user") != ""))
    )


def create_user_app_page_matrix(
    activity_df: pl.DataFrame,
    col_format: Literal["name_only", "name_and_id", "id_only"] = "name_and_id",
    row_format: Literal["email_and_name", "userId_only", "email_only"] = "email_and_name",
    value_mode: Literal["count", "flag", "last_access"] = "count"
) -> pl.DataFrame:
    """ユーザー×App/Page のピボットマトリックス表を生成する"""
    if activity_df.is_empty():
        return pl.DataFrame()

    # 1. ユーザー行ラベルの構築
    if row_format == "userId_only":
        user_expr = pl.col("userId").fill_null("").alias("row_user")
    elif row_format == "email_only":
        user_expr = pl.col("user").fill_null("").alias("row_user")
    else:  # email_and_name
        user_expr = pl.when(
            (pl.col("userId") != pl.col("user")) & (pl.col("userId") != "")
        ).then(
            pl.concat_str([pl.col("user"), pl.lit(" (ID: "), pl.col("userId"), pl.lit(")")])
        ).otherwise(
            pl.col("user")
        ).alias("row_user")

    # 2. 列ヘッダー（App & Page）ラベルの構築
    if col_format == "name_only":
        col_expr = pl.concat_str([pl.col("appName"), pl.lit(" > "), pl.col("pageName")]).alias("col_target")
    elif col_format == "id_only":
        col_expr = pl.concat_str([pl.col("appId"), pl.lit(" / "), pl.col("pageId")]).alias("col_target")
    else:  # name_and_id
        col_expr = pl.concat_str([
            pl.col("appName"), pl.lit(" ("), pl.col("appId"), pl.lit(") > "),
            pl.col("pageName"), pl.lit(" ("), pl.col("pageId"), pl.lit(")")
        ]).alias("col_target")

    prep_df = activity_df.with_columns([user_expr, col_expr])

    if value_mode == "count":
        agg_df = prep_df.group_by(["row_user", "col_target"]).agg(pl.len().alias("value"))
        pivot_df = agg_df.pivot(
            values="value",
            index="row_user",
            on="col_target",
            aggregate_function="first"
        ).fill_null(0)
    elif value_mode == "flag":
        agg_df = prep_df.group_by(["row_user", "col_target"]).agg(pl.lit("✅").alias("value"))
        pivot_df = agg_df.pivot(
            values="value",
            index="row_user",
            on="col_target",
            aggregate_function="first"
        ).fill_null("")
    elif value_mode == "last_access":
        if "timestamp" in prep_df.columns:
            agg_df = prep_df.group_by(["row_user", "col_target"]).agg(pl.col("timestamp").max().alias("value"))
            pivot_df = agg_df.pivot(
                values="value",
                index="row_user",
                on="col_target",
                aggregate_function="first"
            ).fill_null("-")
        else:
            return create_user_app_page_matrix(activity_df, col_format=col_format, row_format=row_format, value_mode="flag")
    else:
        return create_user_app_page_matrix(activity_df, col_format=col_format, row_format=row_format, value_mode="count")

    # 列名 'row_user' を 'User (UserID / Email)' にリネーム
    return pivot_df.rename({"row_user": "User (UserID / Email)"})


def generate_synthesized_app_page_log(
    users_df: pl.DataFrame,
    modules_df: pl.DataFrame,
    days: int = 30,
    seed: int = 42
) -> pl.DataFrame:
    """テナント実在ユーザー情報とモデル内のモジュール・画面群から、
    AppID / PageID および App名 / Page名 が付与されたアクティビティログを生成する"""
    rng = random.Random(seed)

    if users_df.is_empty():
        return pl.DataFrame(schema={
            "userId": pl.Utf8, "user": pl.Utf8, "appId": pl.Utf8, "appName": pl.Utf8,
            "pageId": pl.Utf8, "pageName": pl.Utf8, "timestamp": pl.Utf8, "action": pl.Utf8
        })

    user_rows = []
    for row in users_df.iter_rows(named=True):
        user_rows.append({
            "userId": row.get("userId") or row.get("id") or "",
            "user": row.get("email") or row.get("name") or "",
        })

    # アプリ群とページ群の構造化定義（モジュール名を取り入れつつ App/Page 構造化）
    raw_mod_names = modules_df["name"].to_list() if not modules_df.is_empty() and "name" in modules_df.columns else []
    
    apps_pages_master: list[dict[str, str]] = []

    if raw_mod_names:
        # モジュールを 3〜4 つの App に論理分割して Page を割り当て
        app_templates = [
            ("APP-SCM-01", "Supply Chain Planning App"),
            ("APP-FIN-02", "Financial & Profit Simulation"),
            ("APP-OPS-03", "Operations & Demand Review"),
            ("APP-EXEC-04", "Executive Summary Dashboard")
        ]
        for i, mod_name in enumerate(raw_mod_names):
            app_id, app_name = app_templates[i % len(app_templates)]
            page_id = f"PG-{100 + i}"
            page_name = f"{mod_name} Page"
            apps_pages_master.append({
                "appId": app_id,
                "appName": app_name,
                "pageId": page_id,
                "pageName": page_name
            })
    else:
        # デフォルトマスタ
        apps_pages_master = [
            {"appId": "APP-SCM-01", "appName": "Supply Chain Planning", "pageId": "PG-101", "pageName": "Demand Review & Forecast"},
            {"appId": "APP-SCM-01", "appName": "Supply Chain Planning", "pageId": "PG-102", "pageName": "Inventory & Safety Stock"},
            {"appId": "APP-FIN-02", "appName": "Financial & Profit App", "pageId": "PG-201", "pageName": "Revenue & Margin Simulation"},
            {"appId": "APP-FIN-02", "appName": "Financial & Profit App", "pageId": "PG-202", "pageName": "Cost Center Budget Analysis"},
            {"appId": "APP-EXEC-04", "appName": "Executive Portal", "pageId": "PG-401", "pageName": "Corporate KPI Summary"}
        ]

    actions = ["Open Page", "Edit Cell", "Export TSV", "Run Process", "Filter View"]
    now = datetime.now(UTC)
    records = []

    for u in user_rows:
        num_sessions = rng.randint(4, 25)
        sample_k = min(len(apps_pages_master), rng.randint(2, max(2, len(apps_pages_master) // 2)))
        fav_pages = rng.sample(apps_pages_master, sample_k)

        for _ in range(num_sessions):
            target = rng.choice(fav_pages)
            action = rng.choice(actions)
            random_sec = rng.randint(0, days * 86400)
            event_time = now - timedelta(seconds=random_sec)
            records.append({
                "userId": u["userId"],
                "user": u["user"],
                "appId": target["appId"],
                "appName": target["appName"],
                "pageId": target["pageId"],
                "pageName": target["pageName"],
                "timestamp": event_time.strftime("%Y-%m-%d %H:%M:%S"),
                "action": action
            })

    if not records:
        return pl.DataFrame(schema={
            "userId": pl.Utf8, "user": pl.Utf8, "appId": pl.Utf8, "appName": pl.Utf8,
            "pageId": pl.Utf8, "pageName": pl.Utf8, "timestamp": pl.Utf8, "action": pl.Utf8
        })

    df = pl.DataFrame(records)
    return df.sort("timestamp", descending=True)
