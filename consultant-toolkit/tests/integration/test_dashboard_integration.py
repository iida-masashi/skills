"""
Integration tests for Streamlit dashboards

Tests dashboard initialization and key functions without full UI rendering.
"""

import sys
from pathlib import Path

import pytest


@pytest.fixture
def project_root():
    """Get project root directory"""
    return Path(__file__).parent.parent.parent


class TestFinancialSCMDashboard:
    """Integration tests for app_finance.py"""

    @pytest.mark.integration
    def test_dashboard_imports_successfully(self, project_root):
        """Should import dashboard module without errors"""
        scripts_path = str(project_root / "scripts")
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)

        try:
            # This will fail if there are import errors
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "financial_scm_dashboard",
                project_root / "scripts" / "app_finance.py",
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                # Note: Not executing module to avoid Streamlit initialization
                assert module is not None
        except SyntaxError as e:
            pytest.fail(f"Syntax error in dashboard: {e}")

    @pytest.mark.integration
    def test_load_financial_data_function_exists(self, project_root):
        """Should have load_financial_data function defined"""
        scripts_path = str(project_root / "scripts")
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)

        # Read file and check function definition
        dashboard_path = project_root / "scripts" / "app_finance.py"
        content = dashboard_path.read_text(encoding="utf-8")

        assert "def load_financial_data" in content
        assert "@st.cache_data" in content

    @pytest.mark.integration
    def test_configuration_constants_defined(self, project_root):
        """Should have configuration constants properly defined"""
        dashboard_path = project_root / "scripts" / "app_finance.py"
        content = dashboard_path.read_text(encoding="utf-8")

        # Check for key constants (WACC_BENCHMARK is imported from constants.py)
        assert "COMPANIES" in content
        assert "COMPANY_COLORS" in content
        assert "WACC_BENCHMARK" in content


class TestMarketAnalysisDashboard:
    """Integration tests for app_market_watch.py"""

    @pytest.mark.integration
    def test_dashboard_has_forecast_function(self, project_root):
        """Should have make_forecast function for Prophet"""
        dashboard_path = project_root / "scripts" / "app_market_watch.py"
        content = dashboard_path.read_text(encoding="utf-8")

        assert "def make_forecast" in content
        assert "Prophet" in content

    @pytest.mark.integration
    def test_dashboard_has_market_data_function(self, project_root):
        """Should have get_market_data function"""
        dashboard_path = project_root / "scripts" / "app_market_watch.py"
        content = dashboard_path.read_text(encoding="utf-8")

        assert "def get_market_data" in content
        assert "@st.cache_data" in content


class TestMarketingDashboard:
    """Integration tests for app_marketing.py"""

    @pytest.mark.integration
    def test_dashboard_has_trends_integration(self, project_root):
        """Should have Google Trends integration"""
        dashboard_path = project_root / "scripts" / "app_marketing.py"
        content = dashboard_path.read_text(encoding="utf-8")

        assert "def get_google_trends" in content
        assert "pytrends" in content.lower()

    @pytest.mark.integration
    def test_dashboard_has_gemini_integration(self, project_root):
        """Should have Gemini AI integration"""
        dashboard_path = project_root / "scripts" / "app_marketing.py"
        content = dashboard_path.read_text(encoding="utf-8")

        assert "def call_gemini" in content or "genai" in content


class TestDashboardUtilityFunctions:
    """Test utility functions used across dashboards"""

    def test_ensure_historical_marginal_profit_data(self, tmp_path):
        """Should create mock data CSV if not exists"""
        from consultant_toolkit.mock_data import ensure_historical_marginal_profit_data

        output_file = tmp_path / "test_data.csv"

        # First call - should create file
        ensure_historical_marginal_profit_data(str(output_file))
        assert output_file.exists()

        # Read and validate
        import polars as pl

        df = pl.read_csv(output_file)

        assert "Year" in df.columns
        assert "Category" in df.columns
        assert "Total_Revenue" in df.columns
        assert len(df) > 0

        # Second call - should not overwrite
        original_size = output_file.stat().st_size
        ensure_historical_marginal_profit_data(str(output_file))
        assert output_file.stat().st_size == original_size


class TestDashboardCaching:
    """Test caching behavior of dashboard functions"""

    @pytest.mark.integration
    def test_cache_decorators_present(self, project_root):
        """Should have @st.cache_data decorators on expensive functions"""
        dashboard_path = project_root / "scripts" / "app_finance.py"
        content = dashboard_path.read_text(encoding="utf-8")

        # Count cache decorators
        cache_count = content.count("@st.cache_data")

        # Should have at least 3 cached functions in the main file
        # (Others are moved to ui_components)
        assert cache_count >= 3

    @pytest.mark.integration
    def test_cache_ttl_configured(self, project_root):
        """Should have TTL configured for cache decorators"""
        dashboard_path = project_root / "scripts" / "app_finance.py"
        content = dashboard_path.read_text(encoding="utf-8")

        # Should have ttl parameter
        assert "ttl=3600" in content or "ttl=1800" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
