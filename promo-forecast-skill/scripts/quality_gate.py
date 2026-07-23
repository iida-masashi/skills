"""
Automated Quality Gate to prevent regressions (Gemini Self-Check).
Scans files for known 'traps' and ensures essential fixes remain intact.
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Config
TARGET_FILES = [
    "libs/data_utils.py",
    "libs/models.py",
    "libs/chart_builder.py",
    "scripts/step1_decompose_demand.py",
    "scripts/step2_run_forecast.py",
    "scripts/step3_show_dashboard.py"
]

def check_file(path: Path) -> list[str]:
    if not path.exists(): return [f"MISSING: {path}"]
    content = path.read_text(encoding="utf-8")
    errors = []

    # Trap 1: Polars date_range (must use map_elements)
    if "pl.date_range" in content and "map_elements" not in content and "step0" not in str(path):
        errors.append("Potential Polars date_range scalar error (Use map_elements)")

    # Trap 2: sys.path override (mandatory for scripts)
    if "scripts" in str(path) and "sys.path.insert(0" not in content:
        errors.append("Missing sys.path override for path resilience")

    # Trap 3: importlib.reload (mandatory for streamlit)
    if "dashboard" in str(path) and "importlib.reload" not in content:
        errors.append("Missing importlib.reload for Hot Reloading")

    # Trap 4: Plotly vline datetime error
    if "add_vline" in content and "_date_to_epoch_ms" not in content and "chart_builder.py" not in str(path):
        errors.append("Potential Plotly vline TypeError (Use _date_to_epoch_ms converter)")

    return errors

def main() -> None:
    logger.info("--- 🛡️ SCM Galaxy Quality Gate: Start Scanning ---")
    all_errors = {}
    base_path = Path(__file__).parent.parent

    for f in TARGET_FILES:
        errs = check_file(base_path / f)
        if errs: all_errors[f] = errs

    if all_errors:
        logger.error("❌ REGRESSION(S) DETECTED:")
        for f, errs in all_errors.items():
            for e in errs: logger.error(f"  [{f}] {e}")
        sys.exit(1)
    else:
        logger.info("✅ ALL CHECKS PASSED: No known regressions found.")
        sys.exit(0)

if __name__ == "__main__": main()
