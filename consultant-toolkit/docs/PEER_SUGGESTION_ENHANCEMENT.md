# 競合企業自動提案機能 - 強化版ドキュメント

**作成日:** 2026-02-23
**バージョン:** 2.1.0
**機能:** Advanced Peer Company Suggestion Engine

---

## 📊 概要

従来のキーワードベース提案から、**AI・業界分析・時価総額マッチング**を活用した高度な競合企業提案システムに進化しました。

---

## 🎯 強化された提案モード（3段階）

### 1. 🤖 **AI提案（高精度）**
- **使用技術:** Gemini 2.0 Flash
- **分析内容:**
  - 対象企業の業界・セクター・国・時価総額を分析
  - AIが最適な競合企業を動的に提案
  - グローバル企業と国内企業のバランスを考慮
- **提案数:** 最大8社
- **精度:** ⭐⭐⭐⭐⭐（最高）

**使用例:**
```python
from utils.peer_suggestion import suggest_peers_with_ai

peers = suggest_peers_with_ai("AAPL", max_peers=5)
# 結果: ['MSFT', 'GOOGL', 'META', 'AMZN', 'NVDA']
```

---

### 2. 🔍 **自動提案（高度）**
- **使用技術:** yfinance API + スコアリングアルゴリズム
- **分析内容:**
  - 業界・セクター一致度スコアリング（+50点）
  - 時価総額の近似性スコアリング（+30点）
  - 国・地域の一致度スコアリング（+20点）
- **提案数:** 最大8社
- **精度:** ⭐⭐⭐⭐（高精度）

**スコアリング基準:**
| 基準 | 配点 | 説明 |
|------|------|------|
| 業界一致 | +50点 | 同じIndustry分類 |
| セクター一致 | +30点 | 同じSector分類 |
| 時価総額近似 | +30点 | 0.2x ~ 5x の範囲 |
| 同じ国 | +20点 | 国が一致（日本企業向け優遇） |

**使用例:**
```python
from utils.peer_suggestion import suggest_peers_advanced

peers = suggest_peers_advanced(
    "7203.T",  # トヨタ
    max_peers=5,
    prefer_same_country=True,
    size_tolerance=5.0
)
# 結果: ['7267.T', '7201.T', 'TM', 'F', 'GM']
```

---

### 3. 📋 **自動提案（基本）**
- **使用技術:** industry_peers.json（設定ファイル）
- **分析内容:**
  - ティッカーシンボルのキーワードマッチング
  - 事前定義された業界別競合リスト
- **提案数:** 設定ファイルに依存
- **精度:** ⭐⭐⭐（標準）

**使用例:**
```python
from utils.peer_suggestion import suggest_peers_basic

peers = suggest_peers_basic("5988.T")
# 結果: industry_peers.jsonの設定に基づく
```

---

## 🛠️ 実装詳細

### 新規ファイル

#### `scripts/utils/peer_suggestion.py`
競合提案エンジンの中核モジュール

**主要関数:**

1. **`get_company_info(ticker: str)`**
   - yfinance APIで企業情報を取得
   - 業界、セクター、時価総額、国を返す

2. **`suggest_peers_advanced(target_ticker, max_peers, prefer_same_country, size_tolerance)`**
   - 高度なスコアリングアルゴリズム
   - 業界・規模・地域を総合評価

3. **`suggest_peers_with_ai(target_ticker, api_key, max_peers)`**
   - Gemini AIによる動的提案
   - 自然言語処理で最適な競合を選定

4. **`_calculate_peer_score(target, peer, prefer_same_country, size_tolerance)`**
   - スコアリング計算（0-130点）

5. **`_get_sector_fallback_peers(sector, country)`**
   - セクター別のフォールバックリスト
   - 日本企業とグローバル企業で異なる

---

### 修正ファイル

#### `scripts/financial_scm_dashboard.py`

**変更箇所:**
- L126-155: 提案モード選択UIを5段階に拡張
  - 🤖 AI提案（高精度）
  - 🔍 自動提案（高度）
  - 📋 自動提案（基本）
  - ✏️ 手動入力
  - 📁 設定から読込

**UIの改善:**
```python
competitor_mode = st.sidebar.radio(
    "選択方法",
    ["🤖 AI提案（高精度）", "🔍 自動提案（高度）", "📋 自動提案（基本）", "✏️ 手動入力", "📁 設定から読込"]
)
```

#### `scripts/analyze_company_cli.py`

**追加オプション:**
```bash
python analyze_company_cli.py \
  --target 7203.T \
  --auto-peers \
  --suggestion-mode advanced  # basic, advanced, ai
```

---

## 🧪 使用例

### ダッシュボードでの使用

1. **ブラウザでダッシュボードを開く**
   ```bash
   streamlit run scripts/financial_scm_dashboard.py
   ```

2. **サイドバーで企業を入力**
   - 対象企業: `AAPL`

3. **提案モードを選択**
   - 🤖 **AI提案（高精度）** を選択
   - AIが自動的に競合を分析

4. **提案結果から選択**
   - 提案: `MSFT, GOOGL, META, AMZN, NVDA, TSLA, NFLX, INTC`
   - 上位3社がデフォルトで選択される

---

### CLIでの使用

#### 例1: AI提案モード
```bash
python scripts/analyze_company_cli.py \
  --target AAPL \
  --auto-peers \
  --suggestion-mode ai
```

**出力:**
```
🔍 Advanced peer suggestion for AAPL...
📊 Target: Apple Inc.
   Industry: Consumer Electronics, Sector: Technology
   Market Cap: $2,800,000,000,000, Country: United States
🤖 AI suggested peers: ['MSFT', 'GOOGL', 'META', 'AMZN']
```

#### 例2: 高度提案モード（日本企業）
```bash
python scripts/analyze_company_cli.py \
  --target 7203.T \
  --auto-peers \
  --suggestion-mode advanced
```

**出力:**
```
🔍 Advanced peer suggestion for 7203.T...
📊 Target: トヨタ自動車株式会社
   Industry: Auto Manufacturers, Sector: Consumer Cyclical
   Market Cap: ¥35,000,000,000,000, Country: Japan
✅ Top 5 peers suggested:
   1. 7267.T - 本田技研工業株式会社 (Score: 100.00)
   2. 7201.T - 日産自動車株式会社 (Score: 95.50)
   3. TM - Toyota Motor Corporation (Score: 80.00)
   4. F - Ford Motor Company (Score: 75.00)
   5. GM - General Motors Company (Score: 70.00)
```

---

## 📈 パフォーマンス比較

| 提案モード | 実行時間 | API呼び出し | 精度 | 推奨ケース |
|-----------|---------|------------|------|-----------|
| 基本 | <1秒 | なし | ⭐⭐⭐ | 既知の業界 |
| 高度 | 2-5秒 | yfinance のみ | ⭐⭐⭐⭐ | 一般的な企業 |
| AI | 5-10秒 | yfinance + Gemini | ⭐⭐⭐⭐⭐ | 高精度が必要な場合 |

---

## ⚙️ 設定

### API Key設定（AI提案モード使用時）

`.env`ファイルに追加:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

### フォールバックリストのカスタマイズ

`scripts/utils/peer_suggestion.py`の`_get_sector_fallback_peers()`を編集:

```python
japan_fallback = {
    'Consumer Cyclical': ['7203.T', '7267.T', '7201.T'],  # 自動車
    'Industrials': ['6301.T', '6305.T', '6326.T'],  # 機械
    # ... カスタマイズ
}
```

---

## 🔧 トラブルシューティング

### 問題1: AI提案が動作しない

**エラー:**
```
⚠️ AI suggestion failed. Falling back to advanced.
```

**解決策:**
1. `.env`ファイルに`GOOGLE_API_KEY`が設定されているか確認
2. APIキーが有効か確認（Gemini API ダッシュボードで確認）
3. インターネット接続を確認

---

### 問題2: yfinance APIエラー

**エラー:**
```
Failed to fetch info for AAPL: 404 Client Error
```

**解決策:**
1. ティッカーシンボルが正しいか確認（`AAPL`, `7203.T`など）
2. yfinanceのバージョンを確認:
   ```bash
   pip install --upgrade yfinance
   ```

---

### 問題3: 提案が0件

**原因:**
- 未知の業界・マイナーな企業
- `industry_peers.json`に定義されていない

**解決策:**
1. **AI提案モード**を使用（最も確実）
2. `industry_peers.json`に業界を追加:
   ```json
   {
     "new_industry": {
       "description": "New Industry",
       "keywords": ["NEW"],
       "global_peers": ["TICK1", "TICK2"],
       "domestic_peers": []
     }
   }
   ```

---

## 🚀 今後の拡張予定

1. **複数AI統合**
   - OpenAI GPT-4o との併用
   - Claude 3.5 Sonnet との統合

2. **地域別最適化**
   - 欧州企業向けフォールバック
   - アジア新興市場対応

3. **業界トレンド分析**
   - M&A動向の考慮
   - 業界再編の自動検出

4. **カスタムスコアリング**
   - ユーザー定義の重み付け
   - 戦略的ポジショニング優先

---

## 📚 関連ドキュメント

- [IMPLEMENTATION_HISTORY.md](./IMPLEMENTATION_HISTORY.md) - 実装履歴・Phase 4全体の改善内容
- [README.md](../README.md) - プロジェクト概要
- [config/industry_peers.json](../scripts/config/industry_peers.json) - 基本提案設定

---

**Created by:** consultant-toolkit project
**Last Updated:** 2026-02-23
**Version:** 2.1.0
