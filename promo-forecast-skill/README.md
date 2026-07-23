# Promo Forecast Skill: 定番特売分離需要予測 & 販促ROI分析

## 概要

消費財（CPG）の日次POSデータから「定番需要」と「販促リフト」を分離し、LightGBMベースのハイブリッドモデルで360日先まで予測するパイプラインです。9タブ構成のStreamlitダッシュボードで、利用法・解説・需要分解・販促ROI・価格弾力性・ポートフォリオ分析・What-Ifシミュレーション・販促カレンダー入力までカバーします。

## 技術スタック

| 分類 | ライブラリ |
|------|-----------|
| データ処理 | Polars (100%) |
| 予測モデル | Darts / LightGBM (quantile回帰) |
| ハイパーパラメータ最適化 | Optuna |
| 可視化 | Streamlit / Plotly |
| テスト | Pytest (42テスト) |

## フォルダ構成

```
promo-forecast-skill/
├── libs/
│   ├── config.py          # 定数・パス・ビジネスルール・ランクマッピング
│   ├── data_utils.py      # データ読込・需要分解・ROI集計・弾力性スイープ
│   ├── models.py          # ForecastEngine (LightGBM Hybrid)
│   └── chart_builder.py   # Plotlyチャート生成（11種）
├── scripts/
│   ├── step0_generate_data.py      # テストデータ生成（5品目・5年分、現実性注入: 買いだめ反動・欠品・販促飽和）
│   ├── step1_decompose_demand.py   # 需要分解（Base/Lift分離）
│   ├── step2_run_forecast.py       # 予測実行（Hybrid + LGBM）
│   ├── step3_show_dashboard.py     # Streamlitダッシュボード（9タブ）
│   ├── step4_export_html_report.py # 静的HTMLレポート出力
│   └── step5_taipy_dashboard.py    # Taipyダッシュボード（代替UI）
├── tests/
│   └── test_pipeline.py   # パイプライン整合性テスト（26件）
├── promo_poc_data/        # 生成・加工済みCSV
└── docs/                  # 要件定義・技術仕様ドキュメント
```

## 実行手順

```powershell
# 仮想環境を有効化
.\.venv\Scripts\Activate.ps1

# 1. テストデータ生成
python scripts/step0_generate_data.py

# 2. 需要分解（Base / Lift 分離）
python scripts/step1_decompose_demand.py

# 3. 予測実行（約2分）
python scripts/step2_run_forecast.py

# 4. ダッシュボード起動
streamlit run scripts/step3_show_dashboard.py

# (オプション) HTMLレポート出力
python scripts/step4_export_html_report.py

# テスト実行
pytest tests/test_pipeline.py -v
```

## ダッシュボード構成（9タブ）

各タブにはチャートの読み方・活用方法の解説文が表示されます。先頭の「利用法・解説」タブに全体の使い方をまとめています。

| # | タブ名 | 概要 |
|---|--------|------|
| 0 | 📖 利用法・解説 | クイックスタート・各タブの役割・モデルロジック・指標(MAPE/WAPE/RMSE/バイアス)の読み方 |
| 1 | 需要分解 | 定番/リフト面グラフ + 販促イベントアノテーション + 日次/週次/月次切替 |
| 2 | LGBM 360日展望 | LGBM単体の360日展望（過去180日検証 + 未来180日予測）+ MAPE/WAPE/RMSE/バイアス |
| 3 | Hybrid予測 | Hybridモデルのキャリブレーション済み80%信頼区間付き予測 + バイアス |
| 4 | 販促ROI分析 | 品目別の散布図・ランク別パフォーマンス・キャンペーン一覧 |
| 5 | 品目横断ポートフォリオ | 全5品目の費用vsROI散布図 + ランク別積み上げ棒 + ROIマトリックス |
| 6 | 戦略シミュレーター | 価格・チラシ変更による増分粗利のリアルタイムWhat-If（実分位点リスク幅） |
| 7 | 価格弾力性カーブ | 価格10円刻みスイープ → 増分粗利/数量カーブ + 最適価格自動表示 |
| 8 | 販促カレンダー入力 | 既存カレンダー編集 + 新規プラン追加 → ガントチャート → 予測再実行 → シミュレーター連携 |

## モデルアーキテクチャ

```
実績データ
  → 需要分解（曜日考慮型移動平均・特売日マスク）
      ├── estimated_base（定番需要）
      └── estimated_lift（販促リフト ← 特売日のみ計上、非特売日は0）
  → ForecastEngine.get_hybrid_forecast()
      ├── total = base + lift で再合成してLGBMを学習
      ├── base抽出: price=list_price, flyer=0, discount=0 の中立共変量で再予測
      │            （窓は予測開始日基準で日付明示スライス＝リーク防止）
      └── lift = total_forecast - base_forecast（clip >= 0）
  → calibrate_bands(): バックテスト残差から80%信頼区間を較正（split-conformal）
  → ForecastEngine.get_lgbm_breakdown()   ← LGBM単体（比較用）
  → Streamlitダッシュボード（9タブ）で可視化
```

## 精度指標

| 指標 | 意味 |
|------|------|
| MAPE | 正の実績に対する平均絶対誤差率（%） |
| WAPE | 総量ベースの絶対誤差率（%）。ゼロが多い系列に頑健 |
| RMSE | 二乗平均平方根誤差（実数量スケール） |
| バイアス | 誤差の方向。+ = 過大予測（過剰在庫リスク） / − = 過小予測（欠品リスク） |

> 信頼区間はバックテストの実誤差で較正（split-conformal）。生のLGBM分位点では実カバレッジ約26%だったものを約80%に補正。

## 合成データの現実性パラメータ（`libs/config.py`）

実データに近い挙動を再現するため、Step 0 で以下のCPG現象を注入します。

| 現象 | 定数 | 意味 |
|------|------|------|
| 買いだめ反動（forward-buying） | `PULLFORWARD_FRAC` / `PULLFORWARD_DAYS` | 特売リフトの一定割合を後続N日の定番需要から先食いし、特売後にベースを凹ませる |
| 欠品打ち切り（stockout censoring） | `STOCKOUT_RATE` / `STOCKOUT_CENSOR` | 一部の非特売日で在庫切れにより実売を真の需要より過少に観測。`stockout` フラグで Step 1 のベース推定から除外 |
| 販促飽和（wear-out） | `SATURATION_WINDOW` / `SATURATION_STRENGTH` | 直近の特売頻度に比例してリフトを減衰させ、頻発販促の逓減を表現 |

## 分解精度の検証（合成データ）

`scripts/validate_decomposition.py` は `ground_truth.csv` の真のBase/Liftと推定値を照合し、Base WAPE・Bias・Lift総量比・検知Precision/Recallを出力します（合成データ専用。実データには真値がないため検証不可）。

```powershell
python scripts/validate_decomposition.py
```

`scripts/validate_walkforward.py` は単一ホールドアウトではなく walk-forward（複数origin）バックテストを実行し、品目ごとに WAPE 平均±標準偏差・最悪origin・バイアス平均を出力します。標準偏差が小さいほど精度が安定していることを示し、ヘッドラインの精度が「運」に左右されていないかを確認できます（darts `historical_forecasts`、horizon=30日/stride=30日）。

```powershell
python scripts/validate_walkforward.py
```

## 販促ランク定義

| ランク | 販促名パターン | 特徴 |
|--------|--------------|------|
| S: Deep Impact | 激推し | 深い値引き25-35%・高費用 |
| A: Standard | 通常 | 標準的な特売12-18% |
| B: Light | プチ安 | 浅い値引き5-10% |
| L: Long-term | 長期 | 長期継続型8%・30-45日間 |
