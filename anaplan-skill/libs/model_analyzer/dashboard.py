import hashlib
import html
import os
import tempfile

import networkx as nx
import polars as pl
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from pyvis.network import Network

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', '.env'))
load_dotenv(env_path)

from libs.model_analyzer.analyzer import AnaplanConfig, AnaplanModelAnalyzer
from libs.model_analyzer.diff_engine import compare_dataframes

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



import concurrent.futures
import threading

from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx


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

import io

import xlsxwriter


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

st.title("Anaplan Data Model Analyzer")

st.sidebar.header("1. Connection Settings")
default_ws = os.environ.get("ANAPLAN_WS", "")
default_mod = os.environ.get("ANAPLAN_MODEL", "")
workspace_id = st.sidebar.text_input("Workspace ID", value=default_ws)
model_id = st.sidebar.text_input("Model ID", value=default_mod)

username = os.environ.get("ANAPLAN_USER", os.environ.get("ANAPLAN_USERNAME", ""))
password = os.environ.get("ANAPLAN_PASSWORD", "")

if not username or not password:
    st.error("ANAPLAN_USERNAME または ANAPLAN_PASSWORD が環境変数に設定されていません。")
    st.stop()

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

from google import genai


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
        if display_cols:
            cols = disp_df.columns
            ordered_cols = [c for c in display_cols if c in cols] + [c for c in cols if c not in display_cols]
            st.dataframe(disp_df.select(ordered_cols).to_pandas(), width='stretch', height=700)
        else:
            st.dataframe(disp_df.to_pandas(), width='stretch', height=700)

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

    # JS Injection for Double-click Fullscreen
    fullscreen_js = """
    <script type="text/javascript">
      // Double click on the network container to enter fullscreen
      document.getElementById('mynetwork').addEventListener('dblclick', function(e) {
          if (!document.fullscreenElement) {
              this.requestFullscreen().catch(err => {
                  console.log(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`);
              });
          } else {
              document.exitFullscreen();
          }
      });
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
tab_net_m, tab_net_li, tab_mat, tab_mod, tab_lst, tab_li, tab_imp, tab_proc, tab_exp, tab_act, tab_diff, tab_cap = st.tabs([
    "🌐 Module Network",
    "🕸️ Line Item Network",
    "🧩 Matrices",
    "📦 Modules",
    "📋 Lists",
    "🧮 Line Items",
    "📥 Imports",
    "🔄 Processes",
    "📤 Exports",
    "⚙️ Actions",
    "⚖️ Model Diff",
    "📊 Capacity"
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

with tab_mod:
    st.markdown("### 全モジュール一覧")
    search_m = st.text_input("🔍 モジュール検索")
    disp_m = modules_df
    if search_m and not disp_m.is_empty():
        disp_m = disp_m.filter(pl.col("name").fill_null("").str.to_lowercase().str.contains(search_m.lower()))
    if not disp_m.is_empty():
        st.dataframe(disp_m.to_pandas(), width='stretch', height=750)
    else:
        st.info("データがありません")

with tab_lst:
    st.markdown("### 全リスト一覧")
    search_l = st.text_input("🔍 リスト検索")
    disp_l = lists_df
    if search_l and not disp_l.is_empty():
        disp_l = disp_l.filter(pl.col("name").fill_null("").str.to_lowercase().str.contains(search_l.lower()))
    if not disp_l.is_empty():
        # カラムの並び替え（詳細メタデータがある場合は前に持ってくる）
        cols = disp_l.columns
        front_cols = ["name", "itemCount", "numberedList", "productionData", "hasSelectiveAccess", "usedInAppliesTo", "id"]
        ordered_cols = [c for c in front_cols if c in cols] + [c for c in cols if c not in front_cols]
        st.dataframe(disp_l.select(ordered_cols).to_pandas(), width='stretch', height=750)
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
        cols = disp_li.columns
        front_cols = ["moduleName", "name", "formula", "cellCount", "estimated_size_mb", "is_summary_optimization_candidate", "id"]
        ordered_cols = [c for c in front_cols if c in cols] + [c for c in cols if c not in front_cols]
        st.dataframe(disp_li.select(ordered_cols).to_pandas(), width='stretch', height=750)
    else:
        st.info("データがありません")

with tab_imp:
    imports_df = actions_dfs.get("imports", pl.DataFrame())
    if not imports_df.is_empty():
        def format_import_details(row):
            parts = []
            src = row.get("source")
            if isinstance(src, dict):
                if "columnCount" in src:
                    parts.append(f"Cols: {src['columnCount']}")
                if "columnSeparator" in src:
                    parts.append(f"Sep: '{src['columnSeparator']}'")
            return " | ".join(parts) if parts else ""

        imports_df = imports_df.with_columns(
            pl.struct(imports_df.columns).map_elements(format_import_details, return_dtype=pl.Utf8).alias("details")
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
        # stepsは dict の list。actionName を抽出してカンマ区切りにする
        def format_steps(steps_list):
            if steps_list is None:
                return ""
            try:
                if hasattr(steps_list, "to_list"):
                    steps_list = steps_list.to_list()
                if len(steps_list) == 0:
                    return ""
                # 辞書のリストから actionName を取り出す
                names = [s.get("actionName", "Unknown") if isinstance(s, dict) else str(s) for s in steps_list]
                return ", ".join(names)
            except Exception:
                return str(steps_list)

        processes_df = processes_df.with_columns(
            pl.col("steps").map_elements(format_steps, return_dtype=pl.Utf8).alias("step_details")
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
        def format_export_details(row):
            parts = []
            if row.get("rowCount"):
                parts.append(f"Rows: {row['rowCount']}")
            if row.get("columnCount"):
                parts.append(f"Cols: {row['columnCount']}")
            if row.get("separator"):
                parts.append(f"Sep: '{row['separator']}'")
            return " | ".join(parts) if parts else ""

        exports_df = exports_df.with_columns(
            pl.struct(exports_df.columns).map_elements(format_export_details, return_dtype=pl.Utf8).alias("details")
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
        def format_action_details(row):
            parts = []
            if row.get("actionType"):
                parts.append(f"Type: {row['actionType']}")
            if row.get("listId"):
                parts.append(f"TargetList: {row['listId']}")
            return " | ".join(parts) if parts else ""

        actions_df = actions_df.with_columns(
            pl.struct(actions_df.columns).map_elements(format_action_details, return_dtype=pl.Utf8).alias("details")
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
# trigger reload
