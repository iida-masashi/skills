# ROIC改善シミュレーション機能ドキュメント

**最終更新:** 2026-03-04
**バージョン:** 2.0.0
**配置タブ:** Tab4「🌳 ROICツリー分析」→ サブタブ「🚀 ROIC改善シミュレーション」

---

## 概要

Tab4「高度なROICツリー分析」の5つ目のサブタブとして、**ROIC改善シミュレーター**を実装しています。

`ROIC = NOPAT Margin × IC Turnover` のDuPont分解式に基づき、以下の3つのドライバーをスライダーで操作することで、ROICへのインパクトをリアルタイムで可視化します。

| ドライバー | スライダー | ROICへの経路 |
|-----------|-----------|-------------|
| **NOPAT Margin改善** | -5pp〜+15pp | 収益性の直接向上 |
| **IC Turnover直接改善** | -1.0x〜+3.0x | 資産効率の直接向上（資産売却等） |
| **CCC短縮** | 0〜最大日数 | 運転資本削減 → IC圧縮 → IC Turnover向上 |

---

## ROIC計算式

```
ROIC (%) = NOPAT Margin (%) × IC Turnover (x)

NOPAT Margin (%) = 営業利益 × (1 − 実効税率) ÷ 売上高 × 100
IC Turnover (x)  = 売上高 ÷ 投下資本
投下資本 (IC)    = 有利子負債 + 株主資本
```

---

## CCC短縮 → ROIC改善の連鎖メカニズム

```
CCC短縮 (日)
  → 運転資本削減 (M) = 短縮日数 ÷ 365 × 売上高 × COGS比率
  → 投下資本 (IC) 圧縮
  → IC Turnover 上昇 = 売上高 ÷ 新IC
  → ROIC改善 (pp) = NOPAT Margin × ΔIC Turnover
```

**例:** CCC 20日短縮 / 売上高 65,000M / COGS比率 70%
- 運転資本削減: (20/365) × 65,000 × 0.70 = **2,493M**
- IC Turnover: 1.200x → **1.258x (+0.058x)**
- ROIC改善（NOPAT Margin 6.67%の場合）: **+0.39pp**

---

## 画面構成

### 1. 現状値メトリクス（5列）

| 列 | 表示内容 |
|----|---------|
| 現状 ROIC (%) | 対象企業の直近ROIC |
| 現状 NOPAT Margin (%) | 税引後営業利益率 |
| 現状 IC Turnover (x) | 投下資本回転率 |
| 現状 CCC (日) | キャッシュ・コンバージョン・サイクル |
| 現状 投下資本 (M) | IC = Revenue ÷ IC Turnover で逆算 |

### 2. シミュレーション結果メトリクス（5列）

| 列 | 表示内容 |
|----|---------|
| シミュレーション ROIC (%) | 改善後ROIC（差分pp付き） |
| NOPAT Margin (%) | 改善後マージン |
| IC Turnover (x) | 全ドライバー合算後の回転率 |
| CCC (日) | 短縮後CCC |
| 運転資本削減 (M) | CCC短縮による資本解放額 |

WACC（デフォルト5%）との比較を自動判定し、超過時は緑のSuccess、未達時は黄色のWarningで表示します。

### 3. ROIC改善ブリッジ分析（ウォーターフォールチャート）

```
現状ROIC → マージン改善効果 → CCC短縮効果(IC Turnover↑) → 資産効率直接改善効果 → 交差効果 → シミュレーション後ROIC
```

WACCラインを赤破線でオーバーレイ表示します。

### 4. 感応度マトリクス（ヒートマップ）

NOPAT Margin（行）× IC Turnover（列）の全組み合わせのROIC値をカラーマップで表示します。現状位置に「◉ 現状」マーカーを表示します。

### 5. 目標ROIC達成に向けた改善パス（逆算テーブル）

目標ROICをスライダーで設定すると、3つの改善パスを自動逆算します。

| パス | 内容 |
|------|------|
| パス①: NOPATマージンのみ | `目標NM = 目標ROIC ÷ 現状ICT` |
| パス②: IC Turnoverのみ | `目標ICT = 目標ROIC ÷ 現状NM` |
| パス③: 両方バランス改善 | `スケール係数 = √(目標ROIC ÷ 現状ROIC)` で按分 |

### 6. 改善施策テキスト

NOPATマージン改善策・IC Turnover改善策・CCC短縮施策（DIO/DSO/DPO別）を表示します。
CCC施策には20%短縮時の推定資本解放額を自動計算して表示します。

---

## 関連ドキュメント

- [WHATIF_SIMULATOR_ENHANCED.md](./WHATIF_SIMULATOR_ENHANCED.md) - Tab8 What-Ifシミュレーター
- [IMPLEMENTATION_HISTORY.md](./IMPLEMENTATION_HISTORY.md) - 実装履歴
