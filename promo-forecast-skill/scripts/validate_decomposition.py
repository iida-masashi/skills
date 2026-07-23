"""定番/特売 分解精度の検証 (合成データ専用).

ground_truth.csv の真の Base/Lift と decomposed_data.csv の推定 Base/Lift を
品目・日付で突き合わせ、需要予測の専門家が分解品質を評価する指標を出力する。

実データには真値が無いため検証不能だが、合成データでは「分離がどれだけ
正しいか」を定量化できる。実行: python scripts/validate_decomposition.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.absolute()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging

import numpy as np
import polars as pl
from libs.config import COL_DATE, COL_ITEM_ID, DECOMPOSED_FILE, ITEMS, TRUTH_FILE
from libs.data_utils import calculate_metrics, load_csv_with_date

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _wape(actual: np.ndarray, pred: np.ndarray) -> float:
    _, wape, _ = calculate_metrics(actual, pred)
    return wape


def validate() -> pl.DataFrame:
    truth = load_csv_with_date(TRUTH_FILE, COL_DATE)
    decomp = load_csv_with_date(DECOMPOSED_FILE, COL_DATE)

    # 実績がある期間のみ照合 (sales_volume が非null = POS 実績期間)
    joined = (
        decomp.filter(pl.col("sales_volume").is_not_null())
        .select(COL_DATE, COL_ITEM_ID, "estimated_base", "estimated_lift",
                "is_promo_detected", "discount_rate")
        .join(truth, on=[COL_DATE, COL_ITEM_ID], how="inner")
    )

    rows: list[dict[str, object]] = []
    for item_id in sorted(joined[COL_ITEM_ID].unique().to_list()):
        sub = joined.filter(pl.col(COL_ITEM_ID) == item_id)
        tb = sub["true_base"].to_numpy()
        tl = sub["true_lift"].to_numpy()
        eb = sub["estimated_base"].to_numpy()
        el = sub["estimated_lift"].to_numpy()

        # 真値ベースで「特売日」を定義 (true_lift が実質的に立っている日)
        is_true_promo = tl > (tb * 0.02)  # base比2%超のリフトを特売効果とみなす
        is_detected = sub["is_promo_detected"].to_numpy().astype(bool)

        # --- Base 精度 ---
        base_wape = _wape(tb, eb)
        base_bias = float(np.sum(eb - tb) / np.sum(tb) * 100)  # +なら過大推定

        # --- Lift 精度 (特売日に限定 = 分離の本丸) ---
        if is_true_promo.any():
            lift_wape_promo = _wape(tl[is_true_promo], el[is_true_promo])
        else:
            lift_wape_promo = float("nan")
        lift_total_ratio = float(np.sum(el) / np.sum(tl) * 100) if np.sum(tl) > 0 else float("nan")

        # --- 誤検知/見逃し (検知ロジックの混同行列) ---
        tp = int(np.sum(is_detected & is_true_promo))
        fp = int(np.sum(is_detected & ~is_true_promo))
        fn = int(np.sum(~is_detected & is_true_promo))
        precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else float("nan")
        recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else float("nan")

        # --- 非特売日の偽リフト (本来ゼロであるべき) ---
        false_lift = float(np.sum(el[~is_true_promo]))
        false_lift_pct = false_lift / np.sum(el) * 100 if np.sum(el) > 0 else 0.0

        rows.append({
            "品目": ITEMS[item_id],
            "Base WAPE%": round(base_wape, 1),
            "Base Bias%": round(base_bias, 1),
            "Lift WAPE%(特売日)": round(lift_wape_promo, 1),
            "Lift総量比%": round(lift_total_ratio, 1),
            "検知Precision%": round(precision, 1),
            "検知Recall%": round(recall, 1),
            "偽リフト割合%": round(false_lift_pct, 1),
        })

    result = pl.DataFrame(rows)
    return result


def main() -> None:
    result = validate()
    logger.info("=" * 78)
    logger.info("定番/特売 分解精度の検証 (推定 vs 真値)")
    logger.info("=" * 78)
    with pl.Config(tbl_rows=10, tbl_cols=12, tbl_width_chars=120):
        logger.info(str(result))
    logger.info("")
    logger.info("[指標の読み方]")
    logger.info("  Base WAPE%      : 定番需要の絶対誤差率 (低いほど良い / 業界目安 <10%)")
    logger.info("  Base Bias%      : +=過大推定, -=過小推定 (0に近いほど良い)")
    logger.info("  Lift WAPE%(特売): 特売日に絞ったリフト誤差率 = 分離の本丸")
    logger.info("  Lift総量比%     : 推定リフト合計/真リフト合計 (100%が理想)")
    logger.info("  検知Precision%  : 特売と判定した日のうち実際に特売だった割合")
    logger.info("  検知Recall%     : 実際の特売日のうち検知できた割合")
    logger.info("  偽リフト割合%   : 推定リフトのうち非特売日に誤って立てた割合")


if __name__ == "__main__":
    main()
