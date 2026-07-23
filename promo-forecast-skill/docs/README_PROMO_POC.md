# 定番特売分離需要予測 POC — 技術仕様書

## 1. プロジェクト概要

消費財（CPG）の日次POSデータに混在する「定番需要」と「販促リフト」を構造的に分離し、LightGBMハイブリッドモデルで高精度な需要予測を実現するPOC環境です。

## 2. システムアーキテクチャ

```
Step 0: データ生成
  → Step 1: 需要分解（Base/Lift分離）
  → Step 2: モデル予測（Hybrid + LGBM）
  → Step 3: Streamlitダッシュボード
  → Step 4: HTMLレポート出力（オプション）
```

## 3. データスキーマ

### `sales_actuals.csv` — 日次POS実績
| カラム | 型 | 説明 |
|--------|----|------|
| `date` | Date | 日付 |
| `item_id` | Int | 品目ID (1〜5) |
| `sales_volume` | Float | 販売数量 |
| `actual_price` | Float | 実売価格 |
| `list_price` | Float | 定価 |
| `flyer` | Int | チラシフラグ (0/1) |
| `discount_rate` | Float | 値引き率 `(list_price - actual_price) / list_price` |

### `item_master.csv` — 品目マスタ
| カラム | 型 | 説明 |
|--------|----|------|
| `item_id` | Int | 品目ID |
| `item_name` | Str | 品目名 |
| `list_price` | Float | 定価 |
| `unit_cost` | Float | 原価 |

### `promo_calendar.csv` — 販促カレンダー
| カラム | 型 | 説明 |
|--------|----|------|
| `date` | Date | 日付 |
| `item_id` | Int | 品目ID |
| `promo_name` | Str | 販促名（ランクを含む） |
| `campaign_cost` | Float | 販促費用（円） |

### `decomposed_data.csv` — 分解済み需要（Step1出力）
`sales_actuals` の全カラム + `estimated_base`, `estimated_lift`, 将来行の共変量補完を含む。

### `forecast_results.csv` — 予測結果（Step2出力）
| カラム | 説明 |
|--------|------|
| `forecast_hybrid_base/lift` | Hybridモデルの定番・リフト予測 |
| `forecast_hybrid_lower/upper` | 80%信頼区間（10%・90%分位点） |
| `forecast_lgbm_base/lift` | LGBM単体の定番・リフト予測（比較用） |
| `actual_total` | 検証期間の実績（未来行はNaN） |

## 4. 需要分解アルゴリズム

```
1. 販促日の特定: discount_rate > 10% または promo_calendar に記録がある日
2. 非販促日の sales_volume から曜日別移動平均でベースラインを算出
3. estimated_base = 補間されたベースライン
4. estimated_lift = max(sales_volume - estimated_base, 0)
```

## 5. Hybridモデルの仕組み

**中立共変量カウンターファクチュアル**による定番需要抽出：

```
1. total_series = base + lift で再合成（訓練データ）
2. LightGBM を total_series + covariate_series で学習
3. total_forecast = predict(実際の共変量)
4. base_forecast  = predict(price=list_price, flyer=0, discount=0 の中立共変量)
5. base  = base_forecast.quantile(0.5)
6. lift  = max(total_forecast.quantile(0.5) - base, 0)
7. lower = total_forecast.quantile(0.1)   ← 総需要の10%分位点
8. upper = total_forecast.quantile(0.9)   ← 総需要の90%分位点
```

従来のProphet+LightGBMハイブリッドと異なり、**単一モデルで定番とリフトを統合学習**し、予測時に反実仮想で分解する設計。Prophetが不要なため、インストール依存が減り、MAPEも大幅に改善（31% → 10%台）。

## 6. 販促ROI定義

```
増分粗利 = (販売価格 - 原価) × Σ総需要
         − (定価 - 原価) × Σ定番需要

ROI (%) = 増分粗利 / 直接販促費用 × 100
```

## 7. v0.2.0 追加機能 (2026-04-15)

### 7.1 販促イベントアノテーション (タブ0: 需要分解)
- 需要分解面グラフに販促ブロックの背景色帯 + ランクラベル（`S -30%` 等）を重畳
- 日次/週次/月次の集約切替（`st.radio`）
- アノテーションは日次表示のみ（集約時は非表示で描画負荷を回避）

### 7.2 品目横断ポートフォリオビュー (タブ4: 新規)
- `get_all_items_campaign_summary()`: 全5品目のキャンペーンサマリーを一括算出
- 散布図（費用 vs ROI、color=品目）、ランク別積み上げ棒グラフ、品目xランク平均ROIマトリックス

### 7.3 価格弾力性カーブ (タブ6: 新規)
- `sweep_price_elasticity()`: 原価～定価を10円刻みでスイープし、各価格での180日間リフト・増分粗利を算出
- 2軸チャート: 増分粗利（左軸・赤）+ 総需要数量（右軸・青） + 最適価格の縦線
- `@st.cache_resource` でキャッシュ（初回30-50秒、以降即座）

### 7.4 販促カレンダー入力UI (タブ7: 新規)
- **既存カレンダーの編集**: `promo_calendar.csv` を `st.data_editor` で直接編集（行の追加/削除/修正）
- **予測パイプライン再実行**: 「保存 & 予測を再実行」ボタンでカレンダー保存 → step1（需要分解）→ step2（予測）を自動実行し、全タブの予測に反映
- **新規プラン追加**: `st.form` で品目・ランク・期間・価格・チラシ・費用を入力
- `px.timeline` ガントチャートで既存/新規それぞれの計画を可視化
- CSV出力（`promo_calendar.csv` 互換スキーマ）
- 「シミュレーター連携」ボタン → `st.session_state` 経由でシミュレータータブのスライダーを自動反映

### 7.5 タブ名変更・チャート解説追加
- タブ名を実態に合わせて変更: 「LGBM分析」→「LGBM 360日展望」、「モデル対決」→「Hybrid予測」
- 全8タブの各チャート前にMarkdownで読み方・見方の解説文を追加

### 7.6 共通リファクタリング
- `config.py` に `TIER_MAP`, `TIER_COLORS`, `map_promo_tier()` を一元化（重複ロジック除去）
- `chart_builder.py` に4新チャート関数追加（合計11種）
- テスト: 23件 → 26件

## 8. 今後の展望

- **階層的予測**: カテゴリー・チャネル・店舗クラス単位への拡張
- **外部共変量の統合**: opendata-skill（天候）やdarts-forecast-skill（Google Trends）との連携
- **カニバリゼーション分析**: 品目間の販促クロス影響の定量化

---
*Last updated: 2026-04-15*
