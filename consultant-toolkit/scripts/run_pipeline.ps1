<#
.SYNOPSIS
ERP PMO Automation Pipeline Runner (Local Execution)

.DESCRIPTION
このスクリプトは、PMO関連の自動化タスク（テンプレート作成、週次レポート生成、ダッシュボード作成）を
一括で実行するパイプラインです。タスクスケジューラなどで定期実行することを想定しています。
#>

$ErrorActionPreference = "Stop"

# プロジェクトのルートディレクトリへ移動
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "[INFO] PMO Automation Pipeline Started." -ForegroundColor Cyan

# 1. 仮想環境のチェックと有効化
if (-not (Test-Path ".venv")) {
    Write-Host "[INFO] Creating virtual environment (.venv)..."
    python -m venv .venv
}
Write-Host "[INFO] Activating virtual environment..."
. .venv\Scripts\Activate.ps1

# 2. 依存関係のインストール（必要時のみ更新）
Write-Host "[INFO] Ensuring dependencies are up to date..."
pip install -q -U google-genai python-dotenv polars pandas plotly requests openpyxl xlsxwriter

# 3. フォルダ構成のセットアップ
Write-Host "[INFO] Step 1: Initializing folder structure..."
python create_structure.py

# 4. テンプレートの生成
Write-Host "[INFO] Step 2: Generating templates..."
python scripts\create_templates.py

# 5. 週次レポートの生成
Write-Host "[INFO] Step 3: Generating Weekly Report from Issue Log..."
python scripts\generate_report.py

# 6. (オプション) Backlog AIダッシュボードの生成
# 実行に必要な環境変数または引数があるかチェック
$env:dotenv = ".env"
if (Test-Path $env:dotenv) {
    # .envファイルから環境変数を簡易読み込み (dotenvを使用してもよい)
    Write-Host "[INFO] Found .env file."
}

$spaceId = $env:BACKLOG_SPACE_ID
$projectKey = $env:BACKLOG_PROJECT_KEY

if ($spaceId -and $projectKey) {
    Write-Host "[INFO] Step 4: Generating Backlog AI Dashboard for Project: $projectKey..."
    # API Keyは環境変数 (BACKLOG_API_KEY, GEMINI_STUDIO_API_KEY / GEMINI_API_KEY) で渡される前提
    python scripts\backlog_dashboard_ai_v2.py --space $spaceId --project $projectKey
} else {
    Write-Host "[INFO] Step 4: Skipped Backlog AI Dashboard (BACKLOG_SPACE_ID or BACKLOG_PROJECT_KEY missing)." -ForegroundColor Yellow
}

Write-Host "[INFO] PMO Automation Pipeline Completed Successfully!" -ForegroundColor Green
