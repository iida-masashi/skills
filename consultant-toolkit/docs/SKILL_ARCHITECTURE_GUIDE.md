# Consultant Toolkit 構造ガイド (Galaxy Standard)

## 1. 概要
本ドキュメントは、`consultant-toolkit` スキルのディレクトリ構成、命名規則、および開発ルールを定義する。本スキルは、SCM/SAPコンサルタントがデータ駆動型の意思決定を行うための高度な分析ツール群を提供する。

## 2. ディレクトリ構造

```text
consultant-toolkit/
├── libs/                        # コア・ロジック（パッケージ本体）
│   └── consultant_toolkit/       # 名前空間パッケージ
│       ├── constants.py          # 全定数の単一定義源
│       ├── gemini_client.py      # Gemini API クライアント生成・エラーハンドリング共通
│       ├── financial_metrics.py  # ROIC, CCC, 流動性, 収益性指標
│       ├── finance_data.py       # yfinance データ取得
│       ├── ai_analytics.py       # Prophet予測, 異常検知, LLMクエリ
│       ├── peer_suggestion.py    # 3段階競合提案エンジン
│       ├── company_search.py     # 829社+ 企業名→Ticker変換
│       ├── segment_analysis.py   # 事業セグメント分析
│       ├── simulation_logic.py   # What-Ifシミュレーション
│       ├── rfp_generator.py      # RFPパッケージ生成
│       ├── config_loader.py      # YAML設定読み込み
│       ├── env_loader.py         # 環境変数管理
│       ├── export_utils.py       # PDF/Excel/Markdownエクスポート
│       ├── excel_utils.py        # Excel操作（Polars）
│       ├── mock_data.py          # PPMシミュレーションデータ
│       ├── retry.py              # リトライ機構・カスタム例外
│       ├── config/               # アプリケーション設定 (YAML, JSON)
│       └── ui_components/        # Streamlit UI コンポーネント（※CLI非依存）
│           ├── ui_helpers.py     # 共通データ構造 (BaseFinancials) / ユーティリティ
│           ├── corporate_peers.py       # Tab1: 競合比較
│           ├── detail_analysis.py       # Tab2: 詳細分析 (orchestrator)
│           ├── detail_financial_trends.py # Tab2.1: 財務推移
│           ├── detail_roic_tree.py      # Tab2.2: ROICツリー
│           ├── detail_ccc.py            # Tab2.3: CCC分析
│           ├── future_simulation.py     # Tab3: 将来予測 (orchestrator)
│           ├── future_whatif.py          # Tab3.1: What-If
│           ├── future_demand_forecast.py # Tab3.2: 需要予測
│           ├── future_capex.py          # Tab3.3: CAPEX
│           └── future_ai_strategy.py    # Tab3.4: AI戦略
├── scripts/                      # 実行エントリポイント
│   ├── app_finance.py            # 財務・SCM 統合分析ダッシュボード
│   ├── app_backlog.py            # ERP PMO / 課題管理ダッシュボード
│   ├── app_market_watch.py       # 市場動向・テクニカル分析ダッシュボード
│   ├── app_marketing.py          # AIブランド評判分析ダッシュボード
│   ├── analyze_company_cli.py    # 汎用企業分析CLI
│   ├── fetch_finance_data.py     # 財務データ取得CLI
│   ├── excel_to_csv_cli.py       # Excel→CSV変換CLI
│   ├── generate_report.py        # 週次レポート生成
│   ├── generate_rfp_package.py   # RFPパッケージ生成CLI
│   └── data_analyzer.py          # Polarsデータ分析CLI
├── tests/                        # Pytest スイート
│   ├── integration/              # 統合・CLIテスト
│   └── *.py                      # ユニットテスト
├── data/                         # 実行時データ (CSV等)
├── docs/                         # ドキュメント
├── templates/                    # Excelテンプレート (WBS, Issue Log)
├── references/                   # CLIコマンド一覧（Progressive Disclosure用）
├── pyproject.toml                # プロジェクト定義・依存管理
└── SKILL.md                      # スキル定義（Gemini CLI用）
```

## 3. 命名規則

### 3.1 実行スクリプト (`scripts/`)
- Streamlit アプリケーションは `app_{機能名}.py` で統一する。
- CLI ツールは `{機能名}_cli.py` で統一する。

### 3.2 パッケージモジュール (`libs/`)
- 全てのスネークケース (`snake_case`) を使用する。
- 略称（`utils` 等）は許容するが、意味が明確であること。

## 4. 開発・運用ルール

### 4.1 インポート・パス
`pyproject.toml` の `[tool.setuptools.packages.find]` により、`pip install -e .` で `consultant_toolkit` が正規パッケージとしてインストールされる。

```python
# 正しいインポート方法
from consultant_toolkit.financial_metrics import calculate_roic
from consultant_toolkit.constants import DAYS_PER_YEAR, WACC_BENCHMARK
```

**禁止パターン:**
```python
# NG: sys.path 操作は不要（削除済み）
sys.path.insert(0, libs_path)

# NG: 相対的な不透明パス
from utils.finance_data import ...
```

### 4.2 定数管理
全ての共有定数は `consultant_toolkit.constants` に一元管理する。
各モジュールで独自に `DAYS_PER_YEAR = 365` 等を定義してはならない。

```python
# 正しい使い方
from consultant_toolkit.constants import DAYS_PER_YEAR, DEFAULT_TAX_RATE
```

### 4.3 環境変数
`os.environ` を直接操作（特に `del os.environ[...]`）してはならない。
必ず `consultant_toolkit.env_loader` を使用する。

```python
# 正しい使い方
from consultant_toolkit.env_loader import get_api_key
api_key = get_api_key("GOOGLE_API_KEY")
```

### 4.4 例外処理
`except Exception:` の使用は原則禁止。具体的な例外型を指定する。
ネットワーク系は `retry.py` のカスタム例外クラスを活用する。

```python
# 正しいパターン
except (ConnectionError, TimeoutError) as e:
    logger.error(f"Network error: {e}")

# NG
except Exception:
    pass
```

### 4.5 データアクセス
- コード内でのハードコードされたパスは禁止。
- 実行時データは常に `Path(__file__).resolve().parent.parent / "data"` を基点として参照すること。

### 4.6 品質保証
- コード変更後は必ず `ruff check .` を実行し、警告がないことを確認すること。
- テストは `pytest tests/` で全項目パスすることを完了条件とする（139テスト以上）。

---
*Updated: 2026-04-14 (v5.0 Post-Refactoring)*
