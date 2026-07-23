"""Tests for generate_dashboard.py — DashboardGenerator (standalone CSV→HTML)."""
from pathlib import Path

import polars as pl

from libs.common.audit_html import AuditDashboardGenerator as DashboardGenerator


def _write_sample_csv(path: Path) -> Path:
    """テスト用サンプルCSVを生成する。"""
    df = pl.DataFrame({
        "User": ["user_a", "user_b", "user_c", "user_a"],
        "ID": [150, 80, 30, 50],
        "First Name": ["Alice", "Bob", "Carol", "Alice"],
        "Last Name": ["Smith", "Jones", "Brown", "Smith"],
        "Model Role": ["Admin", "User", "User", "Admin"],
        "Model": ["SOP_TR", "SOP_TR", "SOP_PRD", "SOP_PRD"],
    })
    df.write_csv(path)
    return path


# ── initialization ────────────────────────────────────────────────────────────

class TestDashboardGeneratorInit:
    def test_loads_csv_on_init(self, tmp_path: Path) -> None:
        """初期化時にCSVを読み込んでDataFrameを保持する。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)

        assert isinstance(gen.df, pl.DataFrame)
        assert len(gen.df) == 4

    def test_csv_path_stored(self, tmp_path: Path) -> None:
        """csv_pathが正しく保存される。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        assert gen.csv_path == csv


# ── generate ─────────────────────────────────────────────────────────────────

class TestDashboardGeneratorGenerate:
    def test_generates_html_file(self, tmp_path: Path) -> None:
        """generate()がHTMLファイルを生成する。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        out = gen.generate(tmp_path / "dashboard.html")

        assert out.exists()

    def test_default_output_path(self, tmp_path: Path) -> None:
        """output_pathを省略すると同ディレクトリに _dashboard.html が生成される。"""
        csv = _write_sample_csv(tmp_path / "summary.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        out = gen.generate(tmp_path / "summary_dashboard.html")

        assert out.name == "summary_dashboard.html"
        assert out.exists()

    def test_returns_output_path(self, tmp_path: Path) -> None:
        """generate()が出力パスを返す。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        result = gen.generate(tmp_path / "out.html")

        assert isinstance(result, Path)

    def test_html_contains_doctype(self, tmp_path: Path) -> None:
        """生成されたHTMLがDOCTYPE宣言を含む。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        gen.generate(tmp_path / "out.html")

        content = (tmp_path / "out.html").read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_html_contains_total_users(self, tmp_path: Path) -> None:
        """総ユーザー数がHTMLに含まれる。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        gen.generate(tmp_path / "out.html")

        content = (tmp_path / "out.html").read_text(encoding="utf-8")
        # 4行 = 4ユーザーエントリ
        assert "4" in content

    def test_html_contains_model_names(self, tmp_path: Path) -> None:
        """モデル名がHTMLに含まれる。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        gen.generate(tmp_path / "out.html")

        content = (tmp_path / "out.html").read_text(encoding="utf-8")
        assert "SOP_TR" in content
        assert "SOP_PRD" in content

    def test_html_contains_csv_filename(self, tmp_path: Path) -> None:
        """データソースのCSVファイル名がHTMLに含まれる。"""
        csv = _write_sample_csv(tmp_path / "audit_summary.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        gen.generate(tmp_path / "out.html")

        content = (tmp_path / "out.html").read_text(encoding="utf-8")
        assert "audit_summary.csv" in content

    def test_html_is_utf8(self, tmp_path: Path) -> None:
        """HTMLがUTF-8で書き込まれ、日本語が含まれる。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        gen.generate(tmp_path / "out.html")

        content = (tmp_path / "out.html").read_text(encoding="utf-8")
        assert "Model" in content or "User" in content


# ── _generate_model_summary_table ────────────────────────────────────────────

class TestModelSummaryTable:
    def test_returns_html_string(self, tmp_path: Path) -> None:
        """_generate_model_summary_table()がHTML文字列を返す。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        result = gen._generate_model_summary_table()

        assert isinstance(result, str)
        assert "<table>" in result

    def test_contains_model_names(self, tmp_path: Path) -> None:
        """テーブルに全モデル名が含まれる。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        result = gen._generate_model_summary_table()

        assert "SOP_TR" in result
        assert "SOP_PRD" in result

    def test_aggregates_actions_correctly(self, tmp_path: Path) -> None:
        """ID列の合計が正しく集計される（SOP_TR: 150+80=230）。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        result = gen._generate_model_summary_table()

        assert "230" in result  # SOP_TRの合計


# ── _generate_user_activity_table ────────────────────────────────────────────

class TestUserActivityTable:
    def test_returns_html_string(self, tmp_path: Path) -> None:
        """_generate_user_activity_table()がHTML文字列を返す。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        result = gen._generate_user_activity_table()

        assert isinstance(result, str)
        assert "<table>" in result

    def test_top_user_appears_first(self, tmp_path: Path) -> None:
        """最多アクションのユーザーが含まれる（user_a: 150）。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        result = gen._generate_user_activity_table()

        assert "user_a" in result

    def test_limits_to_top_20(self, tmp_path: Path) -> None:
        """25ユーザーがいても上位20件のみ表示される。"""
        users = [f"user_{i:02d}" for i in range(25)]
        ids = list(range(25, 0, -1))  # 25, 24, ..., 1
        df = pl.DataFrame({
            "User": users,
            "ID": ids,
            "First Name": ["N/A"] * 25,
            "Last Name": ["N/A"] * 25,
            "Model Role": ["User"] * 25,
            "Model": ["SOP_TR"] * 25,
        })
        csv = tmp_path / "large.csv"
        df.write_csv(csv)

        gen = DashboardGenerator(pl.read_csv(csv), csv)
        result = gen._generate_user_activity_table()

        # 21位以降(ID=5以下)のユーザーは含まれない
        assert "user_24" not in result  # ID=1, 最下位

    def test_activity_bar_in_html(self, tmp_path: Path) -> None:
        """アクティビティバーのdivがHTMLに含まれる。"""
        csv = _write_sample_csv(tmp_path / "data.csv")
        gen = DashboardGenerator(pl.read_csv(csv), csv)
        result = gen._generate_user_activity_table()

        assert "activity-bar" in result
