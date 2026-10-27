<#
.SYNOPSIS
ERP PMO Automation Pipeline Runner (Local Execution)

.DESCRIPTION
このスクリプトは、PMO関連の自動化タスク（RFPパッケージ作成、週次レポート生成）を
一括で実行するパイプラインです。タスクスケジューラなどで定期実行することを想定しています。
#>

$ErrorActionPreference = "Stop"

# プロジェクトのルートディレクトリへ移動
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "[INFO] PMO Automation Pipeline Started." -ForegroundColor Cyan

# 1. 仮想環境・依存関係の同期 (uv 優先)
$UvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($UvCmd) {
    Write-Host "[INFO] Syncing dependencies via uv..."
    uv sync
} else {
    if (-not (Test-Path ".venv")) {
        Write-Host "[INFO] Creating virtual environment (.venv)..."
        python -m venv .venv
    }
    Write-Host "[INFO] Activating virtual environment..."
    . .venv\Scripts\Activate.ps1
    Write-Host "[INFO] Ensuring dependencies are up to date..."
    pip install -q -e .
}

# 2. RFPパッケージテンプレートの生成
if (Test-Path "scripts\generate_rfp_package.py") {
    Write-Host "[INFO] Step 1: Generating RFP Package..."
    if ($UvCmd) {
        uv run python scripts\generate_rfp_package.py
    } else {
        python scripts\generate_rfp_package.py
    }
}

# 3. 週次レポートの生成
if (Test-Path "scripts\generate_report.py") {
    Write-Host "[INFO] Step 2: Generating Weekly Report from Issue Log..."
    if ($UvCmd) {
        uv run python scripts\generate_report.py
    } else {
        python scripts\generate_report.py
    }
}

Write-Host "[INFO] PMO Automation Pipeline Completed Successfully!" -ForegroundColor Green
