# 開発ガイド

> **対象**: consultant-toolkit プロジェクトの開発者・コントリビューター向けドキュメント

---

## 📋 目次

1. [環境セットアップ](#環境セットアップ)
2. [Pre-commitフックの使用](#pre-commitフックの使用)
3. [テストの実行](#テストの実行)
4. [コード品質チェック](#コード品質チェック)
5. [CI/CDパイプライン](#cicdパイプライン)
6. [リリースプロセス](#リリースプロセス)

---

## 🚀 環境セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/your-org/consultant-toolkit.git
cd consultant-toolkit
```

### 2. 仮想環境の作成

```bash
# Python 3.12以上が必要
python -m venv .venv

# 仮想環境の有効化
# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. 依存関係のインストール

```bash
# パッケージをeditable modeでインストール
pip install -e .

# 開発ツール（テスト・リント・フォーマッター）
pip install pytest pytest-cov black ruff mypy pre-commit
```

### 4. Pre-commitフックのインストール

```bash
pip install pre-commit
pre-commit install
```

---

## 🔧 Pre-commitフックの使用

Pre-commitフックは、コミット前に自動でコード品質チェックを実行します。

### インストール済みフック

1. **Black** - コードフォーマッター
2. **isort** - import文の整理
3. **ruff** - リンター（コード規約チェック）
4. **mypy** - 型チェック（utils/モジュールのみ）
5. **bandit** - セキュリティ脆弱性チェック
6. **yamllint** - YAML構文チェック
7. **markdownlint** - Markdown構文チェック
8. **codespell** - スペルチェック

### 使用方法

#### 自動実行（推奨）

```bash
# 通常通りコミット
git add .
git commit -m "feat: add new feature"

# Pre-commitフックが自動実行される
# エラーがあれば修正してから再コミット
```

#### 手動実行

```bash
# すべてのファイルに対して実行
pre-commit run --all-files

# 特定のフックのみ実行
pre-commit run black --all-files
pre-commit run ruff --all-files
```

#### フックのスキップ（非推奨）

```bash
# 緊急時のみ使用
git commit -m "WIP" --no-verify
```

### フックの更新

```bash
# 最新版のフックに更新
pre-commit autoupdate
```

---

## 🧪 テストの実行

### 基本的なテスト実行

```bash
# すべてのテストを実行
pytest

# 詳細モード
pytest -v

# 特定のファイルのみ
pytest tests/test_financial_metrics.py

# 特定のテストケースのみ
pytest tests/test_financial_metrics.py::TestCalculateROIC::test_calculate_roic_basic
```

### マーカーを使ったテスト分類

```bash
# ユニットテストのみ（高速）
pytest -m unit

# 統合テストを除外
pytest -m "not integration"

# 遅いテストを除外
pytest -m "not slow"
```

### カバレッジレポート

```bash
# カバレッジ付きで実行
pytest --cov=libs/consultant_toolkit --cov-report=html

# ブラウザでレポート表示
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

### 並列実行（高速化）

```bash
# 4プロセスで並列実行
pytest -n 4

# 自動検出（CPU数に応じて調整）
pytest -n auto
```

---

## ✅ コード品質チェック

### コードフォーマット

```bash
# Black（自動フォーマット）
black scripts/ tests/

# チェックのみ（変更なし）
black --check scripts/ tests/

# 差分表示
black --diff scripts/ tests/
```

### インポート整理

```bash
# isortで自動整理
isort scripts/ tests/

# チェックのみ
isort --check scripts/ tests/
```

### リント（コード規約チェック）

```bash
# ruffでチェック
ruff check scripts/ tests/

# 自動修正（必要な場合）
ruff check scripts/ tests/ --fix
```

### 型チェック

```bash
# mypyで型チェック（utils/モジュールのみ）
mypy libs/consultant_toolkit/ --config-file mypy.ini
```

### セキュリティチェック

```bash
# banditでセキュリティ脆弱性チェック
bandit -r scripts/ -ll

# 詳細レポート
bandit -r scripts/ -f json -o bandit_report.json
```

### 総合チェック

```bash
# すべてのチェックを一度に実行
pre-commit run --all-files
```

---

## 🔄 CI/CDパイプライン

### GitHub Actionsワークフロー

プロジェクトには以下のワークフローが設定されています：

#### 1. Tests (`test.yml`)

**トリガー**: Push/PR to main/develop

```yaml
- Python 3.12 のテスト
- ユニットテスト実行
- 統合テスト実行（失敗許容）
```

#### 2. Code Quality (`lint.yml`)

**トリガー**: Push/PR to main/develop

```yaml
- Black フォーマットチェック
- ruff リント
- mypy 型チェック
- bandit セキュリティチェック
```

#### 3. Coverage (`coverage.yml`)

**トリガー**: Push/PR to main/develop

```yaml
- カバレッジ70%以上を要求
- Codecovへアップロード
- HTMLレポート生成（アーティファクト）
- PRへのコメント投稿
```

#### 4. Dependency Review (`dependency-review.yml`)

**トリガー**: PR to main

```yaml
- 依存関係の脆弱性チェック
- ライセンス検証（GPL禁止）
```

#### 5. Release (`release.yml`)

**トリガー**: Tag push (v*.*.*)

```yaml
- テスト実行
- GitHub Releaseの作成
- 変更履歴の自動生成
```

### ローカルでCI/CDをシミュレート

```bash
# すべてのチェックを実行
./scripts/run_ci_locally.sh  # （作成推奨）

# または手動で
pytest -m "not integration" --cov=libs/consultant_toolkit --cov-fail-under=70
black --check libs/ scripts/ tests/
ruff check libs/ scripts/ tests/
mypy libs/consultant_toolkit/ --config-file mypy.ini
```

---

## 🚢 リリースプロセス

### バージョン番号の決定

[Semantic Versioning](https://semver.org/) に従います：

- **Major (X.0.0)**: 破壊的変更
- **Minor (0.X.0)**: 新機能追加（後方互換性あり）
- **Patch (0.0.X)**: バグ修正

### リリース手順

#### 1. バージョン更新

```bash
# pyproject.toml のバージョンを更新
version = "3.1.0"
```

#### 2. 変更履歴の作成

```bash
# CHANGELOG.md を更新
## [3.1.0] - 2026-02-22

### Added
- 新機能の説明

### Fixed
- バグ修正の説明
```

#### 3. コミット & タグ作成

```bash
git add .
git commit -m "chore: bump version to 3.1.0"

# タグ作成
git tag -a v3.1.0 -m "Release v3.1.0"

# リモートへプッシュ
git push origin main
git push origin v3.1.0
```

#### 4. GitHub Releaseの自動作成

タグがプッシュされると、GitHub Actionsが自動で：
- テスト実行
- GitHub Release作成
- 変更履歴の抽出

---

## 📚 コーディング規約

### Python

- **PEP 8** 準拠（Black適用で自動対応）
- 最大行長: **120文字**
- インポート順序: isortで自動整理
- 型ヒント: `utils/` モジュールでは必須

### 命名規則

- 関数・変数: `snake_case`
- クラス: `PascalCase`
- 定数: `UPPER_SNAKE_CASE`
- プライベート: `_leading_underscore`

### Docstring

Google形式を推奨：

```python
def example_function(param1: str, param2: int) -> bool:
    """
    関数の簡潔な説明

    Args:
        param1: 引数1の説明
        param2: 引数2の説明

    Returns:
        戻り値の説明

    Raises:
        ValueError: エラー条件の説明
    """
    pass
```

---

## 🐛 デバッグ

### ログレベルの設定

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### pytest デバッグ

```bash
# 最初の失敗で停止
pytest -x

# 詳細トレースバック
pytest --tb=long

# pdbデバッガ起動
pytest --pdb
```

---

## 🤝 コントリビューション

### プルリクエストのプロセス

1. Issueの作成または既存Issueの確認
2. ブランチ作成: `git checkout -b feature/your-feature`
3. 変更の実装
4. テスト追加
5. Pre-commitフック通過確認
6. PR作成（テンプレートに従って記載）
7. レビュー対応
8. マージ

### コミットメッセージ規約

[Conventional Commits](https://www.conventionalcommits.org/) を推奨：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**例**:
```
feat(financial): add parallel data fetching for multiple companies

Implement ThreadPoolExecutor-based batch fetching to improve
performance by 67% when analyzing multiple companies.

Closes #123
```

**Type**:
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: フォーマット
- `refactor`: リファクタリング
- `test`: テスト
- `chore`: その他

---

## 📞 サポート

質問や問題がある場合：

1. [Issues](https://github.com/your-org/consultant-toolkit/issues) で検索
2. 見つからなければ新しいIssue作成
3. [Discussions](https://github.com/your-org/consultant-toolkit/discussions) で質問

---

**Happy Coding! 🚀**
