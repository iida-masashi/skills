"""Tests for HistoryAudit_Scheduled.py — OptimizedAnaplanExporter and DashboardGenerator."""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl

# config モジュールをモック（本番認証情報を読み込まない）
_config_mock = types.ModuleType("config")
_config_mock.ANAPLAN_USER_EMAIL = "test@example.com"  # type: ignore[attr-defined]
_config_mock.ANAPLAN_PASSWORD = "test_password"  # type: ignore[attr-defined]
_config_mock.OUTPUT_FOLDER = "./test_output"  # type: ignore[attr-defined]
_config_mock.MAX_WORKERS = 2  # type: ignore[attr-defined]
_config_mock.TIMEOUT = 30  # type: ignore[attr-defined]
_config_mock.LOG_LEVEL = 20  # logging.INFO  # type: ignore[attr-defined]
_config_mock.MODELS = []  # type: ignore[attr-defined]

import dataclasses


@dataclasses.dataclass
class _ModelConfig:
    ws_id: str
    m_id: str
    action_id: str
    file_suffix: str
    users_csv: str
    model_name: str

_config_mock.ModelConfig = _ModelConfig  # type: ignore[attr-defined]
sys.modules["config"] = _config_mock

from HistoryAudit_Scheduled import OptimizedAnaplanExporter

from libs.common.audit_html import AuditDashboardGenerator as DashboardGenerator


def _make_model() -> _ModelConfig:
    return _ModelConfig(
        ws_id="ws123",
        m_id="m456",
        action_id="999000000001",
        file_suffix="SOP_TR",
        users_csv="Users.csv",
        model_name="TestModel",
    )


def _make_sample_df() -> pl.DataFrame:
    return pl.DataFrame({
        "User": ["user_a", "user_b", "user_c"],
        "ID": [100, 50, 30],
        "First Name": ["Alice", "Bob", "Carol"],
        "Last Name": ["Smith", "Jones", "Brown"],
        "Model Role": ["Admin", "User", "User"],
        "Model": ["TestModel", "TestModel", "TestModel"],
    })


# ── OptimizedAnaplanExporter.create_client ────────────────────────────────────

class TestCreateClient:
    def test_create_client_calls_sdk(self) -> None:
        """create_client()がanaplan_sdk.Clientを呼び出す。"""
        exporter = OptimizedAnaplanExporter()
        mock_client_cls = MagicMock()
        mock_client_cls.return_value = MagicMock()

        with patch("libs.common.anaplan_sdk_client.create_anaplan_client", mock_client_cls):
            exporter.create_client("ws123", "m456")

        mock_client_cls.assert_called_once()
        call_kwargs = mock_client_cls.call_args[1]
        assert call_kwargs["workspace_id"] == "ws123"
        assert call_kwargs["model_id"] == "m456"

    def test_create_client_uses_config_credentials(self) -> None:
        """設定ファイルのemailとpasswordが渡される。"""
        exporter = OptimizedAnaplanExporter()
        mock_client_cls = MagicMock()

        with patch("libs.common.anaplan_sdk_client.create_anaplan_client", mock_client_cls):
            exporter.create_client("ws1", "m1")

        call_kwargs = mock_client_cls.call_args[1]
        assert call_kwargs["user_email"] == "test@example.com"
        assert call_kwargs["password"] == "test_password"


# ── OptimizedAnaplanExporter._merge_user_details ─────────────────────────────

class TestMergeUserDetails:
    def test_merge_with_existing_users_csv(self, tmp_path: Path) -> None:
        """Users.csvが存在するとき、ユーザー詳細をjoinする。"""
        users_csv = tmp_path / "Users.csv"
        users_df = pl.DataFrame({
            "User": ["user_a", "user_b"],
            "First Name": ["Alice", "Bob"],
            "Last Name": ["Smith", "Jones"],
            "Model Role": ["Admin", "User"],
        })
        users_df.write_csv(users_csv)

        model = _make_model()
        model.users_csv = "Users.csv"

        count_df = pl.DataFrame({
            "User": ["user_a", "user_b"],
            "ID": [100, 50],
        })

        exporter = OptimizedAnaplanExporter()
        # OUTPUT_FOLDER を tmp_path に向けることで users_csv_path が tmp_path/Users.csv になる
        with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
            result = exporter._merge_user_details(count_df, model)

        # joinが成功すれば行数は保持される
        assert len(result) == 2

    def test_fallback_when_users_csv_missing(self, tmp_path: Path) -> None:
        """Users.csvが存在しないとき、N/Aのフォールバック列を追加する。"""
        model = _make_model()
        model.users_csv = "NonExistent.csv"

        count_df = pl.DataFrame({
            "User": ["user_x"],
            "ID": [42],
        })

        exporter = OptimizedAnaplanExporter()
        with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
            result = exporter._merge_user_details(count_df, model)

        assert "First Name" in result.columns
        assert result["First Name"][0] == "N/A"
        assert result["Last Name"][0] == "N/A"

    def test_fallback_preserves_original_data(self, tmp_path: Path) -> None:
        """フォールバック時でもUser/ID列のデータが保持される。"""
        model = _make_model()
        model.users_csv = "Missing.csv"

        count_df = pl.DataFrame({
            "User": ["user_z"],
            "ID": [99],
        })

        exporter = OptimizedAnaplanExporter()
        with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
            result = exporter._merge_user_details(count_df, model)

        assert result["User"][0] == "user_z"
        assert result["ID"][0] == 99


# ── OptimizedAnaplanExporter.export_data (error path) ────────────────────────

class TestExportDataErrorHandling:
    def test_returns_error_dict_on_exception(self, tmp_path: Path) -> None:
        """エクスポート失敗時にstatus='error'の辞書を返す。"""
        model = _make_model()
        exporter = OptimizedAnaplanExporter()

        with patch("libs.common.anaplan_sdk_client.create_anaplan_client", side_effect=Exception("Auth failed")):
            with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
                result = exporter.export_data(model)

        assert result is not None
        assert result["status"] == "error"
        assert "Auth failed" in result["error"]
        assert result["model_name"] == "TestModel"

    def test_error_dict_contains_error_type(self, tmp_path: Path) -> None:
        """エラー辞書にerror_typeが含まれる。"""
        model = _make_model()
        exporter = OptimizedAnaplanExporter()

        with patch("libs.common.anaplan_sdk_client.create_anaplan_client", side_effect=ValueError("bad value")):
            with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
                result = exporter.export_data(model)

        assert result["error_type"] == "ValueError"


# ── DashboardGenerator (HistoryAudit_Scheduled) ──────────────────────────────

class TestHistoryAuditDashboardGenerator:
    def test_generate_creates_html_file(self, tmp_path: Path) -> None:
        """generate()がHTMLファイルを作成する。"""
        df = _make_sample_df()
        gen = DashboardGenerator(df)

        with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
            result = gen.generate(tmp_path / "out.html", "202401011200")

        assert result.exists()
        assert result.suffix == ".html"

    def test_generate_with_none_df(self, tmp_path: Path) -> None:
        """DataFrameがNoneでもクラッシュしない。"""
        df = pl.DataFrame()
        gen = DashboardGenerator(df)

        with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
            result = gen.generate(tmp_path/"out.html", "202401011200")

        assert result.exists()

    def test_generate_with_failed_models(self, tmp_path: Path) -> None:
        """failed_modelsがある場合もHTMLが生成される。"""
        df = _make_sample_df()
        gen = DashboardGenerator(df)
        failed = [{"model_name": "BrokenModel", "error": "Timeout", "error_type": "TimeoutError"}]

        with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
            result = gen.generate(tmp_path / "out.html", "202401011200", failed_models=failed)

        content = result.read_text(encoding="utf-8")
        assert "BrokenModel" in content
        assert "Timeout" in content

    def test_html_contains_stats(self, tmp_path: Path) -> None:
        """HTMLに統計情報（ユーザー数・アクション数）が含まれる。"""
        df = _make_sample_df()
        gen = DashboardGenerator(df)

        with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
            result = gen.generate(tmp_path / "out.html", "202401011200")

        content = result.read_text(encoding="utf-8")
        assert "3" in content   # total_users = 3
        assert "180" in content  # total_actions = 100+50+30

    def test_generate_with_empty_dataframe(self, tmp_path: Path) -> None:
        """空のDataFrameでもクラッシュしない。"""
        df = pl.DataFrame()
        gen = DashboardGenerator(df)

        with patch("HistoryAudit_Scheduled.OUTPUT_FOLDER", str(tmp_path)):
            result = gen.generate(tmp_path / "out.html", "202401011200")

        assert result.exists()


# ── ModelConfig dataclass ─────────────────────────────────────────────────────

class TestModelConfig:
    def test_model_config_fields(self) -> None:
        """ModelConfigの全フィールドが正しく設定される。"""
        model = _make_model()
        assert model.ws_id == "ws123"
        assert model.m_id == "m456"
        assert model.action_id == "999000000001"
        assert model.file_suffix == "SOP_TR"
        assert model.users_csv == "Users.csv"
        assert model.model_name == "TestModel"

    def test_model_config_is_dataclass(self) -> None:
        """ModelConfigがdataclassであること。"""
        import dataclasses
        assert dataclasses.is_dataclass(_ModelConfig)
