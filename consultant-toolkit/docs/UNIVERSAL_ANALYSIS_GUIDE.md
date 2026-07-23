# 汎用企業分析ガイド

## 概要

任意の企業・業界で財務・SCM分析を実行できる汎用CLIツールの使用ガイドです。

---

## CLIツール

### 1. `analyze_company_cli.py` (汎用企業分析CLI)

**新機能**:
- `--auto-peers`: 業界に基づいた競合企業自動提案
- `--competitors`: オプション化（指定しない場合は自動提案のみ）
- 業界マッピング設定ファイル対応

**使用例**:

```bash
# 自動車部品メーカーの分析（自動競合提案）
python scripts/analyze_company_cli.py --target 5988.T --auto-peers

# 食品メーカーの分析（自動競合提案）
python scripts/analyze_company_cli.py --target 2229.T --auto-peers

# 手動で競合指定
python scripts/analyze_company_cli.py --target 7203.T --competitors 7267.T,7201.T

# 手動指定 + 自動提案の併用
python scripts/analyze_company_cli.py --target 5988.T --competitors 5949.T --auto-peers
```

**出力例**:
```
2026-02-22 14:53:36,714 - INFO - 🌐 Industry: Food & Snacks (Japan) - Suggested peers: ['2229.T', '2226.T', '2206.T', '2201.T']
2026-02-22 14:53:36,714 - INFO - 🌐 Auto-suggested peers: ['2226.T', '2206.T', '2201.T']

--- Financial & SCM Metrics ---
| Symbol | Name                  | ROIC (%) | CCC (Days) | DIO (Days) | Revenue Growth (%) |
|--------|-----------------------|----------|------------|------------|--------------------|
| 2229.T | Calbee, Inc.          | 8.80     | 67.31      | 43.14      | 6.45               |
| 2226.T | KOIKE-YA Inc.         | 12.43    | 54.14      | 32.30      | 8.31               |
| 2206.T | Ezaki Glico Co., Ltd. | 2.72     | 59.98      | 74.29      | -0.44              |
| 2201.T | Morinaga&Co., Ltd.    | 10.35    | 86.53      | 99.72      | 7.31               |

============================================================
--- AI Analysis for Calbee, Inc. (Gemini) ---
(詳細な競合分析とSCM改善提案...)
```

---

### 2. `fetch_finance_data.py` (汎用財務データ取得)

**新機能**:
- `--trends`: 財務トレンド分析機能（EBIT, ROE Proxy, Revenue推移）
- 拡張された企業概要（Operating Margin, ROA, ROE, PBR追加）
- ティッカーごとにサブディレクトリ生成（`financial_data/5988_T/`）

**使用例**:

```bash
# 基本的なデータ取得
python scripts/fetch_finance_data.py --ticker AAPL

# トレンド分析付き（日本株の例）
python scripts/fetch_finance_data.py --ticker 7203.T --trends

# 米国株のトレンド分析
python scripts/fetch_finance_data.py --ticker MSFT --trends
```

**出力例**:
```
--- 📊 Company Overview ---
Name                : Example Corp
Sector              : Technology
Industry            : Software
Operating Margin    : 25.0%
ROA                 : 15.0%
ROE                 : 30.0%
Price to Book       : 8.5

--- 📈 Financial Trends (Annual) ---
                 Revenue    Net Income          EBIT  ROE_Proxy
2022-03-31  1.000000e+11  2.000000e+10  2.500000e+10  20.000000
2023-03-31  1.100000e+11  2.300000e+10  2.800000e+10  21.000000
2024-03-31  1.250000e+11  2.700000e+10  3.200000e+10  22.000000
2025-03-31  1.400000e+11  3.100000e+10  3.700000e+10  23.000000

✅ Financial trends saved to: financial_data/AAPL/financial_trends.csv
```

---

## 業界別競合マッピング設定

### 設定ファイル: `scripts/config/industry_peers.json`

業界ごとの競合企業を定義します。新しい業界を追加する場合は、このファイルを編集してください。

**現在サポートされている業界**:

```json
{
  "automotive_parts": {
    "keywords": ["5988", "5949", "5991", "7203", "7267"],
    "global_peers": ["ITW", "STM.DE", "LEA"],
    "description": "Automotive Parts & Components"
  },
  "food_snacks": {
    "keywords": ["2229", "2226", "2206", "2201"],
    "domestic_peers": ["2229.T", "2226.T", "2206.T", "2201.T"],
    "description": "Food & Snacks (Japan)"
  },
  "electronics": {
    "keywords": ["6758", "6501", "6502"],
    "global_peers": ["AAPL", "MSFT", "GOOGL"],
    "description": "Electronics & Technology"
  }
}
```

**新規業界の追加方法**:

```json
{
  "your_industry": {
    "keywords": ["1234", "5678"],  // ティッカーの一部（".T" なしの数字部分）
    "global_peers": ["AAPL", "MSFT"],  // グローバル競合
    "domestic_peers": ["1234.T", "5678.T"],  // 国内競合
    "description": "Your Industry Description"
  }
}
```

---

## ユースケース例

### 1. 新規企業の競合分析

```bash
# トヨタ自動車の分析（業界自動判定）
python scripts/analyze_company_cli.py --target 7203.T --auto-peers

# 任天堂の分析（エレクトロニクス業界）
python scripts/analyze_company_cli.py --target 7974.T --auto-peers
```

### 2. カスタム競合リストでの分析

```bash
# 手動で競合を指定（業界マッピングを使わない）
python scripts/analyze_company_cli.py --target 7203.T --competitors F,TM,GM
```

### 3. 財務トレンドのみ取得

```bash
# 過去数年の財務推移を分析
python scripts/fetch_finance_data.py --ticker 6758.T --trends
```

---

## 今後の拡張可能性

### 1. 業界マッピングの充実化
- `industry_peers.json` に新しい業界を追加することで、自動競合提案の精度向上

### 2. AI プロンプトのカスタマイズ
- 業界ごとに異なるAI分析プロンプトを設定
- `config/ai_prompts.json` などで管理

### 3. ダッシュボードとの統合
- `financial_scm_dashboard.py` でも `industry_peers.json` を活用
- 企業選択時に自動で競合提案

