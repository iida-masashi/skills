# 事業セグメント分析機能ドキュメント

**作成日:** 2026-02-23
**バージョン:** 1.0.0
**機能:** Business Segment Revenue Analysis

---

## 📊 概要

企業の**事業セグメント別**および**地域別**の収益構成を分析する機能を追加しました。

yfinance APIではセグメントデータが提供されていないため、以下の3つのアプローチを実装:

1. **手動マッピング方式** (Manual Mapping) - デフォルト
2. **AI自動抽出方式** (AI Extraction) - Gemini API使用
3. **地域別分析** (Geographic Analysis)

---

## 🎯 背景と課題

### yfinance APIの制限

```python
import yfinance as yf
ticker = yf.Ticker('AAPL')

# ❌ セグメント情報は提供されていない
# ticker.segment_revenue → 存在しない
# ticker.earnings → Deprecated (API経由で利用不可)
```

**問題:**
- 有価証券報告書や10-Kファイリングに記載されているセグメント情報がAPIで取得できない
- 企業ごとにセグメント定義が異なる（製品別、地域別、事業部別など）

**解決策:**
- 主要企業の手動マッピングデータベース構築
- Gemini AIによる最新情報の自動抽出
- ユーザーによるカスタムマッピング追加機能

---

## 🗂️ 対応企業リスト

### **米国ハイテク企業**

| 企業 | ティッカー | セグメント数 | データソース |
|------|----------|------------|------------|
| Apple Inc. | AAPL | 5 | Apple 10-K Filing (FY2023) |
| Microsoft | MSFT | 3 | Microsoft 10-K (FY2023) |
| Alphabet | GOOGL | 3 | Alphabet 10-K (FY2023) |
| Amazon | AMZN | 5 | Amazon 10-K (FY2023) |

#### Apple (AAPL) セグメント詳細

```python
{
    "iPhone": 52%,
    "Services": 22%,
    "Mac": 8%,
    "iPad": 8%,
    "Wearables": 10%
}
```

#### Microsoft (MSFT) セグメント詳細

```python
{
    "Intelligent Cloud": 42%,    # Azure, Server products
    "Productivity": 34%,          # Office, LinkedIn, Dynamics
    "Personal Computing": 24%     # Windows, Xbox, Surface
}
```

---

### **日本企業**

| 企業 | ティッカー | セグメント数 | データソース |
|------|----------|------------|------------|
| トヨタ自動車 | 7203.T | 3 | 有価証券報告書 (FY2023) |
| ソニーグループ | 6758.T | 6 | 有価証券報告書 (FY2023) |

#### トヨタ自動車 (7203.T) セグメント詳細

```python
{
    "自動車": 90%,
    "金融": 7%,
    "その他": 3%
}
```

#### ソニーグループ (6758.T) セグメント詳細

```python
{
    "ゲーム＆ネットワーク": 30%,
    "音楽": 11%,
    "映画": 12%,
    "エレクトロニクス": 25%,
    "イメージング＆センシング": 13%,
    "金融": 9%
}
```

---

## 🛠️ 使い方

### **1. ダッシュボードでの使用**

#### Step 1: 企業選択

```
サイドバー > 企業名 または ティッカー: Apple
```

#### Step 2: Tab8に移動

```
タブ: 📊 8. 事業セグメント分析 (Business Segments)
```

#### Step 3: 分析モード選択

**オプション1: 手動マッピング（デフォルト）**
```
✅ 高速
✅ 正確（手動検証済み）
❌ 対応企業に限定
```

**オプション2: AI自動抽出**
```
☑ AI自動抽出を使用 (Gemini API)

✅ 任意の企業に対応
✅ 最新情報を取得
❌ Gemini APIキーが必要
❌ 精度はAIに依存
```

---

### **2. プログラムでの使用**

#### 基本的な使い方

```python
from utils.segment_analysis import get_segment_analysis

# セグメント分析実行
segment_df, geo_df, source = get_segment_analysis(
    ticker="AAPL",
    use_ai=False  # 手動マッピング使用
)

# 結果表示
print(segment_df)
#        Segment      Revenue  Percentage         Description
# 0       iPhone  208000.00M       52.0%  Smartphone hardware
# 1     Services   88000.00M       22.0%  App Store, iCloud...
# 2   Wearables   40000.00M       10.0%  Apple Watch, AirPods
```

#### AI抽出モード

```python
# Gemini APIで最新情報を抽出
segment_df, geo_df, source = get_segment_analysis(
    ticker="NVDA",  # 手動マッピングにない企業
    use_ai=True     # AI抽出を使用
)

print(source)
# "AI-extracted from NVIDIA 10-K Filing"
```

#### カスタムマッピング追加

```python
from utils.segment_analysis import add_segment_mapping

# 新しい企業を追加
add_segment_mapping(
    ticker="5988.T",
    company_name="パイオラックス株式会社",
    segments={
        "自動車部品": {"percentage": 0.85, "description": "ファスナー、エアダンパー"},
        "医療機器": {"percentage": 0.10, "description": "カテーテル"},
        "その他": {"percentage": 0.05, "description": "新規事業"}
    },
    fiscal_year=2023,
    source="会社資料"
)
```

---

## 📈 分析機能

### **1. 事業セグメント別収益構成**

**パイチャート**
- セグメントごとの収益割合を視覚化
- ドーナツチャートで中央に企業名表示

**データテーブル**
- セグメント名
- 収益額（百万単位）
- 構成比率（%）
- 説明

**棒グラフ**
- セグメント別収益額の比較

---

### **2. リスク評価 (Consultant's Insight)**

#### 集中リスク判定

| 最大セグメント割合 | リスクレベル | 判定 |
|------------------|------------|------|
| 50%超 | 🔴 高リスク | 単一事業依存、多角化必須 |
| 30-50% | 🟡 中リスク | 主力事業は健全、多角化余地あり |
| 30%未満 | 🟢 分散良好 | バランスの取れたポートフォリオ |

**例:**

```
💡 Consultant's Insight: 🔴 高リスク
収益の52.0%を「iPhone」に依存しているわ。集中リスクが高すぎるわね。
他セグメントの育成が急務よ。
```

---

### **3. 地域別収益構成**

**対応地域:**
- Americas (北米)
- Europe (欧州)
- Greater China (中華圏)
- Japan (日本)
- Asia Pacific (アジア太平洋)
- EMEA (欧州・中東・アフリカ)

**表示内容:**
- 地域別パイチャート
- 収益額・構成比率テーブル

---

## 🔧 実装詳細

### **ファイル構成**

```
scripts/
├── utils/
│   └── segment_analysis.py        # セグメント分析モジュール（新規作成）
└── financial_scm_dashboard.py     # ダッシュボード（Tab8追加）

docs/
└── SEGMENT_ANALYSIS_FEATURE.md    # このドキュメント
```

---

### **主要関数**

#### `get_segment_analysis(ticker, use_ai=False)`

統合インターフェース - セグメント分析を実行

**引数:**
- `ticker` (str): ティッカーシンボル
- `use_ai` (bool): AI抽出を使用するか

**戻り値:**
- `segment_df` (pd.DataFrame): 事業セグメント別収益
- `geo_df` (pd.DataFrame): 地域別収益
- `source` (str): データソース情報

---

#### `get_segment_data_manual(ticker)`

手動マッピングからセグメントデータを取得

**引数:**
- `ticker` (str): ティッカーシンボル

**戻り値:**
- セグメント情報辞書、見つからない場合はNone

---

#### `extract_segments_with_ai(ticker, company_name)`

Gemini AIでセグメント情報を自動抽出

**引数:**
- `ticker` (str): ティッカーシンボル
- `company_name` (str): 企業名

**戻り値:**
- 抽出されたセグメント情報辞書

**実装:**
```python
prompt = f"""
企業名: {company_name} (ティッカー: {ticker})

この企業の最新の事業セグメント構成を教えてください。

以下の形式でJSON形式で回答してください:
{{
    "segments": {{
        "セグメント名1": {{"percentage": 割合(0-1), "description": "説明"}},
        ...
    }},
    "fiscal_year": 年度,
    "source": "情報源"
}}
"""

response = client.models.generate_content(
    model='gemini-2.0-flash-exp',
    contents=prompt,
    config=types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json"
    )
)
```

---

#### `calculate_segment_revenue(ticker, total_revenue)`

総収益からセグメント別収益を計算

**引数:**
- `ticker` (str): ティッカーシンボル
- `total_revenue` (float): 総収益額

**戻り値:**
- セグメント別収益DataFrame

---

#### `get_geographic_revenue(ticker, total_revenue)`

地域別収益を計算

**引数:**
- `ticker` (str): ティッカーシンボル
- `total_revenue` (float): 総収益額

**戻り値:**
- 地域別収益DataFrame

---

## 🧪 テストケース

### **Test 1: Apple (手動マッピング)**

**入力:**
```python
segment_df, geo_df, source = get_segment_analysis("AAPL", use_ai=False)
```

**期待結果:**
```
segment_df:
   Segment       Revenue  Percentage
0  iPhone    208000.00M      52.0%
1  Services   88000.00M      22.0%
...

source: "Manual mapping (FY2023)"
```

---

### **Test 2: トヨタ自動車 (手動マッピング)**

**入力:**
```python
segment_df, geo_df, source = get_segment_analysis("7203.T", use_ai=False)
```

**期待結果:**
```
segment_df:
   Segment       Revenue  Percentage
0  自動車    36000000.00M     90.0%
1  金融       2800000.00M      7.0%
...
```

---

### **Test 3: NVIDIA (AI抽出)**

**入力:**
```python
segment_df, geo_df, source = get_segment_analysis("NVDA", use_ai=True)
```

**期待結果:**
```
segment_df:
   Segment            Revenue  Percentage
0  Data Center    26000.00M       65.0%
1  Gaming         10000.00M       25.0%
...

source: "AI-extracted from NVIDIA 10-K Filing"
```

---

## 🚀 今後の拡張案

### **1. 複数年セグメント推移分析**

現状は単年度のみ → 過去5年のセグメント成長率を分析

```python
def segment_growth_analysis(ticker, years=5):
    # セグメント別のCAGR（年平均成長率）を計算
    # 成長セグメント vs 衰退セグメントを可視化
```

---

### **2. セグメント別収益性分析**

収益構成だけでなく、セグメント別の利益率も分析

```python
{
    "iPhone": {
        "revenue_pct": 0.52,
        "operating_margin": 0.38,  # セグメント別営業利益率
        "contribution_margin": 0.45
    }
}
```

---

### **3. SEC EDGAR API統合**

10-K/10-Q filingから直接セグメントデータを抽出

```python
from sec_edgar_downloader import Downloader

def fetch_segment_from_edgar(ticker):
    # SECファイリングをダウンロード
    # セグメント情報を自動抽出
```

---

### **4. Financial Modeling Prep API統合**

有料APIだがセグメントデータが充実

```python
import requests

def fetch_segment_from_fmp(ticker, api_key):
    url = f"https://financialmodelingprep.com/api/v4/revenue-product-segmentation/{ticker}"
    response = requests.get(url, params={"apikey": api_key})
    return response.json()
```

---

### **5. 競合セグメント比較**

複数企業のセグメント構成を並べて比較

```python
def compare_segments_multi_company(tickers):
    # Apple vs Microsoft vs Google
    # セグメント別市場シェア分析
```

---

## 📊 UI/UX詳細

### **Tab8のレイアウト**

```
┌─────────────────────────────────────────────────────┐
│ 8. 事業セグメント別 収益分析                          │
├─────────────────────────────────────────────────────┤
│ 📊 分析設定                                          │
│ ☑ AI自動抽出を使用 (Gemini API)                      │
│ ✅ AAPL はマッピング済み                              │
├─────────────────────────────────────────────────────┤
│ 📈 事業セグメント別 収益構成                          │
│ ┌──────────────┬──────────────┐                     │
│ │ パイチャート │ データテーブル │                     │
│ └──────────────┴──────────────┘                     │
│ 棒グラフ (セグメント別収益額)                         │
│ 💡 Consultant's Insight: 🔴 高リスク                 │
├─────────────────────────────────────────────────────┤
│ 🌍 地域別 収益構成                                    │
│ ┌──────────────┬──────────────┐                     │
│ │ パイチャート │ データテーブル │                     │
│ └──────────────┴──────────────┘                     │
├─────────────────────────────────────────────────────┤
│ 🔧 カスタムセグメント登録 (Advanced)                  │
│ [展開可能フォーム]                                    │
└─────────────────────────────────────────────────────┘
```

---

## 📚 関連ドキュメント

- [IMPLEMENTATION_HISTORY.md](./IMPLEMENTATION_HISTORY.md) - 実装履歴・汎用化全体像
- [COMPANY_NAME_SEARCH.md](./COMPANY_NAME_SEARCH.md) - 企業名検索機能
- [PEER_SUGGESTION_ENHANCEMENT.md](./PEER_SUGGESTION_ENHANCEMENT.md) - 競合提案機能

---

## ⚠️ 注意事項

### **データの正確性**

- **手動マッピング:** FY2023時点のデータ（定期更新が必要）
- **AI抽出:** Gemini AIの回答精度に依存（要検証）
- **地域別データ:** 企業によって開示粒度が異なる

### **API制限**

- **Gemini API:** 無料枠は1分間に15リクエストまで
- **yfinance:** レート制限あり（過度なリクエストは禁止）

### **セグメント定義の違い**

企業ごとにセグメント定義が異なるため、横並び比較には注意:

```
例:
Apple:      製品別（iPhone, Mac, Services）
Microsoft:  事業別（Cloud, Productivity, Personal Computing）
トヨタ:     事業別（自動車、金融、その他）
```

---

**作成者:** consultant-toolkit project
**最終更新:** 2026-02-23
**バージョン:** 1.0.0
