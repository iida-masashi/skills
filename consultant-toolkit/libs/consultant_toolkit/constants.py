"""
Consultant Toolkit 共通定数

全モジュールで使用する財務・UI定数の単一定義源（Single Source of Truth）。
app_config.yaml で上書き可能な値は config_loader 経由でロードする。
"""

# ========================================
# 財務定数
# ========================================

DAYS_PER_YEAR: float = 365.0

# デフォルト値はフォールバック用。app_config.yaml の financial セクションで上書き可能。
try:
    from consultant_toolkit.config_loader import get as _get_cfg

    DEFAULT_COGS_RATIO: float = _get_cfg("financial.default_cogs_ratio", 0.75)
    DEFAULT_TAX_RATE: float = _get_cfg("financial.default_tax_rate", 0.30)
    WACC_BENCHMARK: float = _get_cfg("financial.wacc_benchmark", 0.05)
    TARGET_MARGIN: float = _get_cfg("financial.target_margin", 0.20)

    # UI / アニメーション定数
    ANIMATION_DURATION_MS: int = _get_cfg("ui.animation_duration_ms", 2500)
    ANIMATION_TRANSITION_MS: int = _get_cfg("ui.animation_transition_ms", 1500)
except (ImportError, NameError, KeyError, TypeError):
    DEFAULT_COGS_RATIO = 0.75
    DEFAULT_TAX_RATE = 0.30
    WACC_BENCHMARK = 0.05
    TARGET_MARGIN = 0.20
    ANIMATION_DURATION_MS = 2500
    ANIMATION_TRANSITION_MS = 1500
