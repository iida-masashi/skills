# Consultant Toolkit

> 経営コンサルタントの「泥臭い作業」から「高度な戦略立案」までを、最新の Gemini AI で自動化する最強のツールキットです。

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

---

## 📊 主な機能

### 🎯 AIコンサルティング・ダッシュボード

#### 1. **企業・SCM財務分析ダッシュボード** (Enterprise Edition)
- **階層化ナビゲーション**: 目的別の3つのメインカテゴリとサブタブ構造による直感的な操作性
    - **📂 全社・競合比較**: 競合ベンチマーク（KPI比較・レーダーチャート）、全社ROIC動向（PPM）、事業セグメント分析
    - **🌳 詳細収益・効率分析**: 財務推移、詳細ROICツリー分解、CCC（運転資本）詳細
    - **🏗️ 投資・将来シミュレーション**: 統合What-Ifシミュレーター（ROIC/FCF連動）、需要予測インパクト試算、CAPEX効率分析
- **AI戦略アドバイザリー**: Gemini 3.1 による双方向対話型コンサルティング。戦略オプション提示、供給網リスク・レジリエンス診断を搭載
- **コンポーネント指向設計**: 各分析モジュールを独立させ、高度なメンテナンス性と拡張性を実現
- **広範な企業対応**: 829社以上の企業名→Ticker変換、半導体商社・自動車・電機など全業種対応

#### 2. **マーケット分析ダッシュボード**
- グローバル市場ヒートマップ
- セクターローテーション分析（RRG）
- コモディティ価格予測（Prophet）
- テクニカル指標分析（RSI, MACD, Bollinger Bands）

#### 3. **ブランド評判分析ダッシュボード**
- Google Trends統合
- Webセンチメント分析
- 競合ポジショニングマップ
- 自動競合企業探索

#### 4. **ERP PMO Galaxy Dashboard** (`app_backlog.py`)
Backlog API と Gemini AI を連携した ERP 導入プロジェクト向けインタラクティブ PMO ダッシュボード：

```bash
.venv/Scripts/streamlit run scripts/app_backlog.py
```

**タブ構成と機能：**

| タブ | 主な機能 |
|------|---------|
| 📊 Executive View (AI) | AI SteerCo Report・AI 週次サマリー自動生成・バーンアップチャート・**納期予測（線形回帰）** |
| 🧩 Module Status | モジュール別進捗・リスクヒートマップ・工数予実（EVM） |
| 👤 Resource Load | 個人別タスク負荷・**週次ベロシティトレンド（4週移動平均）** |
| 🚨 Delayed & At-Risk | 期限超過/期限間近/工数超過タスク・**コメントリスク AI 分析** |
| 📅 1-Week Deadlines | 直近1週間の期限タスク一覧 |
| 📅 Timeline & Backlog | ガントチャート（直近30件） |
| 🔍 Raw Data | フィルタ済みデータテーブル・**タスク詳細ドロワー** |

**その他の特徴：**
- 全テーブルの IssueKey が Backlog URL へのクリッカブルリンク
- サイドバーに最終データ取得時刻を常時表示（JST）
- 週次レポートの Markdown ダウンロード機能

### 🛠️ CLI ツール

#### **汎用企業分析CLI** (New!)
任意の企業・業界で財務・SCM分析を実行：

```bash
# 自動競合提案付き分析
python scripts/analyze_company_cli.py --target 5988.T --auto-peers

# 手動で競合指定
python scripts/analyze_company_cli.py --target 7203.T --competitors 7267.T,7201.T
```

**特徴**:
- 業界別の自動競合提案
- ROIC, CCC, DIO/DSO/DPO 自動計算
- Gemini/OpenAI による AI 分析（自動フォールバック）

#### **財務データ取得CLI**
```bash
# 基本データ取得
python scripts/fetch_finance_data.py --ticker AAPL

# トレンド分析付き
python scripts/fetch_finance_data.py --ticker 5988.T --trends
```

---

## 🚀 クイックスタート

### 1. インストール

```bash
# リポジトリをクローン（consultant-toolkit はモノレポ内のサブフォルダ）
git clone https://github.com/iida-masashi/skills.git
cd skills/consultant-toolkit

# 依存パッケージをインストール（editable mode）
pip install -e .
```

### 2. 環境変数設定

プロジェクトルートに `.env` ファイルを作成：

```env
# 必須
GOOGLE_API_KEY=your_gemini_api_key_here

# オプション（OpenAI フォールバック用）
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. ダッシュボード起動

```bash
# 企業・SCM分析ダッシュボード
.venv/Scripts/streamlit run scripts/app_finance.py

# ERP PMO Galaxy Dashboard
.venv/Scripts/streamlit run scripts/app_backlog.py

# マーケット分析ダッシュボード
.venv/Scripts/streamlit run scripts/app_market_watch.py

# ブランド評判分析ダッシュボード
.venv/Scripts/streamlit run scripts/app_marketing.py
```

### 4. CLI ツール使用例

```bash
# 自動車部品メーカーの分析
python scripts/analyze_company_cli.py --target 5988.T --auto-peers

# 食品メーカーの分析
python scripts/analyze_company_cli.py --target 2229.T --auto-peers

# 半導体商社の分析
python scripts/analyze_company_cli.py --target 7433.T --auto-peers

# トヨタの分析（手動で競合指定）
python scripts/analyze_company_cli.py \
  --target 7203.T \
  --competitors 7267.T,7201.T
```

---

## 📁 プロジェクト構造

```
consultant-toolkit/
├── libs/consultant_toolkit/            # コアライブラリ
│   ├── financial_metrics.py           # 財務計算（ROIC, CCC等）
│   ├── finance_data.py                # データ取得（yfinance）
│   ├── gemini_client.py               # Gemini API クライアント生成・エラーハンドリング共通
│   ├── ai_analytics.py                # AI分析（Prophet予測・異常検知・LLMクエリ）
│   ├── peer_suggestion.py             # 競合提案エンジン（3段階: 設定/スコア/AI）
│   ├── company_search.py              # 企業名→Ticker変換（829社対応、日本語対応）
│   ├── segment_analysis.py            # セグメント分析
│   ├── simulation_logic.py            # What-Ifシミュレーションロジック
│   ├── constants.py                   # 全定数の単一定義源（DAYS_PER_YEAR等）
│   ├── export_utils.py                # エクスポートユーティリティ
│   ├── excel_utils.py                 # Excel操作ユーティリティ
│   ├── rfp_generator.py               # RFPパッケージ生成
│   ├── mock_data.py                   # モックデータ
│   ├── config_loader.py               # 設定読み込み
│   ├── env_loader.py                  # 環境変数管理
│   ├── retry.py                       # リトライ機構
│   ├── config/
│   │   ├── app_config.yaml            # アプリケーション設定（企業・色定義）
│   │   └── industry_peers.json        # 業界別競合マッピング
│   └── ui_components/
│       ├── ui_helpers.py              # 共通データ構造・ユーティリティ (BaseFinancials等)
│       ├── corporate_peers.py         # Tab1: 競合比較・セグメント分析
│       ├── detail_analysis.py         # Tab2: 詳細分析オーケストレータ
│       ├── detail_financial_trends.py # Tab2.1: 財務推移分析
│       ├── detail_roic_tree.py        # Tab2.2: ROICツリー分解
│       ├── detail_ccc.py              # Tab2.3: CCC運転資本詳細
│       ├── future_simulation.py       # Tab3: 将来シミュレーションオーケストレータ
│       ├── future_whatif.py           # Tab3.1: What-Ifシミュレーター
│       ├── future_demand_forecast.py  # Tab3.2: 需要予測インパクト
│       ├── future_capex.py            # Tab3.3: CAPEX効率分析
│       └── future_ai_strategy.py      # Tab3.4: AI SCM戦略提案
├── scripts/
│   ├── app_finance.py                 # 企業・SCM財務分析ダッシュボード
│   ├── app_backlog.py                 # ERP PMO Galaxy Dashboard (Backlog連携)
│   ├── app_market_watch.py            # マーケット分析ダッシュボード
│   ├── app_marketing.py               # ブランド評判ダッシュボード
│   ├── analyze_company_cli.py         # 汎用企業分析CLI
│   ├── fetch_finance_data.py          # 財務データ取得CLI
│   ├── excel_to_csv_cli.py            # Excel→CSV変換CLI
│   ├── data_analyzer.py               # データ分析ユーティリティ
│   ├── generate_report.py             # レポート生成
│   └── generate_rfp_package.py        # RFPパッケージ生成
├── tests/                              # テスト
├── docs/                               # ドキュメント
├── templates/                          # Excelテンプレート
├── pyproject.toml                      # パッケージ定義・依存管理
├── mypy.ini                            # 型チェック設定
└── README.md                           # 本ファイル
```

---

## 🔧 設定のカスタマイズ

### 企業設定の追加

`libs/consultant_toolkit/config/app_config.yaml` を編集：

```yaml
companies:
  your_company:
    ticker: "1234.T"
    display_name: "Your Company"
    color: "#ff0000"

financial:
  default_cogs_ratio: 0.75   # 原価率デフォルト（COGSが取得できない場合）
  default_tax_rate: 0.30     # 実効税率デフォルト（赤字・異常値の場合）
```

### 企業検索データベース

`libs/consultant_toolkit/company_search.py` に **829社以上**の企業名→Tickerマッピングを収録：
- 日本企業（東証プライム）: 自動車・電機・半導体商社・金融・通信・医薬・建設など全業種
- 米国企業（NYSE/NASDAQ）: S&P500 主要銘柄 / Big Tech / ETF など
- 欧州・アジア企業も収録

企業名で検索すると fuzzy matching で自動候補表示。日本語名にも対応。

### 業界別競合マッピング

`libs/consultant_toolkit/config/industry_peers.json` を編集：

```json
{
  "your_industry": {
    "keywords": ["1234", "5678"],
    "domestic_peers": ["1234.T", "5678.T"],
    "global_peers": ["AAPL", "MSFT"],
    "description": "Your Industry Description"
  },
  "semiconductor_trading": {
    "keywords": ["7433", "3132", "8154"],
    "domestic_peers": ["3132.T", "8154.T", "8141.T", "8150.T", "9880.T"],
    "global_peers": ["AVT", "ARW", "WCC"],
    "description": "Semiconductor & Electronics Trading / Distribution (Japan)"
  }
}
```

> **Note**: 日本企業（`.T` ティッカー）では `domestic_peers` が先に表示されます。

---

## 📚 ドキュメント

### ユーザー向け
- **[docs/UNIVERSAL_ANALYSIS_GUIDE.md](docs/UNIVERSAL_ANALYSIS_GUIDE.md)** - 汎用分析CLI使用ガイド
- **[docs/COMPANY_NAME_SEARCH.md](docs/COMPANY_NAME_SEARCH.md)** - 企業名・Ticker検索機能
- **[docs/PEER_SUGGESTION_ENHANCEMENT.md](docs/PEER_SUGGESTION_ENHANCEMENT.md)** - 競合企業自動提案（3段階）
- **[docs/SEGMENT_ANALYSIS_FEATURE.md](docs/SEGMENT_ANALYSIS_FEATURE.md)** - セグメント分析仕様
- **[docs/ROIC_SIMULATION_FEATURE.md](docs/ROIC_SIMULATION_FEATURE.md)** - ROIC改善シミュレーション

### 開発者向け
- **[docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md)** - 開発環境セットアップ・CI/CD
- **[docs/IMPLEMENTATION_HISTORY.md](docs/IMPLEMENTATION_HISTORY.md)** - リファクタリング実装履歴

---

## 🧪 開発者向け

### 型チェック

```bash
mypy scripts/
```

### テスト実行

```bash
pytest tests/
pytest --cov=scripts --cov-report=html tests/
pytest -m "not integration and not slow"
```

### コードフォーマット

```bash
black scripts/
```

---

## 🤝 コントリビューション

プルリクエスト歓迎！以下の点にご注意ください：

1. **コード品質**: 型ヒントを追加し、docstringを記載
2. **テスト**: 新機能には単体テストを追加
3. **ドキュメント**: README更新を忘れずに

---

## 📝 ライセンス

MIT License - 詳細は [LICENSE](../LICENSE) を参照

---

## 🙏 謝辞

- **Gemini AI** - 高度な分析とコンサルティング提案
- **yfinance** - 財務データ取得
- **Streamlit** - インタラクティブダッシュボード
- **Plotly** - 美しい可視化

---

## 📞 サポート

問題や質問がある場合:
- [Issues](https://github.com/iida-masashi/skills/issues) で報告
- [Discussions](https://github.com/iida-masashi/skills/discussions) で質問

---

**Built with ❤️ by consultant-toolkit project**
