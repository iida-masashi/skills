# What-If シミュレーター - 強化版ドキュメント

**作成日:** 2026-02-23
**バージョン:** 2.0.0
**機能:** Interactive Financial Simulator

---

## 📊 概要

**Tab8: What-If シミュレーター**は、財務指標を動的に調整して、ROIC・FCF・営業利益への影響をリアルタイムで可視化する対話型シミュレーターです。

### 🎯 目的

経営判断の「もしも」を数値化し、施策の優先順位付けを支援します。

---

## 🚀 主要機能

### **4つのシミュレーションモード**

1. **💰 収益性改善**
   - 売上成長率の変更
   - 売上原価率の削減
   - 販管費率の最適化
   - ウォーターフォールチャートで要因分解

2. **🔄 運転資本効率化**
   - DIO（在庫回転日数）削減
   - DSO（売掛金回収日数）短縮
   - DPO（買掛金支払日数）延長
   - CCC最適化による運転資本削減効果

3. **🏗️ 投資戦略**
   - CAPEX増減シミュレーション
   - 投資効率（ROI）分析
   - FCF推移の3年間予測（保守的・ベース・積極的）

4. **📊 総合シミュレーション**
   - 全パラメータ統合分析
   - レーダーチャートで多角的評価
   - 推奨アクションプラン自動生成
   - JSON形式でエクスポート可能

---

## 🎛️ 使い方

### **Step 1: ダッシュボードを開く**

```bash
streamlit run scripts/financial_scm_dashboard.py
```

ブラウザで http://localhost:8501 にアクセス

---

### **Step 2: Tab8「What-If シミュレーター」を選択**

タブバーから「🎮 8. What-If シミュレーター」をクリック

---

### **Step 3: パラメータを調整**

#### **モード1: 収益性改善**

**パラメータ:**
- **売上高 成長率 (%):** -20% ~ +50%
- **売上原価率 変更 (pp):** -10pp ~ +10pp
- **販管費率 変更 (pp):** -10pp ~ +10pp

**例:**
```
売上高成長率: +10%
売上原価率変更: -2pp (原価削減)
販管費率変更: -1pp (固定費削減)
```

**結果:**
- 売上高: 110,000M → 121,000M (+11,000M)
- 営業利益: 15,000M → 18,150M (+3,150M)
- 営業利益率: 15.0% → 15.8% (+0.8pp)

**ビジュアル:**
- 📊 **メトリクスカード:** 現状 vs シミュレーション
- 📉 **ウォーターフォールチャート:** 利益の増減要因分解

---

#### **モード2: 運転資本効率化**

**パラメータ:**
- **DIO 変更:** -30日 ~ +30日
- **DSO 変更:** -20日 ~ +20日
- **DPO 変更:** -20日 ~ +20日

**例:**
```
DIO: -15日 (在庫削減)
DSO: -10日 (回収早期化)
DPO: +5日 (支払延長)
```

**結果:**
- DIO: 60日 → 45日 (-15日)
- DSO: 45日 → 35日 (-10日)
- DPO: 30日 → 35日 (+5日)
- **CCC: 75日 → 45日 (-30日短縮)**

**インパクト:**
```
💡 運転資本削減効果: CCC 30日短縮により、
約 5,479M の運転資本を削減できます。
```

**ビジュアル:**
- 📊 **棒グラフ:** DIO/DSO/DPO/CCC の現状 vs シミュレーション
- 💰 **運転資本削減額:** 自動計算して表示

---

#### **モード3: 投資戦略**

**パラメータ:**
- **CAPEX 変更率 (%):** -50% ~ +100%
- **CAPEX効率性:** 0.5 ~ 3.0 (1億投資で何億の売上増加か)

**例:**
```
CAPEX変更率: +20%
CAPEX効率性: 2.0 (1億投資で2億の売上増加)
```

**結果:**
- CAPEX: 5,000M → 6,000M (+1,000M)
- 売上増加効果: +2,000M
- FCF: 10,000M → 9,000M (-1,000M) ※短期的には減少
- 投資ROI: 200%

**ビジュアル:**
- 📈 **FCF推移シミュレーション (3年間):**
  - 保守的シナリオ (OCF成長2%)
  - ベースシナリオ (OCF成長5%)
  - 積極的シナリオ (OCF成長8%)

---

#### **モード4: 総合シミュレーション**

**表示内容:**

1. **統合KPIダッシュボード**
   - 売上高、営業利益、営業利益率、CCC、FCF
   - 現状からの変化を△表示

2. **レーダーチャート**
   - 収益性、効率性、キャッシュ創出、成長性、投資効率
   - 現状 vs シミュレーションを重ねて表示

3. **推奨アクションプラン**
   - 実施した施策とインパクトを箇条書き
   - 自動生成

**例:**
```
✅ 原価削減: 売上原価率を2.0pp削減 → 営業利益 2,420M増加
✅ 在庫最適化: DIOを15日短縮 → 運転資本 2,740M削減
✅ 売掛金回収強化: DSOを10日短縮 → キャッシュフロー改善
✅ 成長投資: CAPEXを20%増加 → 売上成長 2,000M期待
```

4. **エクスポート機能**
   - JSON形式でシミュレーション結果をダウンロード
   - 日時、企業名、パラメータ、結果、インパクトを記録

---

## 📊 ビジュアル一覧

### **1. ウォーターフォールチャート (Waterfall Chart)**

**用途:** 営業利益の増減要因を分解

**構成:**
```
現状営業利益 → 売上高増減効果 → 原価率改善効果 → 販管費削減効果 → シミュレーション後
```

**色分け:**
- 🟢 緑: プラス要因（利益増加）
- 🔴 赤: マイナス要因（利益減少）
- 🔵 青: 合計値

---

### **2. CCC コンポーネント比較 (Bar Chart)**

**用途:** DIO/DSO/DPO/CCCの現状とシミュレーションを並べて比較

**構成:**
- DIO: 🟠 オレンジ
- DSO: 🟢 グリーン
- DPO: 🔴 レッド (マイナス表示)
- CCC: 🔵 ブルー

---

### **3. FCF推移シミュレーション (Line Chart)**

**用途:** 3年間のFCF予測を3シナリオで表示

**シナリオ:**
- 🔴 保守的 (OCF成長2%/年): 点線
- 🔵 ベース (OCF成長5%/年): 実線（太字）
- 🟢 積極的 (OCF成長8%/年): 破線

---

### **4. 総合パフォーマンス比較 (Radar Chart)**

**用途:** 5つの評価軸で現状とシミュレーションを比較

**評価軸:**
1. **収益性:** 営業利益率ベース
2. **効率性:** CCC短縮度
3. **キャッシュ創出:** FCF/売上高比率
4. **成長性:** 売上成長率
5. **投資効率:** OCF/CAPEX比率

**スコア化:** 各軸を0-100点で正規化

---

## 🧪 シミュレーション例

### **ケース1: 製造業のコスト削減**

**背景:**
- 原価率が高く、在庫回転が遅い
- 利益率改善とキャッシュフロー改善を同時に実現したい

**設定:**
```
[収益性改善]
- 売上原価率変更: -3pp (サプライヤー見直し、自動化)

[運転資本効率化]
- DIO変更: -20日 (JIT導入、在庫削減)
- DSO変更: -10日 (請求早期化)
```

**結果:**
```
営業利益: +3,630M
CCC: 75日 → 45日 (-30日)
運転資本削減: 約 5,479M
FCF: +2,479M
```

**推奨アクション:**
- ✅ サプライチェーン最適化で原価3pp削減
- ✅ 在庫管理システム導入でDIO20日短縮
- ✅ 請求サイクル見直しでDSO10日短縮

---

### **ケース2: ハイテク企業の成長投資**

**背景:**
- 市場拡大期で積極投資したい
- FCF減少は許容するが、売上成長を最大化

**設定:**
```
[収益性改善]
- 売上高成長率: +25%

[投資戦略]
- CAPEX変更率: +50%
- CAPEX効率性: 2.5
```

**結果:**
```
売上高: 100,000M → 125,000M (+25,000M)
CAPEX: 5,000M → 7,500M (+2,500M)
売上増加効果（CAPEX寄与）: +6,250M
合計売上: 131,250M
FCF: 10,000M → 7,500M (-2,500M) ※短期的減少
投資ROI: 250%
```

**3年後予測（積極的シナリオ）:**
```
Year 0: 10,000M
Year 1: 10,125M
Year 2: 10,935M
Year 3: 11,810M ← 投資効果で回復
```

---

### **ケース3: 小売業のキャッシュフロー改善**

**背景:**
- 売上は好調だがキャッシュフローが逼迫
- 運転資本の最適化が急務

**設定:**
```
[運転資本効率化]
- DIO変更: -10日 (商品回転率向上)
- DSO変更: -5日 (カード決済比率向上)
- DPO変更: +10日 (支払条件見直し)
```

**結果:**
```
CCC: 75日 → 40日 (-35日短縮)
運転資本削減: 6,397M
営業利益: 変化なし（コスト構造は維持）
FCF: +6,397M（運転資本削減効果）
```

---

## 💡 活用シーン

### **1. 経営会議での意思決定**

```
質問: 「原価削減 vs 在庫削減、どちらを優先すべきか？」

シミュレーション:
→ 原価削減2pp: 営業利益 +2,000M
→ 在庫削減15日: 運転資本 -2,740M、FCF改善

結論: 短期的にはFCF改善の在庫削減、中長期では利益体質改善の原価削減
```

---

### **2. 予算策定・中期計画**

```
目標: 3年後にFCF 15,000M達成

現状: FCF 10,000M

シミュレーション:
→ 売上成長5%/年 + CCC10日短縮 + CAPEX抑制10%
→ 3年後FCF予測: 14,800M

→ さらに原価1pp削減を追加
→ 3年後FCF予測: 16,200M ✅ 目標達成
```

---

### **3. M&A・事業買収の検討**

```
買収対象: 売上 50,000M、営業利益率 8%、CCC 90日

シミュレーション:
→ 自社のベストプラクティス適用
  - 原価削減: -2pp
  - CCC短縮: -20日

改善後:
→ 営業利益率: 8% → 10% (+2pp)
→ CCC: 90日 → 70日
→ 追加価値創出: 1,000M/年
```

---

## 🔧 技術実装

### **データ取得**

```python
# 財務データ取得
income_statement, balance_sheet = load_financial_data(target_ticker)
cf_data = get_cashflow_data(target_ticker)

# 最新年度データ
latest_year = income_statement.columns[0]

current_revenue = get_val_safe(income_statement, ["Total Revenue"], latest_year)
current_cogs = get_val_safe(income_statement, ["Cost Of Revenue"], latest_year)
current_inventory = get_val_safe(balance_sheet, ["Inventory"], latest_year)
```

---

### **シミュレーション計算**

#### 収益性計算

```python
sim_revenue = current_revenue * (1 + revenue_growth / 100)
sim_cogs_ratio = current_cogs_ratio + cogs_change
sim_cogs = sim_revenue * (sim_cogs_ratio / 100)
sim_oi = sim_revenue - sim_cogs - sim_opex
sim_oi_margin = (sim_oi / sim_revenue * 100)
```

#### CCC計算

```python
sim_dio = max(0, current_dio + dio_change)
sim_dso = max(0, current_dso + dso_change)
sim_dpo = max(0, current_dpo + dpo_change)
sim_ccc = sim_dio + sim_dso - sim_dpo

# 運転資本削減効果
ccc_improvement = current_ccc_val - sim_ccc
working_capital_reduction = (ccc_improvement / DAYS_PER_YEAR) * (current_revenue * (current_cogs_ratio / 100))
```

#### FCF予測

```python
# 3年間シミュレーション
for year in range(1, 4):
    fcf_base = (current_ocf * (1.05 ** year) - sim_capex) / 1e6
    fcf_aggressive = (current_ocf * (1.08 ** year) - sim_capex * (1.02 ** year)) / 1e6
```

---

### **レーダーチャートスコア計算**

```python
# 0-100点に正規化
current_scores = [
    min(current_oi_margin * 5, 100),           # 収益性
    max(0, 100 - current_ccc_val),              # 効率性
    min((current_fcf / current_revenue * 100) * 10, 100),  # キャッシュ創出
    50,                                         # 成長性（ベースライン）
    min((current_ocf / current_capex) * 20, 100)  # 投資効率
]
```

---

## 📥 エクスポート形式

### **JSON出力例**

```json
{
  "simulation_date": "2026-02-23 12:30:45",
  "company": "Apple Inc.",
  "ticker": "AAPL",
  "parameters": {
    "revenue_growth": "10%",
    "cogs_change": "-2pp",
    "opex_change": "-1pp",
    "dio_change": "-15日",
    "dso_change": "-10日",
    "dpo_change": "+5日",
    "capex_change": "0%"
  },
  "results": {
    "revenue": "121000.0M",
    "operating_income": "18150.0M",
    "operating_margin": "15.8%",
    "ccc": "45日",
    "fcf": "12479.0M"
  },
  "impact": {
    "revenue_change": "+11000.0M",
    "oi_change": "+3150.0M",
    "ccc_change": "-30日",
    "fcf_change": "+2479.0M"
  }
}
```

---

## 🚀 今後の拡張案

### **1. シナリオ保存機能**

複数のシミュレーション結果を保存・比較

```python
scenarios = {
    "保守的": {...},
    "ベース": {...},
    "積極的": {...}
}
```

---

### **2. 感度分析 (Sensitivity Analysis)**

特定パラメータの変化がKPIに与える影響を可視化

```python
# 原価率 -5pp ~ +5pp の範囲で営業利益への影響を計算
sensitivity_cogs = []
for cogs_delta in range(-5, 6):
    oi_impact = calculate_oi(cogs_delta)
    sensitivity_cogs.append(oi_impact)
```

---

### **3. モンテカルロシミュレーション**

不確実性を考慮した確率的予測

```python
# 売上成長率を正規分布でランダム化（平均5%, 標準偏差2%）
for i in range(1000):
    growth_rate = np.random.normal(5, 2)
    fcf_simulation = calculate_fcf(growth_rate)
```

---

### **4. 業界ベンチマーク比較**

同業他社の平均値と比較

```python
industry_avg = {
    "oi_margin": 12.5,
    "ccc": 55,
    "capex_ratio": 8.0
}
```

---

## 📚 関連ドキュメント

- [ROIC_SIMULATION_FEATURE.md](./ROIC_SIMULATION_FEATURE.md) - Tab4 ROIC改善シミュレーター
- [SEGMENT_ANALYSIS_FEATURE.md](./SEGMENT_ANALYSIS_FEATURE.md) - セグメント分析（Tab9）
- [IMPLEMENTATION_HISTORY.md](./IMPLEMENTATION_HISTORY.md) - 実装履歴

---

**作成者:** consultant-toolkit project
**最終更新:** 2026-02-23
**バージョン:** 2.0.0
