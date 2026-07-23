# 企業名検索機能ドキュメント

**作成日:** 2026-02-23
**バージョン:** 2.2.0
**機能:** Company Name to Ticker Search

---

## 📊 概要

ティッカーシンボルを知らないユーザーでも、**企業名（日本語・英語）から直接検索**できる機能を追加しました。

---

## 🎯 機能

### **1. 企業名入力対応**

**従来:**
```
入力欄: "対象企業ティッカー"
入力例: AAPL, 7203.T
```

**新機能:**
```
入力欄: "企業名 または ティッカー"
入力例: Apple, トヨタ, Microsoft, AAPL, 7203.T
```

---

### **2. 自動判定**

ユーザーの入力を自動的に判定:

| 入力 | 判定 | 処理 |
|------|------|------|
| `AAPL` | ティッカー | そのまま使用 |
| `Apple` | 企業名 | ティッカー検索 → `AAPL` |
| `7203.T` | ティッカー | そのまま使用 |
| `トヨタ` | 企業名 | ティッカー検索 → `7203.T` |
| `Microsoft` | 企業名 | ティッカー検索 → `MSFT` |

---

### **3. 検索候補表示**

企業名を入力すると、類似する候補を表示:

**例:**
```
入力: "toyota"
↓
💡 他の候補: toyota (7203.T), トヨタ (7203.T)
```

---

### **4. 曖昧検索対応**

スペルミスや部分一致でも検索可能:

| 入力 | マッチ | 結果 |
|------|--------|------|
| `apple` | 完全一致 | `AAPL` |
| `appl` | 曖昧検索 | `AAPL` |
| `マイクロソフト` | 部分一致 | `MSFT` |
| `トヨタ自動車` | 部分一致 | `7203.T` |

---

## 🗂️ 対応企業リスト

### **米国ハイテク (US Tech)**
| 企業名 | ティッカー |
|--------|----------|
| Apple / apple | AAPL |
| Microsoft / microsoft | MSFT |
| Google / Alphabet / alphabet | GOOGL |
| Amazon / amazon | AMZN |
| Meta / Facebook / meta / facebook | META |
| Tesla / tesla | TSLA |
| NVIDIA / nvidia | NVDA |
| Netflix / netflix | NFLX |
| Intel / intel | INTC |
| Adobe / adobe | ADBE |

### **米国金融 (US Finance)**
| 企業名 | ティッカー |
|--------|----------|
| JPMorgan / jp morgan | JPM |
| Bank of America | BAC |
| Wells Fargo | WFC |
| Citigroup | C |
| Goldman Sachs | GS |
| Visa / visa | V |
| Mastercard / mastercard | MA |

### **日本企業 (Japanese Companies)**
| 企業名 | ティッカー |
|--------|----------|
| トヨタ / Toyota / toyota | 7203.T |
| ホンダ / Honda / honda | 7267.T |
| 日産 / Nissan / nissan | 7201.T |
| ソニー / Sony / sony | 6758.T |
| パナソニック / Panasonic | 6752.T |
| 任天堂 / Nintendo / nintendo | 7974.T |
| キーエンス / Keyence | 6861.T |
| ソフトバンク / SoftBank / softbank | 9984.T |
| ファーストリテイリング / Uniqlo / uniqlo | 9983.T |
| デンソー / Denso / denso | 6902.T |
| パイオラックス / Piolax / piolax | 5988.T |
| ユニプレス / Unipres / unipres | 5949.T |
| 日本発条 / NHK Spring | 5991.T |

### **欧州企業 (European Companies)**
| 企業名 | ティッカー |
|--------|----------|
| Volkswagen / volkswagen | VOW.DE |
| BMW / bmw | BMW.DE |
| Mercedes / Daimler / mercedes | MBG.DE |
| Siemens / siemens | SIE.DE |
| SAP / sap | SAP.DE |
| Shell / shell | SHEL |
| BP / bp | BP |
| Nestle / nestle | NESN.SW |

**合計:** 約80社以上のマッピング

---

## 🛠️ 使い方

### **ダッシュボードでの使用**

#### **1. 企業名で検索（英語）**

**入力:**
```
企業名 または ティッカー: Apple
```

**結果:**
```
✓ Apple Inc. (AAPL) - 企業名から検索
```

---

#### **2. 企業名で検索（日本語）**

**入力:**
```
企業名 または ティッカー: トヨタ
```

**結果:**
```
✓ トヨタ自動車株式会社 (7203.T) - 企業名から検索
```

---

#### **3. ティッカーで検索（従来通り）**

**入力:**
```
企業名 または ティッカー: MSFT
```

**結果:**
```
✓ Microsoft Corporation
```

---

#### **4. 部分一致検索**

**入力:**
```
企業名 または ティッカー: micro
```

**結果:**
```
✓ Microsoft Corporation (MSFT) - 企業名から検索
💡 他の候補: microsoft (MSFT)
```

---

### **プログラムでの使用**

```python
from utils.company_search import get_ticker_from_input, search_companies

# 基本的な使い方
ticker, method = get_ticker_from_input("Apple")
print(ticker)  # "AAPL"
print(method)  # "name_search"

# ティッカーの場合
ticker, method = get_ticker_from_input("AAPL")
print(ticker)  # "AAPL"
print(method)  # "ticker"

# 候補検索
results = search_companies("toyota")
print(results)
# [('toyota', '7203.T'), ('トヨタ', '7203.T')]

# カスタムマッピング追加
from utils.company_search import add_custom_mapping
add_custom_mapping("マイ企業", "1234.T")
```

---

## 🔧 実装詳細

### **ファイル構成**

```
scripts/
├── utils/
│   └── company_search.py  # 新規作成（企業名検索ロジック）
└── financial_scm_dashboard.py  # 修正（検索機能統合）
```

---

### **検索アルゴリズム**

#### **Step 1: 入力形式判定**

```python
def get_ticker_from_input(user_input):
    # ティッカー形式か？
    if user_input.isupper() and len(user_input) <= 6:
        return user_input, "ticker"

    # 日本株形式か？（例: 7203.T）
    if '.' in user_input and user_input.split('.')[0].isdigit():
        return user_input.upper(), "ticker"

    # 企業名として検索
    ticker = search_ticker_by_name(user_input)
    return ticker, "name_search"
```

---

#### **Step 2: 企業名検索**

```python
def search_ticker_by_name(company_name, threshold=0.6):
    query = company_name.lower().strip()

    # 1. 完全一致
    if query in COMPANY_NAME_TO_TICKER:
        return COMPANY_NAME_TO_TICKER[query]

    # 2. 部分一致
    for name, ticker in COMPANY_NAME_TO_TICKER.items():
        if query in name or name in query:
            return ticker

    # 3. 曖昧検索（類似度ベース）
    matches = difflib.get_close_matches(query, COMPANY_NAME_TO_TICKER.keys(), cutoff=threshold)
    if matches:
        return COMPANY_NAME_TO_TICKER[matches[0]]

    return None
```

**優先順位:**
1. 完全一致（最優先）
2. 部分一致（高優先）
3. 曖昧検索（低優先）

---

### **企業マッピング追加方法**

新しい企業を追加する場合、`company_search.py` の `COMPANY_NAME_TO_TICKER` 辞書を編集:

```python
COMPANY_NAME_TO_TICKER = {
    # 既存のマッピング...

    # 新規追加
    "新しい企業": "TICKER",
    "new company": "TICKER",
    "新企業略称": "TICKER",
}
```

**推奨事項:**
- 英語名（小文字）
- 日本語名（カタカナ・漢字）
- 略称・通称
- 複数のバリエーションを登録

---

## 🧪 テストケース

### **Test 1: 英語企業名**

| 入力 | 期待結果 |
|------|---------|
| `Apple` | `AAPL` |
| `apple` | `AAPL` |
| `APPLE` | `AAPL` |
| `Microsoft` | `MSFT` |
| `Google` | `GOOGL` |
| `Alphabet` | `GOOGL` |

---

### **Test 2: 日本語企業名**

| 入力 | 期待結果 |
|------|---------|
| `トヨタ` | `7203.T` |
| `ソニー` | `6758.T` |
| `任天堂` | `7974.T` |
| `パイオラックス` | `5988.T` |

---

### **Test 3: 部分一致**

| 入力 | 期待結果 |
|------|---------|
| `micro` | `MSFT` |
| `トヨタ自動車` | `7203.T` |
| `jp morgan` | `JPM` |

---

### **Test 4: ティッカー入力（後方互換性）**

| 入力 | 期待結果 |
|------|---------|
| `AAPL` | `AAPL` (そのまま) |
| `7203.T` | `7203.T` (そのまま) |
| `MSFT` | `MSFT` (そのまま) |

---

## 🚀 今後の拡張案

### **1. APIベースの検索**

現在は静的なマッピング辞書を使用していますが、将来的には外部APIを統合:

- **Yahoo Finance Search API**
- **Financial Modeling Prep API**
- **Alpha Vantage Symbol Search**

```python
def search_ticker_online(company_name):
    # APIで動的に検索
    response = requests.get(f"https://api.example.com/search?q={company_name}")
    return response.json()['ticker']
```

---

### **2. 業界別フィルタリング**

```python
def search_companies(query, industry=None):
    results = []
    for name, ticker in COMPANY_NAME_TO_TICKER.items():
        if industry and not matches_industry(ticker, industry):
            continue
        if query in name:
            results.append((name, ticker))
    return results
```

---

### **3. 多言語対応**

- 中国語企業名
- ドイツ語企業名
- フランス語企業名

---

### **4. 学習機能**

ユーザーの検索履歴から優先度を学習:

```python
def track_search(query, selected_ticker):
    # 検索履歴を保存
    search_history[query] = selected_ticker

def search_with_history(query):
    # 過去の検索結果を優先
    if query in search_history:
        return search_history[query]
    return search_ticker_by_name(query)
```

---

## 📚 関連ドキュメント

- [IMPLEMENTATION_HISTORY.md](./IMPLEMENTATION_HISTORY.md) - 実装履歴・汎用化全体像
- [PEER_SUGGESTION_ENHANCEMENT.md](./PEER_SUGGESTION_ENHANCEMENT.md) - 競合提案機能

---

**作成者:** consultant-toolkit project
**最終更新:** 2026-02-23
**バージョン:** 2.2.0
