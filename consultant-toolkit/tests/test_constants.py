"""Tests for constants module."""

from consultant_toolkit.constants import (
    ANIMATION_DURATION_MS,
    ANIMATION_TRANSITION_MS,
    DAYS_PER_YEAR,
    DEFAULT_COGS_RATIO,
    DEFAULT_TAX_RATE,
    TARGET_MARGIN,
    WACC_BENCHMARK,
)


class TestConstants:
    """定数値の妥当性テスト"""

    def test_days_per_year(self):
        assert DAYS_PER_YEAR == 365.0

    def test_cogs_ratio_range(self):
        assert 0 < DEFAULT_COGS_RATIO < 1

    def test_tax_rate_range(self):
        assert 0 < DEFAULT_TAX_RATE < 1

    def test_wacc_benchmark_range(self):
        assert 0 < WACC_BENCHMARK < 1

    def test_target_margin_range(self):
        assert 0 < TARGET_MARGIN < 1

    def test_animation_positive(self):
        assert ANIMATION_DURATION_MS > 0
        assert ANIMATION_TRANSITION_MS > 0
