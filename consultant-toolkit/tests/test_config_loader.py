"""
Unit tests for config_loader module

Tests YAML configuration loading and singleton pattern.
"""

import os
import tempfile
from pathlib import Path

import pytest
from consultant_toolkit.config_loader import (
    ConfigLoader,
    get_config,
)
from consultant_toolkit.config_loader import (
    get as get_config_value,
)


class TestConfigLoader:
    """Test suite for ConfigLoader class"""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary YAML config file for testing"""
        config_content = """
companies:
  test_company:
    ticker: "TEST.T"
    display_name: "Test Company"
    color: "#123456"

financial:
  wacc_benchmark: 0.05
  target_margin: 0.20

ui:
  animation_duration_ms: 2500
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        yield temp_path

        # Cleanup
        os.unlink(temp_path)

    def test_singleton_pattern(self, temp_config_file):
        """Should return same instance (singleton pattern)"""
        loader1 = ConfigLoader(temp_config_file)
        loader2 = ConfigLoader(temp_config_file)

        assert loader1 is loader2

    def test_load_config_successful(self, temp_config_file):
        """Should load YAML configuration successfully"""
        loader = ConfigLoader(temp_config_file)

        assert loader._config is not None
        assert "companies" in loader._config
        assert "financial" in loader._config
        assert "ui" in loader._config

    def test_get_with_dot_notation(self, temp_config_file):
        """Should retrieve nested values using dot notation"""
        loader = ConfigLoader(temp_config_file)

        ticker = loader.get("companies.test_company.ticker")
        assert ticker == "TEST.T"

        wacc = loader.get("financial.wacc_benchmark")
        assert wacc == 0.05

    def test_get_with_default_value(self, temp_config_file):
        """Should return default when key doesn't exist"""
        loader = ConfigLoader(temp_config_file)

        result = loader.get("nonexistent.key", default=999)
        assert result == 999

    def test_get_top_level_key(self, temp_config_file):
        """Should retrieve entire top-level section"""
        loader = ConfigLoader(temp_config_file)

        companies = loader.get("companies")
        assert isinstance(companies, dict)
        assert "test_company" in companies

    def test_get_deeply_nested_key(self, temp_config_file):
        """Should retrieve deeply nested values"""
        loader = ConfigLoader(temp_config_file)

        color = loader.get("companies.test_company.color")
        assert color == "#123456"

    def test_get_with_none_default(self, temp_config_file):
        """Should return None for missing keys when default is None"""
        loader = ConfigLoader(temp_config_file)

        result = loader.get("missing.key")
        assert result is None


class TestModuleLevelFunctions:
    """Test suite for module-level helper functions"""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary YAML config file"""
        config_content = """
test_section:
  nested_key: "test_value"
  numeric_value: 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        yield temp_path

        os.unlink(temp_path)

    def test_get_config_returns_loader(self, temp_config_file, monkeypatch):
        """get_config() should return ConfigLoader instance"""
        # Monkeypatch the default config path
        monkeypatch.setattr(
            "consultant_toolkit.config_loader.DEFAULT_CONFIG_PATH", Path(temp_config_file)
        )

        # Reset singleton
        ConfigLoader._instance = None

        loader = get_config()
        assert isinstance(loader, ConfigLoader)

    def test_get_config_value_shorthand(self, temp_config_file, monkeypatch):
        """get() should be shorthand for get_config().get()"""
        monkeypatch.setattr(
            "consultant_toolkit.config_loader.DEFAULT_CONFIG_PATH", Path(temp_config_file)
        )

        # Reset singleton
        ConfigLoader._instance = None

        value = get_config_value("test_section.nested_key")
        assert value == "test_value"

        num_value = get_config_value("test_section.numeric_value")
        assert num_value == 42


class TestInvalidConfig:
    """Test suite for error handling with invalid configs"""

    def test_invalid_yaml_syntax(self):
        """Should handle invalid YAML gracefully"""
        invalid_yaml = """
companies:
  - [this is completely invalid YAML
  : syntax error
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name

        try:
            # Reset singleton
            ConfigLoader._instance = None

            with pytest.raises(Exception):
                ConfigLoader(temp_path)
        finally:
            os.unlink(temp_path)

    def test_missing_config_file(self):
        """Should handle missing config file gracefully"""
        # Reset singleton
        ConfigLoader._instance = None

        loader = ConfigLoader("/nonexistent/path/config.yaml")
        assert loader.get("financial.target_margin") == 0.20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
