---
name: promo-forecast-skill
description: 販売実績データから定番需要と販促リフトを分解し、LightGBMハイブリッドモデルで需要予測・ROI分析・価格弾力性・ポートフォリオ分析・What-Ifシミュレーション・販促カレンダー入力を提供する。S&OP計画や販促効果測定、価格最適化に使う。
---

# Promo Forecast Skill

## 目的

販売実績データから「定番需要」と「販促リフト」を分解し、LightGBMハイブリッドモデルで需要予測・ROI分析を提供するスキル。

## 提供する機能

1. **需要分解** — 値引き率・チラシ情報をもとに実績をBase/Liftに分離 + 販促イベントのアノテーション可視化
2. **ハイブリッド予測** — 中立共変量カウンターファクチュアルによるBase/Lift予測
3. **販促ROI分析** — キャンペーン単位の増分粗利・費用対効果の算出
4. **品目横断ポートフォリオ** — 全品目のROI散布図・ランク別積み上げ棒・ROIマトリックス
5. **What-Ifシミュレーター** — 価格・チラシ変更による増分粗利のリアルタイム試算
6. **価格弾力性カーブ** — 価格スイープによる最適販売価格の自動算出
7. **販促カレンダー入力** — 既存カレンダーの編集 + 新規プランの追加 → ガントチャート → CSV出力 → 予測パイプライン再実行 → シミュレーター連携

## 活用シーン

- **S&OP**: 来月の特売計画（価格・チラシ）を入力し、精緻な予測数量を算出
- **販促効果測定**: 過去の施策が純粋にどれだけ数量リフトをもたらしたかを定量化
- **価格最適化**: 弾力性カーブで粗利最大化ポイントを特定し最適特売価格を決定
- **ポートフォリオ管理**: 全品目横断でどの品目・どのランクに販促予算を振るべきか判断

## 実行方法

```powershell
cd .gemini/skills/promo-forecast-skill

python scripts/step0_generate_data.py
python scripts/step1_decompose_demand.py
python scripts/step2_run_forecast.py
streamlit run scripts/step3_show_dashboard.py
```

詳細は `README.md` を参照。
