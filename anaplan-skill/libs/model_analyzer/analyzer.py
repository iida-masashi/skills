import base64
import concurrent.futures
import logging
from dataclasses import dataclass
from typing import Any

import polars as pl
import requests

logger = logging.getLogger(__name__)


@dataclass
class AnaplanConfig:
    user: str
    password: str
    workspace_id: str
    model_id: str


class AnaplanAuthenticator:
    """Anaplanの認証ロジックをカプセル化するクラス。将来的に証明書認証にも対応可能にするための布石。"""
    def __init__(self, config: AnaplanConfig):
        self.config = config
        self._token: str | None = None

    def get_token(self) -> str:
        if self._token:
            return self._token

        auth_string = f"{self.config.user}:{self.config.password}"
        encoded = base64.b64encode(auth_string.encode()).decode()
        headers = {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}
        auth_url = "https://auth.anaplan.com/token/authenticate"
        res = requests.post(auth_url, headers=headers)
        if res.status_code != 201:
            raise ValueError(f"Auth failed: {res.text}")

        self._token = res.json()["tokenInfo"]["tokenValue"]
        return self._token


class AnaplanModelAnalyzer:
    """Anaplanのデータモデルを解析し、依存関係ネットワークを生成するクラス"""

    def __init__(self, config: AnaplanConfig):
        self.config = config
        self.authenticator = AnaplanAuthenticator(config)
        self._cache = {}

    def _get_headers(self) -> dict[str, str]:
        token = self.authenticator.get_token()
        return {"Authorization": f"AnaplanAuthToken {token}", "Accept": "application/json"}

    def fetch_modules(self, status_callback=None) -> list[dict[str, Any]]:
        """APIからモジュール一覧を取得"""
        if "modules" in self._cache: return self._cache["modules"]
        if status_callback: status_callback("Downloading Modules list...")
        url = f"https://api.anaplan.com/2/0/models/{self.config.model_id}/modules"
        res = requests.get(url, headers=self._get_headers())
        res.raise_for_status()
        self._cache["modules"] = res.json().get("modules", [])
        return self._cache["modules"]

    def fetch_lists(self, status_callback=None) -> list[dict[str, Any]]:
        """APIからリスト一覧を取得し、並列処理で詳細メタデータを付与する"""
        if "lists" in self._cache: return self._cache["lists"]
        if status_callback: status_callback("Downloading Lists index...")
        url = f"https://api.anaplan.com/2/0/models/{self.config.model_id}/lists"
        res = requests.get(url, headers=self._get_headers())
        if res.status_code != 200:
            return []

        data = res.json()
        lists_base = data.get("lists", data.get("item", []))

        def fetch_list_detail(lst: dict[str, Any]) -> dict[str, Any]:
            list_id = lst["id"]
            detail_url = f"{url}/{list_id}"
            try:
                detail_res = requests.get(detail_url, headers=self._get_headers(), timeout=10)
                if detail_res.status_code == 200:
                    metadata = detail_res.json().get("metadata", {})
                    # マージ
                    return {**lst, **metadata}
            except Exception as e:
                logger.warning(f"Failed to fetch detail for list {list_id}: {e}")
            return lst

        enriched_lists = []
        if lists_base:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_lst = {executor.submit(fetch_list_detail, lst): lst for lst in lists_base}
                for future in concurrent.futures.as_completed(future_to_lst):
                    lst = future_to_lst[future]
                    if status_callback:
                        status_callback(f"Downloading List Detail: {lst.get('name', 'Unknown')}")
                    try:
                        enriched_lists.append(future.result())
                    except Exception:
                        pass

        self._cache["lists"] = enriched_lists
        return self._cache["lists"]

    def fetch_line_items(self, status_callback=None) -> list[dict[str, Any]]:
        """APIからラインアイテムとFormulaの依存情報を取得"""
        if "line_items" in self._cache: return self._cache["line_items"]
        if status_callback: status_callback("Downloading Line Items list (This may take a while)...")
        url = f"https://api.anaplan.com/2/0/models/{self.config.model_id}/lineItems?includeAll=true"
        res = requests.get(url, headers=self._get_headers())
        res.raise_for_status()
        self._cache["line_items"] = res.json().get("items", [])
        return self._cache["line_items"]

    def fetch_files(self, status_callback=None) -> list[dict[str, Any]]:
        """APIからファイル一覧を取得"""
        if "files" in self._cache: return self._cache["files"]
        if status_callback: status_callback("Downloading Files index...")
        url = f"https://api.anaplan.com/2/0/models/{self.config.model_id}/files"
        try:
            res = requests.get(url, headers=self._get_headers())
            if res.status_code == 200:
                data = res.json()
                self._cache["files"] = data.get("files", data.get("item", []))
                return self._cache["files"]
        except Exception as e:
            logger.warning(f"Failed to fetch files: {e}")
        return []

    def fetch_actions(self, status_callback=None) -> dict[str, list[dict[str, Any]]]:
        """インポート、エクスポート、プロセスの一覧を取得"""
        if "actions_raw" in self._cache: return self._cache["actions_raw"]

        actions: dict[str, list[dict[str, Any]]] = {}
        action_types = ["imports", "exports", "processes", "actions"]

        def fetch_action_category(action_type: str):
            url = f"https://api.anaplan.com/2/0/models/{self.config.model_id}/{action_type}"
            try:
                if status_callback: status_callback(f"Downloading {action_type.capitalize()} index...")
                res = requests.get(url, headers=self._get_headers())
                if res.status_code == 200:
                    data = res.json()
                    items = data.get(action_type, data.get("item", []))

                    def fetch_detail(item: dict[str, Any], url=url, action_type=action_type) -> dict[str, Any]:
                        item_id = item.get("id")
                        if not item_id:
                            return item
                        detail_url = f"{url}/{item_id}"
                        try:
                            d_res = requests.get(detail_url, headers=self._get_headers(), timeout=10)
                            if d_res.status_code == 200:
                                d_json = d_res.json()
                                if action_type == "processes":
                                    item["steps"] = d_json.get("processMetadata", {}).get("actions", [])
                                elif action_type == "imports":
                                    item.update(d_json.get("importMetadata", {}))
                                elif action_type == "exports":
                                    item.update(d_json.get("exportMetadata", {}))
                                elif action_type == "actions":
                                    item.update(d_json.get("action", {}))
                        except Exception as e:
                            logger.warning(f"Failed to fetch detail for {action_type} {item_id}: {e}")
                        return item

                    if items:
                        processed_items = []
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            future_to_item = {executor.submit(fetch_detail, item): item for item in items}
                            for future in concurrent.futures.as_completed(future_to_item):
                                item = future_to_item[future]
                                display_type = action_type[:-1].capitalize() if action_type.endswith('s') else action_type.capitalize()
                                if status_callback:
                                    status_callback(f"Downloading {display_type} Detail: {item.get('name', 'Unknown')}")
                                try:
                                    processed_items.append(future.result())
                                except Exception:
                                    pass
                        items = processed_items
                    return action_type, items
                return action_type, []
            except Exception as e:
                logger.warning(f"Failed to fetch {action_type}: {e}")
                return action_type, []

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as main_executor:
            futures = [main_executor.submit(fetch_action_category, at) for at in action_types]
            for future in concurrent.futures.as_completed(futures):
                try:
                    cat, items = future.result()
                    actions[cat] = items
                except Exception as e:
                    logger.warning(f"Error executing fetch_action_category: {e}")

        if "imports" in actions:
            files = self.fetch_files(status_callback)
            file_map = {f["id"]: f.get("name", "Unknown") for f in files}
            for imp in actions["imports"]:
                source_id = imp.get("importDataSourceId")
                if source_id:
                    imp["sourceFileName"] = file_map.get(source_id, "Unknown")
                else:
                    imp["sourceFileName"] = "-"

        self._cache["actions_raw"] = actions
        return actions

    def fetch_workspace_details(self, status_callback=None) -> dict[str, Any]:
        """APIからワークスペースの詳細情報を取得"""
        if "workspace_details" in self._cache: return self._cache["workspace_details"]

        # ワークスペースIDが間違っている場合を考慮し、先にモデル詳細を取得して config.workspace_id を正しい値に更新する
        if "model_details" not in self._cache:
            self.fetch_model_details(status_callback)

        if status_callback: status_callback("Downloading Workspace details...")
        url = f"https://api.anaplan.com/2/0/workspaces/{self.config.workspace_id}?tenantDetails=true"
        try:
            res = requests.get(url, headers=self._get_headers())
            if res.status_code == 200:
                ws = res.json().get("workspace", {})
                if ws:
                    self._cache["workspace_details"] = ws
                    return ws
        except Exception as e:
            logger.warning(f"Failed to fetch workspace details: {e}")
        self._cache["workspace_details"] = {}
        return {}

    def fetch_model_details(self, status_callback=None) -> dict[str, Any]:
        """APIからモデルの詳細情報を取得"""
        if "model_details" in self._cache: return self._cache["model_details"]
        if status_callback: status_callback("Downloading Model details...")
        url = f"https://api.anaplan.com/2/0/models/{self.config.model_id}?modelDetails=true"
        try:
            res = requests.get(url, headers=self._get_headers())
            if res.status_code == 200:
                mod = res.json().get("model", {})
                if mod:
                    self._cache["model_details"] = mod
                    if "currentWorkspaceId" in mod:
                        self.config.workspace_id = mod["currentWorkspaceId"]
                    elif "activeWorkspaceId" in mod:
                        self.config.workspace_id = mod["activeWorkspaceId"]
                    return mod
        except Exception as e:
            logger.warning(f"Failed to fetch model details: {e}")
        self._cache["model_details"] = {}
        return {}

    def extract_nodes_and_edges(self, level: str = "module") -> tuple[pl.DataFrame, pl.DataFrame, dict[str, pl.DataFrame]]:
        """メタデータを解析し、ノードとエッジのDataFrame、およびアクション一覧を返す
        level: "module" または "line_item"
        """
        modules = self.fetch_modules()
        line_items = self.fetch_line_items()
        actions_raw = self.fetch_actions()

        actions_dfs: dict[str, pl.DataFrame] = {}
        for k, v in actions_raw.items():
            if v:
                actions_dfs[k] = pl.DataFrame(v)
            else:
                actions_dfs[k] = pl.DataFrame()

        nodes_data = []
        edges_data = []
        edge_set = set() # 重複排除用

        if level == "module":
            # Build quick lookup for module names to IDs
            module_name_to_id = {m["name"]: m["id"] for m in modules}

            for m in modules:
                nodes_data.append(
                    {
                        "id": m["id"],
                        "label": m["name"],
                        "group": "Module",
                        "title": f"Module: {m['name']}",
                        "module": m["name"],
                        "line_item": "-",
                        "formula": "-",
                        "cellCount": 0,
                        "value": 1
                    }
                )

            # 解析: referencedBy からモジュール間の依存関係を抽出
            for li in line_items:
                source_module_id = li.get("moduleId")
                if not source_module_id:
                    continue

                referenced_by = li.get("referencedBy", [])
                for ref in referenced_by:
                    ref_name = ref.get("name", "")
                    if "." in ref_name:
                        target_module_name = ref_name.split(".")[0]
                        target_module_id = module_name_to_id.get(target_module_name)

                        if target_module_id and source_module_id != target_module_id:
                            edge_key = (source_module_id, target_module_id)
                            if edge_key not in edge_set:
                                edge_set.add(edge_key)
                                edges_data.append(
                                    {
                                        "source": source_module_id,
                                        "target": target_module_id,
                                        "label": "referenced_by",
                                        "value": 1,
                                        "dashes": False
                                    }
                                )

            # プロセスのノードとエッジ追加
            if "processes" in actions_raw and actions_raw["processes"]:
                for proc in actions_raw["processes"]:
                    proc_id = proc.get("id")
                    proc_name = proc.get("name", "")
                    if not proc_id:
                        continue

                    # Process Node
                    nodes_data.append(
                        {
                            "id": proc_id,
                            "label": f"🔄 {proc_name}",
                            "group": "Action: Process",
                            "title": f"Process: {proc_name}",
                            "module": "-",
                            "line_item": "-",
                            "formula": "-",
                            "cellCount": 0,
                            "value": 3
                        }
                    )

                    # Edge: Process -> Action (step)
                    steps = proc.get("steps", [])
                    for step in steps:
                        action_id = step.get("id") or step.get("actionId")
                        if action_id:
                            edge_key = (proc_id, action_id)
                            if edge_key not in edge_set:
                                edge_set.add(edge_key)
                                edges_data.append(
                                    {
                                        "source": proc_id,
                                        "target": action_id,
                                        "label": "executes",
                                        "value": 1,
                                        "dashes": False
                                    }
                                )

            # データフロー（Import/File）のヒューリスティック推論
            if "imports" in actions_raw and actions_raw["imports"]:
                for imp in actions_raw["imports"]:
                    imp_id = imp.get("id")
                    imp_name = imp.get("name", "")
                    if not imp_id:
                        continue

                    source_file = imp.get("sourceFileName", "-")

                    # Import Action Node
                    nodes_data.append(
                        {
                            "id": imp_id,
                            "label": f"📥 {imp_name}",
                            "group": "Action: Import",
                            "title": f"Import: {imp_name}\\nSource: {source_file}",
                            "module": "-",
                            "line_item": "-",
                            "formula": "-",
                            "cellCount": 0,
                            "value": 2
                        }
                    )

                    # File Source Node
                    if source_file != "-" and source_file != "Unknown":
                        file_id = f"file_{source_file}"
                        # Check if file node already added
                        if not any(n["id"] == file_id for n in nodes_data):
                            nodes_data.append(
                                {
                                    "id": file_id,
                                    "label": f"📄 {source_file}",
                                    "group": "Data Source",
                                    "title": f"File: {source_file}",
                                    "module": "-",
                                    "line_item": "-",
                                    "formula": "-",
                                    "cellCount": 0,
                                    "value": 1
                                }
                            )
                        # Edge: File -> Import
                        edges_data.append(
                            {
                                "source": file_id,
                                "target": imp_id,
                                "label": "reads_from",
                                "value": 1,
                                "dashes": False
                            }
                        )

                    # Heuristic inference: Import -> Module
                    for m_name, m_id in module_name_to_id.items():
                        if m_name.lower() in imp_name.lower():
                            edge_key = (imp_id, m_id)
                            if edge_key not in edge_set:
                                edge_set.add(edge_key)
                                edges_data.append(
                                    {
                                        "source": imp_id,
                                        "target": m_id,
                                        "label": "updates (inferred)",
                                        "value": 1,
                                        "dashes": True
                                    }
                                )

        elif level == "line_item":
            for li in line_items:
                formula = li.get("formula") or ""
                cell_count = li.get("cellCount", 0)
                estimated_mb = (cell_count * 8) / (1024 * 1024)
                nodes_data.append(
                    {
                        "id": li["id"],
                        "label": li["name"],
                        "group": li.get("moduleName", "Unknown"),
                        "title": f"Module: {li.get('moduleName')}\\nLineItem: {li['name']}\\nFormula: {formula}\\nCells: {cell_count:,}\\nEst. Size: {estimated_mb:.2f} MB",
                        "module": li.get("moduleName", "Unknown"),
                        "line_item": li["name"],
                        "formula": formula,
                        "cellCount": cell_count,
                        "estimated_size_mb": estimated_mb,
                        "value": cell_count if cell_count > 0 else 1
                    }
                )

            for li in line_items:
                source_li_id = li["id"]
                referenced_by = li.get("referencedBy", [])
                for ref in referenced_by:
                    target_li_id = ref.get("id")
                    if target_li_id and source_li_id != target_li_id:
                        edge_key = (source_li_id, target_li_id)
                        if edge_key not in edge_set:
                            edge_set.add(edge_key)
                            edges_data.append(
                                {
                                    "source": source_li_id,
                                    "target": target_li_id,
                                    "label": "referenced_by",
                                    "value": 1,
                                    "dashes": False
                                }
                            )

        if nodes_data:
            nodes_df = pl.DataFrame(nodes_data)
        else:
            nodes_df = pl.DataFrame(
                schema={"id": pl.Utf8, "label": pl.Utf8, "group": pl.Utf8, "title": pl.Utf8, "module": pl.Utf8, "line_item": pl.Utf8, "formula": pl.Utf8, "cellCount": pl.Int64, "value": pl.Int64}
            )

        if edges_data:
            edges_df = pl.DataFrame(edges_data)
        else:
            edges_df = pl.DataFrame(
                schema={"source": pl.Utf8, "target": pl.Utf8, "label": pl.Utf8, "value": pl.Int64, "dashes": pl.Boolean}
            )

        return nodes_df, edges_df, actions_dfs

    def enrich_modules_with_line_items(self, modules_df: pl.DataFrame, li_df: pl.DataFrame) -> pl.DataFrame:
        """PolarsのネイティブAPIを用いて、モジュール一覧にラインアイテムの集計情報を結合する"""
        if modules_df.is_empty() or li_df.is_empty() or "moduleId" not in li_df.columns:
            return modules_df

        # Optimization detection flags for Line Items before aggregating
        if "formula" in li_df.columns and "summary" in li_df.columns and "appliesTo" in li_df.columns:
            li_df = li_df.with_columns([
                (
                    (pl.col("formula").is_null() | (pl.col("formula") == "")) &
                    (pl.col("summary") != "None") &
                    (pl.col("appliesTo").list.len() > 0)
                ).alias("is_summary_optimization_candidate")
            ])
        else:
            li_df = li_df.with_columns(pl.lit(False).alias("is_summary_optimization_candidate"))

        # Polars Native Aggregation
        agg_exprs = [
            pl.len().alias("line_item_count"),
            pl.col("is_summary_optimization_candidate").sum().alias("opt_candidates_count")
        ]

        if "cellCount" in li_df.columns:
            agg_exprs.append(pl.col("cellCount").sum().alias("total_cell_count"))
            agg_exprs.append(((pl.col("cellCount").sum() * 8) / (1024 * 1024)).alias("estimated_size_mb"))
        else:
            agg_exprs.append(pl.lit(0).alias("total_cell_count"))
            agg_exprs.append(pl.lit(0.0).alias("estimated_size_mb"))

        if "appliesTo" in li_df.columns:
            agg_exprs.append(
                pl.col("appliesTo").explode().struct.field("name")
                .drop_nulls().unique().drop_nulls().implode().list.join(", ")
                .alias("dimensions")
            )
        else:
            agg_exprs.append(pl.lit("").alias("dimensions"))

        if "timeScale" in li_df.columns:
            agg_exprs.append(
                pl.col("timeScale")
                .drop_nulls().unique().drop_nulls().implode().list.join(", ")
                .alias("time_scales")
            )
        else:
            agg_exprs.append(pl.lit("").alias("time_scales"))

        li_agg = li_df.group_by("moduleId").agg(agg_exprs)

        # Left join with modules
        enriched_modules = modules_df.join(li_agg, left_on="id", right_on="moduleId", how="left")
        enriched_modules = enriched_modules.with_columns([
            pl.col("line_item_count").fill_null(0),
            pl.col("total_cell_count").fill_null(0),
            pl.col("estimated_size_mb").fill_null(0.0),
            pl.col("opt_candidates_count").fill_null(0),
            pl.col("dimensions").fill_null(""),
            pl.col("time_scales").fill_null("")
        ])

        return enriched_modules
