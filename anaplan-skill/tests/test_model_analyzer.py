import polars as pl

from libs.model_analyzer.analyzer import AnaplanConfig, AnaplanModelAnalyzer


def test_extract_nodes_and_edges(mocker):
    config = AnaplanConfig(user="test", password="test", workspace_id="w1", model_id="m1")
    # Mock the authenticator to avoid network calls during initialization or fetch
    mocker.patch("libs.model_analyzer.analyzer.AnaplanAuthenticator.get_token", return_value="dummy_token")

    analyzer = AnaplanModelAnalyzer(config)

    # Mock API responses
    mocker.patch.object(
        analyzer,
        "fetch_modules",
        return_value=[{"id": "m1", "name": "Module A"}],
    )
    mocker.patch.object(
        analyzer,
        "fetch_line_items",
        return_value=[
            {
                "id": "li1",
                "name": "Line Item 1",
                "moduleId": "m1",
                "moduleName": "Module A",
                "referencedBy": [{"id": "li2", "name": "Module B.Line Item 2"}]
            }
        ],
    )
    mocker.patch.object(
        analyzer,
        "fetch_actions",
        return_value={
            "imports": [{"id": "imp1", "name": "Import into Module A", "sourceFileName": "data.csv"}],
            "processes": [{"id": "proc1", "name": "Main Process", "steps": [{"actionId": "imp1", "actionName": "Import into Module A"}]}]
        }
    )

    nodes_df, edges_df, actions_dfs = analyzer.extract_nodes_and_edges(level="module")

    assert isinstance(nodes_df, pl.DataFrame)
    assert isinstance(edges_df, pl.DataFrame)
    assert isinstance(actions_dfs, dict)
    assert "imports" in actions_dfs

    # Node contents check
    # 1 Module + 1 Import + 1 File + 1 Process = 4 nodes
    assert nodes_df.height == 4
    node_labels = nodes_df["label"].to_list()
    assert "Module A" in node_labels
    assert "📥 Import into Module A" in node_labels
    assert "📄 data.csv" in node_labels
    assert "🔄 Main Process" in node_labels

    # Edge contents check
    # 1 File->Import + 1 Import->Module (inferred) + 1 Process->Import (executes) = 3 edges
    assert edges_df.height == 3
    assert edges_df.filter(pl.col("label") == "reads_from").height == 1
    assert edges_df.filter(pl.col("label") == "updates (inferred)").height == 1
    assert edges_df.filter(pl.col("label") == "executes").height == 1

def test_enrich_modules_with_line_items(mocker):
    config = AnaplanConfig(user="test", password="test", workspace_id="w1", model_id="m1")
    mocker.patch("libs.model_analyzer.analyzer.AnaplanAuthenticator.get_token", return_value="dummy_token")
    analyzer = AnaplanModelAnalyzer(config)

    modules_df = pl.DataFrame([{"id": "m1", "name": "Module A"}])
    li_df = pl.DataFrame([
        {"id": "li1", "moduleId": "m1", "appliesTo": [{"name": "L1"}, {"name": "L2"}], "timeScale": "MONTH", "cellCount": 100, "formula": "", "summary": "Sum"},
        {"id": "li2", "moduleId": "m1", "appliesTo": [{"name": "L2"}], "timeScale": "DAY", "cellCount": 200, "formula": "A + B", "summary": "None"}
    ])

    enriched = analyzer.enrich_modules_with_line_items(modules_df, li_df)

    assert enriched.height == 1
    assert "line_item_count" in enriched.columns
    assert "total_cell_count" in enriched.columns
    assert "estimated_size_mb" in enriched.columns
    assert "opt_candidates_count" in enriched.columns

    row = enriched.to_dicts()[0]
    assert row["line_item_count"] == 2
    assert row["total_cell_count"] == 300
    assert abs(row["estimated_size_mb"] - (300 * 8) / (1024 * 1024)) < 0.0001
    assert row["opt_candidates_count"] == 1
    assert "L1, L2" in row["dimensions"] or "L2, L1" in row["dimensions"]
    assert "MONTH, DAY" in row["time_scales"] or "DAY, MONTH" in row["time_scales"]

def test_fetch_lists_with_details(mocker):
    config = AnaplanConfig(user="test", password="test", workspace_id="w1", model_id="m1")
    mocker.patch("libs.model_analyzer.analyzer.AnaplanAuthenticator.get_token", return_value="dummy")
    analyzer = AnaplanModelAnalyzer(config)

    # _get_headersのモック
    mocker.patch.object(analyzer, "_get_headers", return_value={})

    # requests.getのモック（1回目はリスト一覧、2回目以降は詳細）
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self):
            return self.json_data

    def mock_get(url, *args, **kwargs):
        if url.endswith("/lists"):
            return MockResponse({"lists": [{"id": "L1", "name": "List 1"}]})
        elif url.endswith("/lists/L1"):
            return MockResponse({"metadata": {"id": "L1", "name": "List 1", "itemCount": 100, "numberedList": True, "productionData": False}})
        return MockResponse({}, 404)

    mocker.patch("requests.get", side_effect=mock_get)

    lists = analyzer.fetch_lists()
    assert len(lists) == 1
    assert lists[0]["itemCount"] == 100
    assert lists[0]["numberedList"] is True

def test_analyzer_memoization(mocker):
    config = AnaplanConfig(user="test", password="test", workspace_id="w1", model_id="m1")
    mocker.patch("libs.model_analyzer.analyzer.AnaplanAuthenticator.get_token", return_value="dummy")
    analyzer = AnaplanModelAnalyzer(config)
    mocker.patch.object(analyzer, "_get_headers", return_value={})

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self): return self.json_data
        def raise_for_status(self): pass

    mock_get = mocker.patch("requests.get", return_value=MockResponse({"modules": [{"id": "m1"}]}))

    res1 = analyzer.fetch_modules()
    assert len(res1) == 1
    assert mock_get.call_count == 1

    res2 = analyzer.fetch_modules()
    assert len(res2) == 1
    # Should not call requests.get again due to memoization
    assert mock_get.call_count == 1

def test_fetch_actions_parallel(mocker):
    config = AnaplanConfig(user="test", password="test", workspace_id="w1", model_id="m1")
    mocker.patch("libs.model_analyzer.analyzer.AnaplanAuthenticator.get_token", return_value="dummy")
    analyzer = AnaplanModelAnalyzer(config)
    mocker.patch.object(analyzer, "_get_headers", return_value={})

    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
        def json(self): return self.json_data

    def mock_get(url, *args, **kwargs):
        if url.endswith("/imports"):
            return MockResponse({"imports": [{"id": "imp1", "name": "Import 1"}]})
        elif url.endswith("/imports/imp1"):
            return MockResponse({"importMetadata": {"columnCount": 3}})
        elif url.endswith("/exports"):
            return MockResponse({"exports": [{"id": "exp1", "name": "Export 1"}]})
        elif url.endswith("/exports/exp1"):
            return MockResponse({"exportMetadata": {"rowCount": 100}})
        elif url.endswith("/processes"):
            return MockResponse({"processes": [{"id": "proc1", "name": "Proc 1"}]})
        elif url.endswith("/processes/proc1"):
            return MockResponse({"processMetadata": {"actions": [{"actionName": "Step 1"}]}})
        elif url.endswith("/actions"):
            return MockResponse({"actions": [{"id": "act1", "name": "Action 1"}]})
        elif url.endswith("/actions/act1"):
            return MockResponse({"action": {"actionType": "DELETE"}})
        elif url.endswith("/files"):
            return MockResponse({"files": [{"id": "f1", "name": "file.txt"}]})
        return MockResponse({}, 404)

    mocker.patch("requests.get", side_effect=mock_get)

    callback_messages = []
    def status_callback(msg):
        callback_messages.append(msg)

    actions = analyzer.fetch_actions(status_callback=status_callback)

    assert "imports" in actions
    assert "exports" in actions
    assert "processes" in actions
    assert "actions" in actions

    assert actions["imports"][0]["columnCount"] == 3
    assert actions["exports"][0]["rowCount"] == 100
    assert actions["processes"][0]["steps"][0]["actionName"] == "Step 1"
    assert actions["actions"][0]["actionType"] == "DELETE"

    assert len(callback_messages) > 0
    assert any("Downloading Imports index..." in m for m in callback_messages)
    assert any("Downloading Import Detail: Import 1" in m for m in callback_messages)

def test_authenticator(mocker):
    from libs.model_analyzer.analyzer import AnaplanAuthenticator, AnaplanConfig
    config = AnaplanConfig(user="test", password="pwd", workspace_id="w", model_id="m")
    auth = AnaplanAuthenticator(config)

    class MockRes:
        def __init__(self, data, code=201):
            self.data = data
            self.status_code = code
        def json(self): return self.data
        @property
        def text(self): return "error"

    mocker.patch("requests.post", return_value=MockRes({"tokenInfo": {"tokenValue": "tok"}}))
    token = auth.get_token()
    assert token == "tok"

    # Should use cached token
    mocker.patch("requests.post", side_effect=Exception("Should not be called"))
    assert auth.get_token() == "tok"

def test_fetch_files(mocker):
    config = AnaplanConfig(user="test", password="pwd", workspace_id="w", model_id="m")
    mocker.patch("libs.model_analyzer.analyzer.AnaplanAuthenticator.get_token", return_value="dummy")
    analyzer = AnaplanModelAnalyzer(config)
    mocker.patch.object(analyzer, "_get_headers", return_value={})

    class MockRes:
        def __init__(self, data, code=200):
            self.data = data
            self.status_code = code
        def json(self): return self.data

    mocker.patch("requests.get", return_value=MockRes({"files": [{"id": "f1"}]}))
    files = analyzer.fetch_files()
    assert len(files) == 1
    assert files[0]["id"] == "f1"
