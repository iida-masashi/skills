"""
Integration tests for CLI tools

Tests end-to-end execution of command-line tools.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def project_root():
    """Get project root directory"""
    return Path(__file__).parent.parent.parent


class TestAnalyzeCompanyCLI:
    """Integration tests for analyze_company_cli.py"""

    def test_cli_help_message(self, project_root):
        """Should display help message with --help flag"""
        script_path = project_root / "scripts" / "analyze_company_cli.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "--target" in result.stdout
        assert "--competitors" in result.stdout
        assert "--auto-peers" in result.stdout

    def test_cli_missing_required_argument(self, project_root):
        """Should fail when required --target argument is missing"""
        script_path = project_root / "scripts" / "analyze_company_cli.py"

        result = subprocess.run(
            [sys.executable, str(script_path)], capture_output=True, text=True
        )

        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()

    @pytest.mark.slow
    @pytest.mark.integration
    def test_cli_successful_execution_with_mock_ticker(self, project_root):
        """Should execute successfully with valid ticker (network dependent)"""
        script_path = project_root / "scripts" / "analyze_company_cli.py"

        # Use a well-known ticker for testing
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--target",
                "AAPL",
                "--competitors",
                "MSFT",
            ],
            capture_output=True,
            text=True,
            timeout=60,  # 60 second timeout
        )

        # Should not crash (exit code may vary based on API availability)
        assert "Traceback" not in result.stderr or result.returncode == 0


class TestFetchFinanceDataCLI:
    """Integration tests for fetch_finance_data.py"""

    def test_cli_help_message(self, project_root):
        """Should display help message"""
        script_path = project_root / "scripts" / "fetch_finance_data.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "--ticker" in result.stdout

    @pytest.mark.slow
    @pytest.mark.integration
    def test_cli_basic_execution(self, project_root):
        """Should fetch data for a ticker without crashing"""
        script_path = project_root / "scripts" / "fetch_finance_data.py"

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, str(script_path), "--ticker", "AAPL"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        # Should not crash
        assert "Traceback" not in result.stderr or result.returncode == 0


class TestDataAnalyzerCLI:
    """Integration tests for data_analyzer.py"""

    def test_cli_help_message(self, project_root):
        """Should display help message"""
        script_path = project_root / "scripts" / "data_analyzer.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "input" in result.stdout.lower() or "file" in result.stdout.lower()


class TestScriptSyntaxValidity:
    """Verify all Python scripts have valid syntax"""

    def test_all_scripts_compile(self, project_root):
        """All Python scripts should compile without syntax errors"""
        scripts_dir = project_root / "scripts"
        python_files = list(scripts_dir.glob("*.py"))

        assert len(python_files) > 0, "No Python files found in scripts directory"

        for script in python_files:
            # Try to compile
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(script)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, (
                f"Syntax error in {script.name}: {result.stderr}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not slow"])
