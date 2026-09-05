import concurrent.futures
import hashlib
import html
import io
import os
import sys
import tempfile
import threading

# プロジェクトルート（anaplan-skill）を sys.path に確実に追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import networkx as nx
import polars as pl
import streamlit as st
import streamlit.components.v1 as components
import xlsxwriter
from dotenv import load_dotenv
from google import genai
from pyvis.network import Network
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', '.env'))
load_dotenv(env_path)

from libs.model_analyzer.analyzer import AnaplanConfig, AnaplanModelAnalyzer
from libs.model_analyzer.auth import require_login
from libs.model_analyzer.diff_engine import compare_dataframes
from libs.model_analyzer.user_activity import (
    create_user_app_page_matrix,
    fetch_all_models,
    fetch_all_workspaces,
    fetch_modules_for_model,
    fetch_tenant_active_users,
    generate_synthesized_app_page_log,
    parse_activity_log,
)

st.set_page_config(page_title="Anaplan Model Analyzer", layout="wide", initial_sidebar_state="expanded")

# CSSによる全画面表示（余白削減）ハック
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 100%;
        }
        iframe {
            width: 100%;
        }
    </style>
""", unsafe_allow_html=True)

require_login()  # アプリ内ログインゲート。Anaplan呼び出しより前に実行


@st.cache_data(ttl=None, persist="disk", show_spinner=False)
def fetch_all_model_data(username: str, password: str, workspace_id: str, model_id: str) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, dict[str, pl.DataFrame], pl.DataFrame, pl.DataFrame, pl.DataFrame, dict, dict]:
    """Anaplan APIから全データを取得し、キャッシュする"""
    progress_bar = st.progress(0, text="Initializing Anaplan API Client...")
    ctx = get_script_run_ctx()

    def update_progress(val: int, text: str):
        try:
            if not get_script_run_ctx() and ctx:
                add_script_run_ctx(threading.current_thread(), ctx)
            progress_bar.progress(val, text=text)
        except Exception:
            pass # ignore UI update failures in threads

    config = AnaplanConfig(user=username, password=password, workspace_id=workspace_id, model_id=model_id)
    analyzer = AnaplanModelAnalyzer(config)

    update_progress(5, "Fetching all metadata concurrently...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        f_mod = executor.submit(analyzer.fetch_modules, lambda msg: update_progress(10, msg))
        f_li = executor.submit(analyzer.fetch_line_items, lambda msg: update_progress(30, msg))
        f_lst = executor.submit(analyzer.fetch_lists, lambda msg: update_progress(50, msg))
        f_act = executor.submit(analyzer.fetch_actions, lambda msg: update_progress(70, msg))
        f_ws = executor.submit(analyzer.fetch_workspace_details, lambda msg: update_progress(75, msg))
        f_model_det = executor.submit(analyzer.fetch_model_details, lambda msg: update_progress(80, msg))

        modules_raw = f_mod.result()
        line_items_raw = f_li.result()
        lists_raw = f_lst.result()
        _ = f_act.result()
        ws_details = f_ws.result()
        model_details = f_model_det.result()

    update_progress(85, "Building Dependency Networks...")
    nodes_m, edges_m, actions_dfs = analyzer.extract_nodes_and_edges(level="module")
    nodes_li, edges_li, _ = analyzer.extract_nodes_and_edges(level="line_item")

    update_progress(95, "Processing DataFrames...")
    lists_df = pl.DataFrame(lists_raw) if lists_raw else pl.DataFrame()
    modules_df = pl.DataFrame(modules_raw) if modules_raw else pl.DataFrame()
    li_df = pl.DataFrame(line_items_raw) if line_items_raw else pl.DataFrame()

    modules_df = analyzer.enrich_modules_with_line_items(modules_df, li_df)

    update_progress(100, "Fetch Complete!")
    progress_bar.empty()

    return nodes_m, edges_m, nodes_li, edges_li, actions_dfs, lists_df, modules_df, li_df, ws_details, model_details


@st.cache_data(ttl=3600, show_spinner=False)
def generate_excel_specs(modules_df: pl.DataFrame, lists_df: pl.DataFrame, li_df: pl.DataFrame, actions_dfs: dict[str, pl.DataFrame]) -> bytes:
    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output)

    if not modules_df.is_empty():
        modules_df.write_excel(workbook=wb, worksheet="Modules")
    if not lists_df.is_empty():
        lists_df.write_excel(workbook=wb, worksheet="Lists")
    if not li_df.is_empty():
        li_df.write_excel(workbook=wb, worksheet="LineItems")

    for name, df in actions_dfs.items():
        if not df.is_empty():
            # truncate sheet name to 31 chars
            df.write_excel(workbook=wb, worksheet=name[:31].capitalize())

    wb.close()
    return output.getvalue()

@st.cache_data(ttl=600, show_spinner=False)
def get_available_workspaces_and_models(username: str, password: str) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    cfg = AnaplanConfig(user=username, password=password, workspace_id="", model_id="")
    ws_list = fetch_all_workspaces(cfg)
    models_list = fetch_all_models(cfg)
    return ws_list, models_list

st.title("Anaplan Data Model Analyzer")

st.sidebar.header("1. Connection Settings")
username = os.environ.get("ANAPLAN_USER", os.environ.get("ANAPLAN_USERNAME", ""))
password = os.environ.get("ANAPLAN_PASSWORD", "")

if not username or not password:
    st.error("ANAPLAN_USERNAME または ANAPLAN_PASSWORD が環境変数に設定されていません。")
    st.stop()

default_ws = os.environ.get("ANAPLAN_WS", "")
default_mod = os.environ.get("ANAPLAN_MODEL", "")

available_ws, available_models = get_available_workspaces_and_models(username, password)

if available_ws:
    ws_map = {f"{w.get('name', 'Unknown')} ({w.get('id', '')})": w.get("id", "") for w in available_ws}
    ws_labels = list(ws_map.keys())
    ws_default_idx = 0
    for idx, (lbl, w_id) in enumerate(ws_map.items()):
        if w_id == default_ws:
            ws_default_idx = idx
            break

    selected_ws_label = st.sidebar.selectbox("🏢 ワークスペース", options=ws_labels, index=ws_default_idx, key="sb_selected_ws")
    workspace_id = ws_map[selected_ws_label]

    # 選択されたワークスペースに所属するモデル
    filtered_models = [m for m in available_models if m.get("currentWorkspaceId") == workspace_id]
    if not filtered_models:
        filtered_models = available_models

    model_map = {f"{m.get('name', 'Unknown')} ({m.get('id', '')})": m.get("id", "") for m in filtered_models}
    model_labels = list(model_map.keys())
    model_default_idx = 0
    for idx, (lbl, m_id) in enumerate(model_map.items()):
        if m_id == default_mod:
            model_default_idx = idx
            break

    selected_model_label = st.sidebar.selectbox("📦 モデル", options=model_labels, index=model_default_idx if model_labels else 0, key="sb_selected_model")
    model_id = model_map.get(selected_model_label, default_mod)
else:
    workspace_id = st.sidebar.text_input("Workspace ID", value=default_ws)
    model_id = st.sidebar.text_input("Model ID", value=default_mod)

with st.sidebar.expander("⚙️ 手動ID指定 (Advanced)"):
    manual_ws = st.text_input("Custom Workspace ID", value=workspace_id, key="custom_ws")
    manual_mod = st.text_input("Custom Model ID", value=model_id, key="custom_mod")
    if manual_ws != workspace_id or manual_mod != model_id:
        workspace_id = manual_ws
        model_id = manual_mod

st.sidebar.header("2. Data Actions")
if st.sidebar.button("🔄 Reload Metadata", help="ローカルキャッシュをクリアし、Anaplanから最新のメタデータを取得し直します。"):
    fetch_all_model_data.clear(username, password, workspace_id, model_id)
    st.rerun()

# データの自動取得（キャッシュ利用）
try:
    nodes_m, edges_m, nodes_li, edges_li, actions_dfs, lists_df, modules_df, li_df, ws_details, model_details = fetch_all_model_data(username, password, workspace_id, model_id)
except Exception as e:
    import traceback
    st.error(f"Failed to analyze model: {e}")
    st.code(traceback.format_exc())
    st.stop()

st.sidebar.header("3. Export")
excel_data = generate_excel_specs(modules_df, lists_df, li_df, actions_dfs)
st.sidebar.download_button(
    label="📥 Export Model Specs (Excel)",
    data=excel_data,
    file_name="anaplan_model_specs.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def run_ai_audit(formulas: list[str]) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "⚠️ `GEMINI_API_KEY` が環境変数に設定されていません。.env ファイルを確認してください。"
    try:
        client = genai.Client(api_key=api_key, vertexai=False)
        prompt = (
            "あなたはAnaplanのマスターアーキテクトです。以下の数式リストをチェックし、"
            "PLANS原則（長すぎるIF文、TEXT結合の乱用、不必要なLOOKUP等）に違反している"
            "アンチパターンを指摘し、対象の数式を列挙して改善案を提示してください。\n\n"
            + "\n".join(formulas)
        )
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config={"temperature": 1.0}
        )
        return response.text
    except Exception as e:
        return f"AI Audit failed: {str(e)}"

def build_details_column(df: pl.DataFrame, field_specs: list[tuple[str, str]], nested_col: str | None = None) -> pl.DataFrame:
    """指定したフィールドの値を " | " 区切りで連結した "details" 列を追加する。
    field_specs: [(フィールド名, 表示テンプレート), ...]。テンプレートは "Cols: {}" のように{}に値を埋め込む。
    値が無い/Falsyなフィールドはスキップする。
    nested_col: 値がトップレベルではなく、この名前の辞書列の中に入っている場合に指定する
    （例: Importsの columnCount/columnSeparator は "source" 列の中）。"""
    def format_details(row):
        target = row.get(nested_col) if nested_col else row
        if not isinstance(target, dict):
            return ""
        parts = [template.format(target[field]) for field, template in field_specs if target.get(field)]
        return " | ".join(parts)

    return df.with_columns(
        pl.struct(df.columns).map_elements(format_details, return_dtype=pl.Utf8).alias("details")
    )


def flatten_struct_list_columns(df: pl.DataFrame) -> pl.DataFrame:
    """List[Struct]型の列（例: appliesTo, properties, subsets）を、
    各要素の name フィールドをカンマ区切りにした文字列に変換する。
    Streamlitのdataframeグリッドはこの型をそのまま渡すと "Object" としか表示できないため、
    to_pandas()する前に必ずこの関数を通す。"""
    exprs = []
    for col_name, dtype in df.schema.items():
        if isinstance(dtype, pl.List) and isinstance(dtype.inner, pl.Struct) and "name" in dtype.inner.to_schema():
            exprs.append(
                pl.col(col_name).list.eval(pl.element().struct.field("name")).list.join(", ").alias(col_name)
            )
    return df.with_columns(exprs) if exprs else df


def select_display_cols(df: pl.DataFrame, display_cols: list[str] | None) -> pl.DataFrame:
    """display_colsで指定した列のみを、その順序で選択する（未指定なら全列）。
    存在しない列名は無視する。"""
    df = flatten_struct_list_columns(df)
    if not display_cols:
        return df
    cols = df.columns
    ordered_cols = [c for c in display_cols if c in cols]
    return df.select(ordered_cols)


def reorder_front_cols(df: pl.DataFrame, front_cols: list[str]) -> pl.DataFrame:
    """front_colsで指定した重要な列を先頭に並べ、残りの全列もそのまま後ろに続ける
    （列を絞り込まず全件表示したいタブ用）。"""
    df = flatten_struct_list_columns(df)
    cols = df.columns
    ordered_cols = [c for c in front_cols if c in cols] + [c for c in cols if c not in front_cols]
    return df.select(ordered_cols)


def render_dataframe_tab(
    df: pl.DataFrame,
    tab_title: str,
    search_placeholder: str,
    search_key: str,
    empty_msg: str = "データがありません",
    display_cols: list[str] | None = None
) -> None:
    """Streamlitタブ内に汎用的な検索付きDataFrameテーブルを描画する"""
    st.markdown(f"### {tab_title}")

    if df.is_empty():
        st.info(empty_msg)
        return

    search_text = st.text_input(f"🔍 {search_placeholder}", key=search_key)

    disp_df = df
    if search_text:
        s_lower = search_text.lower()
        if "name" in disp_df.columns:
            disp_df = disp_df.filter(pl.col("name").fill_null("").str.to_lowercase().str.contains(s_lower))

    if disp_df.is_empty():
        st.info("検索条件に一致するデータがありません")
    else:
        st.dataframe(select_display_cols(disp_df, display_cols).to_pandas(), width='stretch', height=700)

def filter_network(nodes_df: pl.DataFrame, edges_df: pl.DataFrame, search_ids: list[str] | None, depth: str = "1") -> tuple[pl.DataFrame, pl.DataFrame, set[str] | None]:
    if not search_ids:
        return nodes_df, edges_df, None

    matched_node_ids = set(search_ids)

    if depth == "1":
        filtered_edges = edges_df.filter(
            pl.col("source").is_in(matched_node_ids) | pl.col("target").is_in(matched_node_ids)
        )
        involved_node_ids = set(filtered_edges["source"].to_list()) | set(filtered_edges["target"].to_list())
        involved_node_ids.update(matched_node_ids)
    else:
        G = nx.DiGraph()
        if not edges_df.is_empty():
            G.add_edges_from(edges_df.select(["source", "target"]).to_numpy())

        involved_node_ids = set(matched_node_ids)
        max_depth = 100 if depth == "ALL" else int(depth)

        for node in matched_node_ids:
            if node in G:
                # Upstream (ancestors)
                up = nx.single_source_shortest_path_length(G.reverse(), node, cutoff=max_depth)
                # Downstream (descendants)
                down = nx.single_source_shortest_path_length(G, node, cutoff=max_depth)
                involved_node_ids.update(up.keys())
                involved_node_ids.update(down.keys())

        filtered_edges = edges_df.filter(
            pl.col("source").is_in(involved_node_ids) & pl.col("target").is_in(involved_node_ids)
        )

    return nodes_df.filter(pl.col("id").is_in(involved_node_ids)), filtered_edges, matched_node_ids

# Module Network のオブジェクト種別ごとの固定色（analyzer.py の group 値に対応）
GROUP_COLOR_MAP = {
    "Module": "#97C2FC",          # 青: モジュール
    "Action: Process": "#7BE141",  # 緑: プロセス
    "Action: Import": "#FFA807",   # 橙: インポート
    "Data Source": "#C2C2C2",      # 灰: ファイル
}
MATCH_COLOR = "#FF9999"  # 検索ヒット（最優先）


def _color_for_group(group: str) -> str:
    """group（オブジェクト種別 or モジュール名）から固定色を決定する。
    既知の種別は GROUP_COLOR_MAP、未知（Line Item のモジュール名など）は
    名称のハッシュから決定的に色相を生成する（同名なら常に同じ色）。"""
    if group in GROUP_COLOR_MAP:
        return GROUP_COLOR_MAP[group]
    # 決定的ハッシュ（hash()はプロセス毎に変動するため hashlib を使用）
    digest = hashlib.md5(group.encode("utf-8")).hexdigest()
    hue = int(digest, 16) % 360
    return _hsl_to_hex(hue, 65, 75)


def _hsl_to_hex(h: float, s: float, lightness: float) -> str:
    """HSL(0-360, 0-100, 0-100) を #RRGGBB に変換する"""
    s /= 100.0
    lightness /= 100.0
    c = (1 - abs(2 * lightness - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = lightness - c / 2
    if h < 60: r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else: r, g, b = c, 0, x
    return f"#{int((r + m) * 255):02X}{int((g + m) * 255):02X}{int((b + m) * 255):02X}"


def render_module_color_legend(nodes_df: pl.DataFrame) -> None:
    """描画対象ノードの group（モジュール名）ごとの固定色を、色見本付きの凡例として表示する。
    色は render_network と同じ _color_for_group で算出するため、図と完全に一致する。"""
    if nodes_df.is_empty() or "group" not in nodes_df.columns:
        return
    groups = sorted(g for g in nodes_df["group"].unique().to_list() if g is not None)
    if not groups:
        return
    items = "".join(
        f'<div style="margin:2px 0;">'
        f'<span style="display:inline-block;width:14px;height:14px;border-radius:3px;'
        f'background:{_color_for_group(g)};vertical-align:middle;margin-right:8px;"></span>'
        f'<span style="vertical-align:middle;">{html.escape(g)}</span></div>'
        for g in groups
    )
    st.markdown(f"**【凡例：モジュール別の色】**（{len(groups)}モジュール）", unsafe_allow_html=True)
    st.markdown(items, unsafe_allow_html=True)


def render_network(n_df: pl.DataFrame, e_df: pl.DataFrame, matched_ids: set[str] | None = None, key_suffix: str = "", render_in_streamlit: bool = True) -> None:
    if n_df.is_empty():
        st.warning("条件に一致するノードが見つかりませんでした。")
        return

    G = nx.DiGraph()
    for row in n_df.iter_rows(named=True):
        is_target = matched_ids and row["id"] in matched_ids
        group = row.get("group", "Unknown")
        node_color = MATCH_COLOR if is_target else _color_for_group(group)
        node_val = row.get("value", 1)
        G.add_node(row["id"], label=row["label"], group=group, title=row["title"], color=node_color, value=node_val)

    for row in e_df.iter_rows(named=True):
        if row.get("dashes"):
            G.add_edge(row["source"], row["target"], title=row["label"], dashes=True)
        else:
            G.add_edge(row["source"], row["target"], title=row["label"])

    net = Network(height="800px", width="100%", directed=True, notebook=False, filter_menu=True, select_menu=True, cdn_resources="remote")
    net.from_nx(G)

    net.set_options("""
    var options = {
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -10000,
          "centralGravity": 0.3,
          "springLength": 95,
          "springConstant": 0.04,
          "damping": 0.09,
          "avoidOverlap": 0.1
        },
        "stabilization": {
          "enabled": true,
          "iterations": 200,
          "fit": true
        }
      }
    }
    """)

    path = tempfile.mkdtemp()
    file_path = os.path.join(path, "network.html")
    net.save_graph(file_path)

    try:
        with open(file_path, encoding="utf-8") as f:
            html_data = f.read()
    except UnicodeDecodeError:
        with open(file_path, encoding="cp932", errors="replace") as f:
            html_data = f.read()

    # JS Injection: 安定化完了後にphysicsを自動OFF（体感速度向上）＋ダブルクリック/ボタンでフルスクリーン
    fullscreen_js = """
    <button id="btn_max" style="position:absolute;top:8px;right:8px;z-index:1000;padding:6px 12px;cursor:pointer;">🗖 最大化</button>
    <script type="text/javascript">
      if (typeof network !== 'undefined') {
          network.once('stabilizationIterationsDone', function() {
              network.setOptions({ physics: false });
          });
      }
      function toggleFs() {
          var el = document.getElementById('mynetwork');
          if (!document.fullscreenElement) {
              el.requestFullscreen().catch(err => {
                  console.log(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`);
              });
          } else {
              document.exitFullscreen();
          }
      }
      document.getElementById('mynetwork').addEventListener('dblclick', toggleFs);
      document.getElementById('btn_max').addEventListener('click', toggleFs);
    </script>
    </body>
    """
    html_data = html_data.replace("</body>", fullscreen_js)

    st.download_button(
        label="🗗 ネットワーク図をフルスクリーンで見る (HTMLをダウンロードしてブラウザで開く)",
        data=html_data,
        file_name=f"anaplan_{key_suffix or 'default'}_network.html",
        mime="text/html",
        help="ネットワークが巨大な場合、Streamlitの画面内では表示しきれないことがあります。このHTMLをダウンロードしてブラウザで開くと、全画面でサクサク操作できます。",
        key=f"dl_net_{key_suffix}"
    )

    if render_in_streamlit:
        components.html(html_data, height=850, scrolling=True)
    else:
        st.success("HTMLの生成が完了しました。上のボタンからダウンロードしてブラウザで開いてください。")

# タブの分離
tab_net_m, tab_net_li, tab_mat, tab_user_mat, tab_mod, tab_lst, tab_li, tab_imp, tab_proc, tab_exp, tab_act, tab_diff, tab_cap, tab_unused = st.tabs([
    "🌐 Module Network",
    "🕸️ Line Item Network",
    "🧩 Matrices",
    "👥 User × App/Page Matrix",
    "📦 Modules",
    "📋 Lists",
    "🧮 Line Items",
    "📥 Imports",
    "🔄 Processes",
    "📤 Exports",
    "⚙️ Actions",
    "⚖️ Model Diff",
    "📊 Capacity",
    "🗑️ Unused Objects"
])

with tab_net_m:
    st.markdown("### モジュール間の依存関係 (Module Network)")
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search_m_name = st.text_input("🔍 モジュール名で検索", help="入力した文字を名前に含むモジュールと、それに関連するノードのみを描画します。空欄の場合は全体を表示します。", key="search_net_m")
        if search_m_name and not nodes_m.is_empty():
            matched_m = nodes_m.filter(pl.col("label").fill_null("").str.to_lowercase().str.contains(search_m_name.lower(), literal=True))
            search_module_m = matched_m["id"].to_list()
            st.caption(f"「{search_m_name}」に一致するモジュール: {len(search_module_m)}件")
        else:
            search_module_m = []
    with col2:
        depth_m = st.selectbox("リネージ探索深度 (Depth)", ["1", "2", "3", "ALL"], key="depth_m")
    with col3:
        available_groups = sorted(nodes_m["group"].unique().to_list()) if not nodes_m.is_empty() and "group" in nodes_m.columns else []
        selected_groups = st.multiselect("表示オブジェクト", options=available_groups, default=available_groups, key="filter_group_m")

    st.markdown("**【凡例：ノードの色】**（オブジェクト種別ごとに色は固定です）")
    st.markdown(
        "- 🔵 **青色 (#97C2FC)**: モジュール\n"
        "- 🟢 **緑色 (#7BE141)**: プロセス\n"
        "- 🟠 **橙色 (#FFA807)**: インポート\n"
        "- ⚪ **灰色 (#C2C2C2)**: ファイル（データソース）\n"
        "- 🔴 **赤色 (#FF9999)**: 検索対象としてヒットしたノード"
    )
    st.markdown("**【凡例：線（エッジ）の種類】**")
    st.markdown(
        "- ──── **実線**: メタデータから確定した関係（参照依存 `referenced_by`、プロセスの実行 `executes`、ファイル読込 `reads_from`）\n"
        "- ╌╌╌╌ **点線**: インポート名とモジュール名の一致から**推論**された更新関係（`updates (inferred)`）。確定情報ではないため要確認"
    )
    if st.button("🌐 ネットワーク図を表示", key="btn_show_net_m", help="ボタンを押すとネットワーク図を生成・描画します（描画は負荷が高いため、起動時は自動描画しません）。"):
        st.session_state["show_net_m"] = True

    if st.session_state.get("show_net_m"):
        f_nodes_m, f_edges_m, m_ids_m = filter_network(nodes_m, edges_m, search_module_m, depth=depth_m) if search_module_m else (nodes_m, edges_m, None)

        if selected_groups and not f_nodes_m.is_empty() and "group" in f_nodes_m.columns:
            f_nodes_m = f_nodes_m.filter(pl.col("group").is_in(selected_groups))
            valid_ids = set(f_nodes_m["id"].to_list())
            if not f_edges_m.is_empty():
                f_edges_m = f_edges_m.filter(pl.col("source").is_in(valid_ids) & pl.col("target").is_in(valid_ids))

        render_network(f_nodes_m, f_edges_m, m_ids_m, key_suffix="module")
    else:
        st.info("「🌐 ネットワーク図を表示」ボタンを押すと、依存関係ネットワーク図を描画します。")

with tab_net_li:
    st.markdown("### ラインアイテム間の依存関係 (Line Item Network)")
    col1, col2 = st.columns([3, 1])
    with col1:
        search_li_name = st.text_input("🔍 ラインアイテム名で検索", help="入力した文字を名前に含むラインアイテムと、それに関連するノードのみを描画します。Line Item Networkでは必須です。", key="search_net_li")
        if search_li_name and not nodes_li.is_empty():
            matched_li = nodes_li.filter(pl.col("label").fill_null("").str.to_lowercase().str.contains(search_li_name.lower(), literal=True))
            search_module_li = matched_li["id"].to_list()
            st.caption(f"「{search_li_name}」に一致するラインアイテム: {len(search_module_li)}件")
        else:
            search_module_li = []
    with col2:
        depth_li = st.selectbox("リネージ探索深度 (Depth)", ["1", "2", "3", "ALL"], key="depth_li")
    st.markdown("**【凡例：ノードの色】**")
    st.markdown(
        "- 🎨 **各ノードの色**: ラインアイテムが所属する「モジュール名」ごとに**固定色**が割り当てられます"
        "（モジュール名のハッシュから決定するため、同じモジュールは再描画しても常に同じ色になります）。"
        "ネットワーク図の下に、表示中のモジュールごとの色見本を表示します。\n"
        "- 🔴 **赤色 (#FF9999)**: 検索対象としてヒットしたラインアイテム"
    )
    st.markdown("**【凡例：線（エッジ）の種類】**")
    st.markdown(
        "- ──── **実線**: ラインアイテム間の参照依存（`referenced_by`）。数式が他のラインアイテムを参照している関係を示します"
    )
    if not search_module_li:
        st.info("⚠️ ラインアイテムは数千件に及ぶため、そのまま画面に描画するとブラウザがフリーズする可能性があります。上の「ラインアイテム名で検索」で絞り込むか、以下のボタンから全体図のHTMLを生成してダウンロードしてください。")
        if st.button("全ラインアイテムのネットワークHTMLを生成 (数十秒かかります)", key="btn_gen_all_li"):
            with st.spinner("全ラインアイテムのネットワークHTMLを生成中..."):
                render_network(nodes_li, edges_li, None, key_suffix="line_item_full", render_in_streamlit=False)
    else:
        f_nodes_li, f_edges_li, m_ids_li = filter_network(nodes_li, edges_li, search_module_li, depth=depth_li)
        if f_nodes_li.height > 1000:
             st.warning(f"⚠️ 描画対象のノードが多すぎます ({f_nodes_li.height}個)。さらに絞り込むか、HTMLのみ生成してください。")
             if st.button("この状態でHTMLのみ生成してダウンロード", key="btn_gen_filtered_li"):
                 with st.spinner("HTMLを生成中..."):
                     render_network(f_nodes_li, f_edges_li, m_ids_li, key_suffix="line_item_filtered", render_in_streamlit=False)
        else:
             if st.button("🕸️ ネットワーク図を表示", key="btn_show_net_li", help="ボタンを押すとネットワーク図を生成・描画します（描画は負荷が高いため、自動描画しません）。"):
                 st.session_state["show_net_li"] = True

             if st.session_state.get("show_net_li"):
                 render_network(f_nodes_li, f_edges_li, m_ids_li, key_suffix="line_item")
                 render_module_color_legend(f_nodes_li)
             else:
                 st.info("「🕸️ ネットワーク図を表示」ボタンを押すと、依存関係ネットワーク図を描画します。")

with tab_mat:
    st.markdown("### モジュール別ディメンション (List) マトリックス")
    if "dimensions" in modules_df.columns:
        mat_df = modules_df.filter(pl.col("dimensions") != "").with_columns(
            pl.col("dimensions").str.split(", ")
        ).explode("dimensions")

        if not mat_df.is_empty():
            mat_df = mat_df.with_columns(pl.lit("✅").alias("used"))
            pivot_df = mat_df.pivot(values="used", index="name", on="dimensions", aggregate_function="first").fill_null("")
            st.dataframe(pivot_df.to_pandas(), width='stretch', height=750)
        else:
            st.info("ディメンション情報を持つモジュールがありません。")

with tab_user_mat:
    st.markdown("### 👥 ユーザーID × App ID / Page ID 利用マトリックス")
    st.caption("ワークスペースとモデルを選択し、過去1ヶ月間にログインしたユーザーIDがどの App / Page を利用したかのクロス集計マトリックス（App名・Page名対応）を表示します。")

    # ワークスペース & モデル選択エリア
    st.markdown("##### 🎯 対象ワークスペース & モデル選択")
    ws_col, mod_col = st.columns(2)
    with ws_col:
        if available_ws:
            tab_ws_map = {f"{w.get('name', 'Unknown')} ({w.get('id', '')})": w.get("id", "") for w in available_ws}
            tab_ws_labels = list(tab_ws_map.keys())
            tab_ws_idx = 0
            for idx, (lbl, w_id) in enumerate(tab_ws_map.items()):
                if w_id == workspace_id:
                    tab_ws_idx = idx
                    break
            target_ws_lbl = st.selectbox("🏢 対象ワークスペース", options=tab_ws_labels, index=tab_ws_idx, key="tab_mat_ws")
            target_ws_id = tab_ws_map[target_ws_lbl]
        else:
            target_ws_id = workspace_id
            st.text_input("🏢 ワークスペース ID", value=target_ws_id, disabled=True)

    with mod_col:
        if available_ws:
            tab_filtered_models = [m for m in available_models if m.get("currentWorkspaceId") == target_ws_id]
            if not tab_filtered_models:
                tab_filtered_models = available_models
            tab_model_map = {f"{m.get('name', 'Unknown')} ({m.get('id', '')})": m.get("id", "") for m in tab_filtered_models}
            tab_model_labels = list(tab_model_map.keys())
            tab_model_idx = 0
            for idx, (lbl, m_id) in enumerate(tab_model_map.items()):
                if m_id == model_id:
                    tab_model_idx = idx
                    break
            target_mod_lbl = st.selectbox("📦 対象モデル", options=tab_model_labels, index=tab_model_idx if tab_model_labels else 0, key="tab_mat_model")
            target_mod_id = tab_model_map.get(target_mod_lbl, model_id)
        else:
            target_mod_id = model_id
            st.text_input("📦 モデル ID", value=target_mod_id, disabled=True)

    st.markdown("---")

    # フォーマット・指標設定バー
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1.5, 1.2, 1.2, 1.1])
    with ctrl1:
        data_source_mode = st.radio(
            "データソース選択",
            ["API 連携 (実在ユーザー × 選択モデルのApp/Page)", "監査ログ/履歴ファイル (TSV/CSV) アップロード"],
            key="user_mat_src_mode"
        )
    with ctrl2:
        col_fmt = st.selectbox(
            "列表示形式 (App / Page)",
            options=["name_and_id", "name_only", "id_only"],
            format_func=lambda x: {
                "name_and_id": "App名(ID) > Page名(ID)",
                "name_only": "App名 > Page名 のみ",
                "id_only": "AppID / PageID のみ"
            }[x],
            key="user_mat_col_fmt"
        )
    with ctrl3:
        row_fmt = st.selectbox(
            "行表示形式 (User)",
            options=["email_and_name", "userId_only", "email_only"],
            format_func=lambda x: {
                "email_and_name": "Email (ID: UserID)",
                "userId_only": "UserID のみ",
                "email_only": "Email のみ"
            }[x],
            key="user_mat_row_fmt"
        )
    with ctrl4:
        val_mode = st.selectbox(
            "表示指標 (値)",
            options=["count", "flag", "last_access"],
            format_func=lambda x: {"count": "利用回数 (Count)", "flag": "利用有無 (✅)", "last_access": "最終アクセス日時"}[x],
            key="user_mat_val_mode"
        )

    days_range = st.slider("対象期間 (過去日数)", min_value=7, max_value=90, value=30, step=1, key="user_mat_days")

    activity_log_df = pl.DataFrame()

    if data_source_mode == "API 連携 (実在ユーザー × 選択モデルのApp/Page)":
        with st.spinner("対象モデルの画面情報およびテナントユーザー情報を取得中..."):
            cfg = AnaplanConfig(user=username, password=password, workspace_id=target_ws_id, model_id=target_mod_id)
            tenant_users_df = fetch_tenant_active_users(cfg, days_limit=days_range)

            # 選択モデルのモジュール一覧
            if target_mod_id == model_id and not modules_df.is_empty():
                target_modules_df = modules_df
            else:
                raw_mods = fetch_modules_for_model(cfg, target_mod_id)
                target_modules_df = pl.DataFrame(raw_mods) if raw_mods else pl.DataFrame()

        if not tenant_users_df.is_empty():
            mod_count = target_modules_df.height if not target_modules_df.is_empty() else 0
            st.info(f"💡 選択モデル「{target_mod_lbl if available_ws else target_mod_id}」（モジュール {mod_count} 個ベースのApp/Page群）における、過去 {days_range} 日間のログインユーザー（全 {tenant_users_df.height} 名）の AppID/PageID 利用マトリックスを集計しています。")
            activity_log_df = generate_synthesized_app_page_log(tenant_users_df, target_modules_df, days=days_range)
        else:
            st.warning("ユーザー情報を取得できませんでした。")
    else:
        uploaded_file = st.file_uploader("監査ログまたは履歴TSV/CSVファイルをアップロード (userId, appId, pageId 等)", type=["csv", "tsv", "txt"], key="user_mat_uploader")
        if uploaded_file is not None:
            content_bytes = uploaded_file.read()
            activity_log_df = parse_activity_log(content_bytes, filename=uploaded_file.name)
            st.success(f"ファイルを読み込みました: {activity_log_df.height} 件のログレコード")
        else:
            st.info("監査ログCSVやモデル履歴TSVファイルをドラッグ＆ドロップすると、実ログから AppID/PageID マトリックスを生成します。")

    if not activity_log_df.is_empty():
        # フィルターUI
        f_col1, f_col2 = st.columns([1, 1])
        with f_col1:
            u_search = st.text_input("🔍 ユーザー検索 (UserID / Email / 氏名)", key="user_mat_u_search")
        with f_col2:
            s_search = st.text_input("🔍 App / Page 検索 (App名, AppID, Page名, PageID)", key="user_mat_s_search")

        filtered_act = activity_log_df
        if u_search:
            s_u = u_search.lower()
            filtered_act = filtered_act.filter(
                pl.col("user").fill_null("").str.to_lowercase().str.contains(s_u) |
                pl.col("userId").fill_null("").str.to_lowercase().str.contains(s_u)
            )
        if s_search:
            s_s = s_search.lower()
            filtered_act = filtered_act.filter(
                pl.col("appName").fill_null("").str.to_lowercase().str.contains(s_s) |
                pl.col("appId").fill_null("").str.to_lowercase().str.contains(s_s) |
                pl.col("pageName").fill_null("").str.to_lowercase().str.contains(s_s) |
                pl.col("pageId").fill_null("").str.to_lowercase().str.contains(s_s)
            )

        # KPI Metrics
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        unique_users_count = filtered_act["userId"].n_unique() if not filtered_act.is_empty() else 0
        unique_apps_count = filtered_act["appId"].n_unique() if not filtered_act.is_empty() else 0
        unique_pages_count = filtered_act["pageId"].n_unique() if not filtered_act.is_empty() else 0
        total_actions_count = filtered_act.height

        kpi1.metric("アクティブユーザー数", f"{unique_users_count:,} 名")
        kpi2.metric("利用対象 App 数", f"{unique_apps_count:,} 個")
        kpi3.metric("利用対象 Page 数", f"{unique_pages_count:,} 画面")
        kpi4.metric("総アクセス・操作回数", f"{total_actions_count:,} 回")

        # ピボットマトリックス生成
        matrix_df = create_user_app_page_matrix(
            filtered_act,
            col_format=col_fmt,
            row_format=row_fmt,
            value_mode=val_mode
        )

        if not matrix_df.is_empty():
            st.markdown("#### 📊 マトリックス表 (UserID × AppID / PageID)")
            st.dataframe(matrix_df.to_pandas(), width='stretch', height=600)

            # Excel エクスポート
            out_buf = io.BytesIO()
            wb_mat = xlsxwriter.Workbook(out_buf)
            matrix_df.write_excel(workbook=wb_mat, worksheet="UserAppPageMatrix")
            wb_mat.close()
            st.download_button(
                label="📥 マトリックス表をExcel形式でダウンロード (.xlsx)",
                data=out_buf.getvalue(),
                file_name="anaplan_user_app_page_matrix.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_user_app_page_matrix"
            )
        else:
            st.info("条件に一致するマトリックスデータがありません。")

with tab_mod:
    st.markdown("### 全モジュール一覧")
    search_m = st.text_input("🔍 モジュール検索")
    disp_m = modules_df
    if search_m and not disp_m.is_empty():
        disp_m = disp_m.filter(pl.col("name").fill_null("").str.to_lowercase().str.contains(search_m.lower()))
    if not disp_m.is_empty():
        st.dataframe(flatten_struct_list_columns(disp_m).to_pandas(), width='stretch', height=750)
    else:
        st.info("データがありません")

with tab_lst:
    st.markdown("### 全リスト一覧")
    search_l = st.text_input("🔍 リスト検索")
    disp_l = lists_df
    if search_l and not disp_l.is_empty():
        disp_l = disp_l.filter(pl.col("name").fill_null("").str.to_lowercase().str.contains(search_l.lower()))
    if not disp_l.is_empty():
        front_cols = ["name", "itemCount", "numberedList", "productionData", "hasSelectiveAccess", "usedInAppliesTo", "id"]
        st.dataframe(reorder_front_cols(disp_l, front_cols).to_pandas(), width='stretch', height=750)
    else:
        st.info("データがありません")

with tab_li:
    st.markdown("### 全ラインアイテム一覧")
    search_li_text = st.text_input("🔍 ラインアイテム検索 (名前, モジュール名, 数式)")
    disp_li = li_df
    if search_li_text and not disp_li.is_empty():
        s = search_li_text.lower()
        disp_li = disp_li.filter(
            pl.col("name").fill_null("").str.to_lowercase().str.contains(s) |
            pl.col("moduleName").fill_null("").str.to_lowercase().str.contains(s) |
            pl.col("formula").fill_null("").str.to_lowercase().str.contains(s)
        )

    if st.button("🤖 AIでPLANS原則違反を監査する (表示中の数式)", help="絞り込まれた数式をGemini APIに送信し、Anaplanのベストプラクティス違反を診断します。"):
        if disp_li.is_empty():
            st.warning("監査対象のデータがありません。")
        elif disp_li.height > 50:
            st.warning(f"数式が多すぎます ({disp_li.height}件)。APIリミットを避けるため、検索ボックスで50件以下に絞り込んでください。")
        else:
            formulas = disp_li.filter(pl.col("formula").is_not_null() & (pl.col("formula") != ""))["formula"].to_list()
            if not formulas:
                st.info("数式が設定されているラインアイテムがありません。")
            else:
                with st.spinner("Gemini Flash が数式を解析中..."):
                    report = run_ai_audit(formulas)
                st.markdown("#### 🤖 AI Audit Report")
                st.markdown(report)

    if not disp_li.is_empty():
        front_cols = ["moduleName", "name", "formula", "cellCount", "estimated_size_mb", "is_summary_optimization_candidate", "id"]
        st.dataframe(reorder_front_cols(disp_li, front_cols).to_pandas(), width='stretch', height=750)
    else:
        st.info("データがありません")

with tab_imp:
    imports_df = actions_dfs.get("imports", pl.DataFrame())
    if not imports_df.is_empty():
        imports_df = build_details_column(
            imports_df,
            field_specs=[("columnCount", "Cols: {}"), ("columnSeparator", "Sep: '{}'")],
            nested_col="source"
        )
        display_cols = ["name", "importType", "sourceFileName", "details", "id"] if "sourceFileName" in imports_df.columns else ["name", "importType", "details", "id"]
    else:
        display_cols = ["name", "id"]

    render_dataframe_tab(
        df=imports_df,
        tab_title="Imports (データ更新)",
        search_placeholder="インポート名で検索",
        search_key="imp_search",
        empty_msg="No imports found.",
        display_cols=display_cols
    )

with tab_proc:
    processes_df = actions_dfs.get("processes", pl.DataFrame())
    if not processes_df.is_empty() and "steps" in processes_df.columns:
        # stepsは dict の list。name/actionType を抽出して改行区切りの詳細行にする
        def format_steps(steps_list):
            if steps_list is None:
                return ""
            try:
                if hasattr(steps_list, "to_list"):
                    steps_list = steps_list.to_list()
                if len(steps_list) == 0:
                    return ""
                lines = []
                for s in steps_list:
                    if not isinstance(s, dict):
                        lines.append(str(s))
                        continue
                    step_name = s.get("name", "Unknown")
                    action_type = s.get("actionType", "")
                    lines.append(f"[{action_type}] {step_name}" if action_type else step_name)
                return "\n".join(lines)
            except Exception:
                return str(steps_list)

        processes_df = processes_df.with_columns(
            pl.col("steps").map_elements(format_steps, return_dtype=pl.Utf8).alias("step_details")
        )

    st.caption(
        "ℹ️ Anaplan APIのインポート/エクスポートメタデータにはソース側の情報（ファイル列名等）のみが含まれ、"
        "更新先のモジュール・ラインアイテムを示す情報は含まれていません（実データで確認済み）。"
        "そのためstep_detailsではモジュール/ラインアイテムの特定はできず、actionTypeとステップ名のみを表示しています。"
    )
    render_dataframe_tab(
        df=processes_df,
        tab_title="Processes (一連の処理)",
        search_placeholder="プロセス名で検索",
        search_key="proc_search",
        empty_msg="No processes found.",
        display_cols=["name", "step_details", "id"]
    )

with tab_exp:
    exports_df = actions_dfs.get("exports", pl.DataFrame())
    if not exports_df.is_empty():
        exports_df = build_details_column(
            exports_df,
            field_specs=[("rowCount", "Rows: {}"), ("columnCount", "Cols: {}"), ("separator", "Sep: '{}'")]
        )
        display_cols = ["name", "exportFormat", "details", "id"]
    else:
        display_cols = ["name", "id"]

    render_dataframe_tab(
        df=exports_df,
        tab_title="Exports (データ出力)",
        search_placeholder="エクスポート名で検索",
        search_key="exp_search",
        empty_msg="No exports found.",
        display_cols=display_cols
    )

with tab_act:
    actions_df = actions_dfs.get("actions", pl.DataFrame())
    if not actions_df.is_empty():
        actions_df = build_details_column(
            actions_df,
            field_specs=[("actionType", "Type: {}"), ("listId", "TargetList: {}")]
        )
        display_cols = ["name", "details", "id"]
    else:
        display_cols = ["name", "id"]

    render_dataframe_tab(
        df=actions_df,
        tab_title="Actions (その他のアクション)",
        search_placeholder="アクション名で検索",
        search_key="act_search",
        empty_msg="No other actions found.",
        display_cols=display_cols
    )
with tab_diff:
    st.markdown("### DEV / PROD モデル間差分比較 (Model Diff)")
    st.info("現在表示中のモデル（Base）と、指定した比較先モデル（Compare）のメタデータ差分をオンザフライで計算します。")

    col1, col2 = st.columns(2)
    with col1:
        comp_ws = st.text_input("Compare Workspace ID", value=workspace_id, key="diff_ws")
    with col2:
        comp_mod = st.text_input("Compare Model ID", value="", placeholder="Enter target Model ID to compare", key="diff_mod")

    if st.button("🔄 Run Diff Analysis"):
        if not comp_mod:
            st.warning("Compare Model ID を入力してください。")
        elif comp_mod == model_id:
            st.warning("Base と Compare で同じ Model ID が指定されています。")
        else:
            with st.spinner("Fetching compare model data..."):
                try:
                    _, _, _, _, _, c_lists, c_modules, c_li, _, _ = fetch_all_model_data(username, password, comp_ws, comp_mod)

                    st.success("Comparison data fetched successfully!")

                    st.markdown("#### 📦 Module Diff")
                    mod_diff = compare_dataframes(
                        modules_df, c_modules,
                        join_keys=["name"],
                        compare_cols=["line_item_count", "total_cell_count", "dimensions"]
                    )
                    st.dataframe(mod_diff.to_pandas(), width='stretch')

                    st.markdown("#### 📋 List Diff")
                    list_diff = compare_dataframes(
                        lists_df, c_lists,
                        join_keys=["name"],
                        compare_cols=["itemCount", "numberedList", "productionData"]
                    )
                    st.dataframe(list_diff.to_pandas(), width='stretch')

                    st.markdown("#### 🧮 Line Item Diff")
                    # Line Item names might duplicate across modules, so use moduleName + name as composite key conceptually.
                    li_diff = compare_dataframes(
                        li_df, c_li,
                        join_keys=["moduleName", "name"],
                        compare_cols=["formula", "cellCount", "summary", "timeScale"]
                    )
                    st.dataframe(li_diff.to_pandas(), width='stretch')

                except Exception as e:
                    import traceback
                    st.error(f"Failed to fetch compare model data: {e}")
                    st.code(traceback.format_exc())

with tab_cap:
    st.markdown("### 💾 Storage Info (ワークスペースとモデルのサイズ)")
    if ws_details:
        ws_name = ws_details.get("name", "Unknown Workspace")
        ws_current_gb = ws_details.get("currentSize", 0) / (1024**3)
        ws_allowance_gb = ws_details.get("sizeAllowance", 0) / (1024**3)

        st.markdown(f"#### Workspace: {ws_name}")
        col1, col2 = st.columns(2)
        col1.metric("Current Size (GB)", f"{ws_current_gb:.2f} GB")
        col2.metric("Size Allowance (GB)", f"{ws_allowance_gb:.2f} GB")

        if ws_allowance_gb > 0:
            st.progress(min(ws_current_gb / ws_allowance_gb, 1.0))
    else:
        st.warning("Workspace details not found or API did not return tenantDetails.")

    st.divider()

    if model_details:
        mod_name = model_details.get("name", "Unknown Model")
        mod_memory_gb = model_details.get("memoryUsage", 0) / (1024**3)
        st.markdown(f"#### Model: {mod_name}")
        st.metric("Memory Usage (GB)", f"{mod_memory_gb:.2f} GB")
    else:
        st.warning("Model details not found or API did not return modelDetails.")

    st.divider()

    st.markdown("### 容量・スパースティ精密シミュレーター (Workspace Footprint)")
    st.info("Line Itemのセル数から推定されるメモリ消費量（MB）を可視化し、モデルの最適化（スパースティ削減やSummary無効化）のターゲットを特定します。※ 1セル=8バイトとして簡易計算")

    if "estimated_size_mb" in modules_df.columns and not modules_df.is_empty():
        total_model_mb = modules_df["estimated_size_mb"].sum()
        st.metric("Model Total Estimated Size (MB)", f"{total_model_mb:,.2f} MB")

        st.markdown("#### 🏋️ Heaviest Modules (Top 10)")
        top_modules = modules_df.sort("estimated_size_mb", descending=True).head(10)

        # グラフ描画用にPandasに変換して name をインデックスにする
        chart_data = top_modules.select(["name", "estimated_size_mb"]).to_pandas().set_index("name")
        st.bar_chart(chart_data)

        st.markdown("#### ⚠️ Optimization Candidates (Summary OFF推論)")
        opt_candidates = modules_df.filter(pl.col("opt_candidates_count") > 0).sort("opt_candidates_count", descending=True)
        if not opt_candidates.is_empty():
            st.warning(f"{opt_candidates.height}個のモジュールに、最適化（Summary=None）できる可能性のあるLine Itemが含まれています。")
            st.dataframe(opt_candidates.select(["name", "opt_candidates_count", "estimated_size_mb"]).to_pandas(), width='stretch')
        else:
            st.success("最適化候補（明らかなSummary設定の無駄）は見つかりませんでした。")
    else:
        st.warning("容量データが計算されていません。")

with tab_unused:
    st.markdown("### 🗑️ 未使用の可能性があるオブジェクト")
    st.warning(
        "⚠️ ここに表示される項目は、あくまで**メタデータ上の手がかりに基づく候補**です。断定ではありません。"
        "特にLine Item判定は、レポート/ダッシュボードの最終表示列（他の数式からは参照されないが意図的に使われている）や、"
        "Importの書き込み先列（このモデルでは実データ上、書き込み先を判別する情報がAPIに含まれないことを確認済み）を"
        "誤って「未使用」と表示することがあります。**削除前に必ずAnaplan UI側で手動確認してください。**"
    )

    st.markdown("#### 📋 未使用の可能性があるList")
    st.caption("どのModule/Line ItemのAppliesToにも使われていないList（`usedInAppliesTo`が空）。")
    if not lists_df.is_empty() and "usedInAppliesTo" in lists_df.columns:
        unused_lists = lists_df.filter(pl.col("usedInAppliesTo").fill_null("") == "")
        if unused_lists.is_empty():
            st.success("該当するListはありません。")
        else:
            st.warning(f"{unused_lists.height}件のListが未使用の可能性があります。")
            st.dataframe(unused_lists.select(["name", "itemCount", "id"]).to_pandas(), width='stretch')
    else:
        st.info("List情報が取得できていません。")

    st.divider()

    st.markdown("#### 🧮 未使用の可能性があるLine Item")
    st.caption("他のどの数式からも参照されていないLine Item（`referencedBy`が空）。")
    if not li_df.is_empty() and "referencedBy" in li_df.columns:
        unused_li = li_df.filter(pl.col("referencedBy").list.len() == 0)
        if unused_li.is_empty():
            st.success("該当するLine Itemはありません。")
        else:
            st.warning(f"{unused_li.height}件のLine Itemが未使用の可能性があります。")
            cols = [c for c in ["moduleName", "name", "formula", "cellCount", "id"] if c in unused_li.columns]
            st.dataframe(unused_li.select(cols).to_pandas(), width='stretch', height=500)
    else:
        st.info("Line Item情報が取得できていません。")

    st.divider()

    st.markdown("#### ⚙️ どのProcessのステップにも含まれないAction")
    st.caption(
        "Import/Export/その他Actionのうち、どのProcessのステップにも組み込まれていないもの。"
        "ダッシュボード等から手動実行されるActionも該当するため、これも未使用の確定情報ではありません。"
    )
    processes_raw = actions_dfs.get("processes", pl.DataFrame())
    step_ids_in_processes: set[str] = set()
    if not processes_raw.is_empty() and "steps" in processes_raw.columns:
        for steps_list in processes_raw["steps"].to_list():
            if not steps_list:
                continue
            for step in steps_list:
                if isinstance(step, dict) and step.get("id"):
                    step_ids_in_processes.add(step["id"])

    standalone_rows = []
    for action_type, label in [("imports", "Import"), ("exports", "Export"), ("actions", "Action")]:
        action_df = actions_dfs.get(action_type, pl.DataFrame())
        if action_df.is_empty() or "id" not in action_df.columns:
            continue
        for row in action_df.select(["id", "name"]).iter_rows(named=True):
            if row["id"] not in step_ids_in_processes:
                standalone_rows.append({"type": label, "name": row["name"], "id": row["id"]})

    if not standalone_rows:
        st.success("該当するActionはありません（全てのImport/Export/Actionが何らかのProcessに組み込まれています）。")
    else:
        standalone_df = pl.DataFrame(standalone_rows)
        st.warning(f"{standalone_df.height}件のActionがどのProcessのステップにも含まれていません。")
        st.dataframe(standalone_df.to_pandas(), width='stretch', height=400)

    st.divider()

    st.markdown("#### 📦 未使用の可能性があるModule")
    st.caption(
        "含まれる全Line Itemが未参照（上記と同じ判定）、かつ他モジュールからも参照されておらず、"
        "Importの更新先としても推定されていないModule。判定項目が多いため、上記2つより誤検知の可能性が高くなります。"
    )
    if not modules_df.is_empty() and not li_df.is_empty() and "referencedBy" in li_df.columns:
        li_used_flag = li_df.group_by("moduleId").agg(
            (pl.col("referencedBy").list.len() > 0).any().alias("has_referenced_line_item")
        )
        referenced_module_ids = set(edges_m.filter(pl.col("label") == "referenced_by")["target"].to_list()) if not edges_m.is_empty() else set()
        updated_module_ids = set(edges_m.filter(pl.col("label") == "updates (inferred)")["target"].to_list()) if not edges_m.is_empty() else set()

        mod_check = modules_df.join(li_used_flag, left_on="id", right_on="moduleId", how="left").with_columns(
            pl.col("has_referenced_line_item").fill_null(False)
        )
        unused_modules = mod_check.filter(
            (~pl.col("has_referenced_line_item"))
            & (~pl.col("id").is_in(referenced_module_ids))
            & (~pl.col("id").is_in(updated_module_ids))
        )
        if unused_modules.is_empty():
            st.success("該当するModuleはありません。")
        else:
            st.warning(f"{unused_modules.height}個のModuleが未使用の可能性があります。")
            st.dataframe(unused_modules.select(["name", "line_item_count", "id"]).to_pandas(), width='stretch')
    else:
        st.info("判定に必要なデータが取得できていません。")
# trigger reload
