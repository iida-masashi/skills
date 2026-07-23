# 実装履歴 - consultant-toolkit リファクタリング記録

> **最新更新日**: 2026-04-14
> **最終バージョン**: 3.2.0
> **ステータス**: ✅ Phase 5 共通処理統合・品質改善完了

---

## Phase 5: 共通処理統合・品質改善 (2026-04-14)

### 背景

Phase 4 完了後に残っていた共通処理の重複、`except Exception` の broad catch、依存不足、統合テストの設計問題を一括解消。

### 実施内容

| # | 改善項目 | 変更内容 |
|---|---------|---------|
| 1 | **gemini_client.py 新設** | `create_gemini_client()`, `generate_text()`, `handle_gemini_api_error()`, `DEFAULT_MODEL` 定数を集約。11箇所の `genai.Client()` 直接呼び出しを全て置換 |
| 2 | **Gemini API エラーハンドリング統一** | `future_ai_strategy.py` 内3箇所の重複エラーハンドリングブロックを `handle_gemini_api_error()` に集約 |
| 3 | **load_markdown_asset 移動** | `app_finance.py` のローカル関数を `ui_helpers.py` に移動。`except Exception` も `except OSError` に絞り込み |
| 4 | **except Exception 絞り込み (3箇所)** | `constants.py`: 2つの try ブロックを1つに統合し `(ImportError, NameError, KeyError, TypeError)` に。`config_loader.py`: `(OSError, yaml.YAMLError)` に。`excel_utils.py`: `(OSError, ModuleNotFoundError, ValueError)` + `from e` で例外チェイン追加 |
| 5 | **fastexcel 依存追加** | `pyproject.toml` に `fastexcel>=0.7.0` を追加。polars の `read_excel` に必要 |
| 6 | **統合テスト修正** | `test_dashboard_integration.py`: `import app_finance` (モジュールレベルで Streamlit/Gemini 実行) を `from consultant_toolkit.mock_data import` に変更。不要な `mock_streamlit` フィクスチャ削除 |
| 7 | **scripts の genai.Client 一掃** | `analyze_company_cli.py`, `app_market_watch.py`, `app_marketing.py`, `app_backlog.py` の直接呼び出しを `create_gemini_client()` に置換。未使用 `genai` import 削除 |
| 8 | **テストモック重複排除** | `test_ui_helpers.py` のローカルモック5関数を `conftest.py` からのインポートに統一 |
| 9 | **app_finance.py E402 解消** | docstring 前の `import os` 削除で E402 14件が全て解消 |

### 成果

| 指標 | Before (v3.1) | After (v3.2) |
|------|--------------|-------------|
| テストケース数 | 197 | 199 (+2: conftest 共通化に伴うテスト修正) |
| テスト結果 | 197 passed, 2 failed | **199 passed, 0 failed** |
| genai.Client 直接呼び出し | 11箇所 | **0箇所** (gemini_client.py に一元化) |
| except Exception (コア) | 8箇所 | **4箇所** (全て設計上正当) |
| カバレッジ | 未計測 | **64%** |
| ruff | All checks passed | All checks passed |
| E402 (app_finance.py) | 14件 | **0件** |

---

## Phase 4: UI コンポーネント分割 (2026-04-14)

### 背景

Phase 3 の残課題であった `detail_analysis.py` (1692行) と `future_simulation.py` (1648行) の巨大ファイル分割を実施。

### 実施内容

| # | 改善項目 | 変更内容 |
|---|---------|---------|
| 1 | **ui_helpers.py 新設** | `BaseFinancials` dataclass と `load_base_financials()`, `color_by_sign()` を共通モジュールとして抽出。各UIコンポーネント間の重複コード (データ取得・フォールバック処理) を集約 |
| 2 | **detail_analysis.py 分割** | 1692行 -> 3ファイル: `detail_financial_trends.py` (252行), `detail_roic_tree.py` (370行), `detail_ccc.py` (520行)。`detail_analysis.py` はオーケストレータ (65行) に縮小 |
| 3 | **future_simulation.py 分割** | 1648行 -> 4ファイル: `future_whatif.py` (762行), `future_demand_forecast.py` (107行), `future_capex.py` (221行), `future_ai_strategy.py` (380行)。`future_simulation.py` はオーケストレータ (73行) に縮小 |
| 4 | **test_ui_helpers.py** | `BaseFinancials`, `load_base_financials`, `color_by_sign` の21テスト |
| 5 | **render関数スモークテスト** | 全8 UIコンポーネントのrender関数スモークテスト (17テスト, 7ファイル)。Streamlit モック (`_SessionState`, `_make_st_mock`) を `conftest.py` に集約 |
| 6 | **ドキュメント更新** | README.md, SKILL_ARCHITECTURE_GUIDE.md のプロジェクト構造図を更新 |

### 成果

| 指標 | Before (v3.0) | After (v3.1) |
|------|--------------|-------------|
| テストケース数 | 139 | 197 (+58) |
| 最大ファイル行数 (ui_components) | 1,692行 | 762行 |
| UIコンポーネントファイル数 | 3 | 11 (+ ui_helpers) |
| テスト結果 | 139 passed | 197 passed |
| ruff | All checks passed | All checks passed |

---

## Phase 3: コード品質・構造改善 (2026-04-14)

### 実施内容

| # | 改善項目 | 変更内容 |
|---|---------|---------|
| 1 | **sys.path ハック全廃** | 8スクリプトから `sys.path.insert` を削除。`pyproject.toml` に `[tool.setuptools.packages.find]` を追加し `pip install -e .` で正規パッケージ化 |
| 2 | **constants.py 新設** | `DAYS_PER_YEAR`, `DEFAULT_TAX_RATE`, `WACC_BENCHMARK` 等の散在定数を一元管理。financial_metrics.py, simulation_logic.py, corporate_peers.py, app_finance.py から参照統一 |
| 3 | **重複関数の統合** | `finance_data.get_safe_value` を `financial_metrics.get_val_safe` のエイリアスに変更 |
| 4 | **except Exception 削減** | コアライブラリ9箇所の broad exception を具体的な例外型（ConnectionError, ValueError, KeyError等）に置換 |
| 5 | **os.environ 直接操作の排除** | segment_analysis.py の `os.environ.get` を env_loader に統一。future_simulation.py の `del os.environ["GOOGLE_CLOUD_PROJECT"]` 2箇所を削除 |
| 6 | **Python バージョン統一** | mypy.ini (3.10->3.12), pre-commit (python3.10->3.12), README バッジ (3.10+->3.12+) |
| 7 | **依存バージョン固定** | pyproject.toml で全11パッケージに最低バージョン指定（`google-genai>=1.0.0` 等） |
| 8 | **pre-commit フック更新** | black 24.1.1->25.1.0, ruff v0.2.0->v0.11.6, mypy v1.8.0->v1.15.0 等 8フック |
| 9 | **テスト追加** | 5新規テストファイル・35テスト追加（test_constants, test_simulation_logic, test_ai_analytics, test_segment_analysis, test_company_search） |
| 10 | **README 全面更新** | スクリプト名・プロジェクト構造図・インストール手順を実態に合わせて修正 |
| 11 | **ドキュメント整合** | SKILL.md, scripts_usage.md, SKILL_ARCHITECTURE_GUIDE.md, DEVELOPMENT_GUIDE.md を現行コードに合わせて更新 |
| 12 | **壊れたimport修正** | excel_to_csv_cli.py の `from scripts.utils.excel_utils` を `from consultant_toolkit.excel_utils` に修正 |

### 成果

| 指標 | Before (v2.0) | After (v3.0) |
|------|--------------|-------------|
| テストケース数 | 104 | 139 (+35) |
| sys.path ハック | 8箇所 | 0箇所 |
| except Exception (コア) | 15箇所 | 6箇所 |
| マジックナンバー重複定義 | 12箇所 | 1箇所 (constants.py) |
| os.environ 直接操作 | 4箇所 | 0箇所 |
| テスト結果 | 104 passed | 139 passed |

### 残課題

- ~~`detail_analysis.py` (1692行) と `future_simulation.py` (1648行) の分割~~ -> **Phase 4 で完了**
- UI コンポーネントの `except Exception` (約20箇所) は Streamlit のエラー表示用途のため現状維持

---

## Phase 2: エンタープライズグレード化 (2026-02-22, v2.0.0)

### 最終成果サマリー

| カテゴリ | 指標 | Before | After | 改善率 |
|----------|------|--------|-------|--------|
| コード削減 | 冗長コード行数 | 492行 | 0行 | **-100%** |
| テスト | テストケース数 | 0 | 115 | **新規** |
| カバレッジ | コードカバレッジ | 0% | 70%+ | +70%p |
| パフォーマンス | データ取得時間 | 15秒 | 3-5秒 | **-67%** |
| パフォーマンス | メモリ使用量 | 100% | 80% | **-20%** |
| 品質 | 略語使用箇所 | 4箇所 | 0箇所 | -100% |
| CI/CD | ワークフロー数 | 0 | 5 | 新規 |

---

## Phase 1: 基盤整備

### 1.1 コード重複の排除
- `financial_scm_dashboard.py` から重複関数を削除（95行）
- `get_val_safe()`, `calculate_financial_metrics()`, `calculate_ccc_metrics()` を `utils/financial_metrics.py` に統一
- 企業特化スクリプト2ファイル削除（-188行）
- **作成モジュール**: `utils/env_loader.py`, `utils/finance_data.py`, `utils/financial_metrics.py`

### 1.2 マジックナンバーの設定外部化
- **作成ファイル**: `config/app_config.yaml`（140行）、`utils/config_loader.py`（120行）
- 外部化した設定: 企業設定、財務定数（WACC・目標利益率）、UI定数、キャッシュTTL

### 1.3 エラーハンドリングの強化
- **作成ファイル**: `utils/retry.py`（140行）— 指数バックオフ付きリトライデコレータ
- 広い `except Exception` を具体的例外型に分割（ConnectionError / ValueError / KeyError 等）

---

## Phase 2: コード品質向上

### 2.1 長い関数の分割
- `ensure_historical_marginal_profit_data()`: 118行 → 60行 + 5ヘルパー関数
- `analyze_with_ai()`: 106行 → 30行 + 3ヘルパー関数（プロンプト生成・Gemini呼び出し・OpenAI呼び出しを分離）

### 2.2 命名規約の統一
- 略語変数 `pl`, `bs` → `income_statement_df`, `balance_sheet_df`
- 全関数 snake_case 統一（検証済み）

### 2.3 ドキュメント整備
- `README.md` 完全書き換え（244行）
- 全主要スクリプトにモジュール/関数 docstring 追加（Google形式）

---

## Phase 3: 保守性・拡張性向上

### 3.1 パフォーマンス最適化
- `fetch_financial_data_batch()` 実装（ThreadPoolExecutor、5並列処理）
- 主要関数に `@st.cache_data(ttl=3600)` を統一適用
- データ取得時間 15秒 → 3-5秒（67%短縮）

### 3.2 型ヒントの導入
- `utils/` 配下の全モジュールに型ヒント100%適用
- `mypy.ini` 作成（Python 3.10対応、utils は厳格モード）

### 3.3 テストコードの作成

| テストファイル | ケース数 |
|---|---|
| `test_financial_metrics.py` | 12 |
| `test_finance_data.py` | 11 |
| `test_config_loader.py` | 11 |
| `test_retry.py` | 14 |
| `test_env_loader.py` | 16 |
| `test_calculate_metrics_edge_cases.py` | 33 |
| `test_batch_operations.py` | 8 |
| `test_error_scenarios.py` | 21 |
| `integration/test_cli.py` | 7 |
| `integration/test_dashboard_integration.py` | 9 |
| **合計** | **142** |

---

## CI/CD・品質自動化

### GitHub Actions ワークフロー（`.github/workflows/`）
- `test.yml` — Python 3.10/3.11/3.12 マトリックステスト
- `lint.yml` — Black / ruff / mypy / bandit
- `coverage.yml` — カバレッジ70%以上を要求、Codecov連携
- `dependency-review.yml` — 脆弱性・ライセンス検証
- `release.yml` — タグプッシュ時の自動リリース

### Pre-commit フック（`.pre-commit-config.yaml`）
Black, isort, ruff, mypy, bandit, yamllint, markdownlint, codespell, pre-commit-hooks（9フック）

---

## Phase 4: ダッシュボード汎用化（2026-02-22〜23）

特定企業固有から任意企業対応への全面汎用化。

- **会社名→Ticker変換**: `utils/company_search.py`（80社以上、日本語対応）
- **3段階競合提案**: `utils/peer_suggestion.py`（設定ベース / スコアリング / AI）
- **Tab8 What-If シミュレーター**: 利益率・運転資本・投資・包括シミュレーション
- **Tab9 セグメント分析**: `utils/segment_analysis.py`（手動マッピング + Gemini AI 自動抽出）
- **AI Before/After プレビュー**: パラメータ調整の影響をリアルタイム表示
- **ハードコード参照の完全除去**: Tab1〜6 の全企業固有参照を動的化
- **新規指標**: 15種類の追加財務指標

**最終仕様**: 9タブ / 23以上の財務指標 / 80社以上対応

---

## Phase 5: 半導体商社対応・品質改善（2026-03-17）

### 5.1 企業検索データベース拡充

- `utils/company_search.py`: 登録企業数 **99社 → 829社** に拡張
  - 日本企業（東証プライム）: 自動車・電機・金融・通信・医薬・建設・商社・物流など全業種を網羅
  - 米国企業（NYSE/NASDAQ）: Big Tech / 金融 / ヘルスケア / 消費財 / エネルギー / ETF など S&P500 主要銘柄
  - 欧州・アジア企業も追加
- 日本企業（`.T` ティッカー）を検索した場合、`domestic_peers` を優先して返すよう修正（国内競合が先頭に表示される）

### 5.2 半導体商社の同業他社対応

- `scripts/config/industry_peers.json`: `semiconductor_trading` カテゴリ追加
  - 国内: マクニカHD(3132.T)・加賀電子(8154.T)・新光商事(8141.T)・三信電気(8150.T)・イノテック(9880.T)
  - グローバル: AVT・ARW・WCC
- `scripts/config/app_config.yaml`: 上記6社を企業設定に追加
- デフォルト表示件数: **4社 → 5社** に変更

### 5.3 パフォーマンス改善

| 対象 | Before | After |
|---|---|---|
| 競合企業名取得（サイドバー） | 逐次（n回APIコール） | `ThreadPoolExecutor(8)` で並列化 |
| ベンチマーク計算（Tab1.1） | 逐次 N+1 | 企業単位で並列化・元順序維持 |
| ROIC推移計算（Tab1.2） | 逐次 N×M | 企業単位で並列化 |

### 5.4 計算精度の改善

- **NOPAT税率の異常値ガード** (`financial_metrics.py`):
  - 税引前利益が赤字（pretax ≤ 0）または税額が負の場合、デフォルト税率（30%）を適用
  - 税率上限 60% を設定し、データ異常による NOPAT 狂いを防止
- **COGS 業種別フォールバック** (`financial_metrics.py`):
  - COGS が取得できない場合、業種別推定原価率を適用（11業種対応）
  - 半導体商社: 85%、SaaS: 25%、自動車部品: 78% など

### 5.5 コード品質改善

| 改善項目 | ファイル | 内容 |
|---|---|---|
| `import json` 重複削除 | `financial_scm_dashboard.py` | L398 の冗長インポートを削除 |
| config 冗長取得の解消 | `financial_scm_dashboard.py` | COMPANIES/COMPANY_COLORS 構築をループ化。`app_config.yaml` に企業追加するだけで自動反映 |
| カラーパレット拡張 | `financial_scm_dashboard.py` | 8色 → 20色。20社以上選択しても色が重複しない |
| DEFAULT 値の設定ファイル化 | `financial_metrics.py` + `app_config.yaml` | `DEFAULT_COGS_RATIO` / `DEFAULT_TAX_RATE` を `app_config.yaml` で上書き可能に |

### 5.6 UX・エラーハンドリング改善

- **try-except 粒度改善** (`detail_analysis.py`): データ取得と UI 描画を別ブロックに分離。エラー箇所の特定が容易に
- **モックデータの明示** (`detail_analysis.py`): 実データ取得失敗時に原因・対処法を `st.error()` で明示表示
- **GAP分析の改善率** (`detail_analysis.py`): 現状値が 0 以下でも "N/A" ではなく「黒字化が必要」など意味ある文言を表示
- **セグメント JSON バリデーション** (`corporate_peers.py`): `percentage` 合計が 1.0 ± 2% 以外は警告＋二度押し確認。`JSONDecodeError` を個別キャッチ
- **エクスポートボタン無効化** (`financial_scm_dashboard.py`): データ未読込時は `disabled=True` を設定し、ホバー時に案内テキスト表示
- **Gemini API エラー分類** (`future_simulation.py`): 429（レート制限）・401/403（認証エラー）を日本語で個別表示

**最終仕様**: 9タブ / 23以上の財務指標 / **829社**対応 / 半導体商社業界対応
