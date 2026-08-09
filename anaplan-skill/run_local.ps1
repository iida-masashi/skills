# ローカルでStreamlitダッシュボード（Model Analyzer）を起動するスクリプト。
#
# 必要な環境変数（実行前に $env:NAME = "..." で設定しておくこと）:
#   ANAPLAN_USER / ANAPLAN_PASSWORD      - Anaplanログイン情報
#   ANAPLAN_WS / ANAPLAN_MODEL           - Workspace ID / Model ID（省略可、画面からも入力可）
#   APP_LOGIN_USER                       - アプリ内ログイン画面のユーザー名
#   APP_LOGIN_PASSWORD_HASH              - 上記パスワードのbcryptハッシュ
#                                           (生成: uv run python -c "import streamlit_authenticator as stauth; print(stauth.Hasher.hash('パスワード'))")
#   APP_COOKIE_KEY                       - 認証クッキーの署名鍵（任意の乱数文字列）
#
# 例:
#   $env:ANAPLAN_USER = "you@example.com"
#   $env:ANAPLAN_PASSWORD = "..."
#   $env:APP_LOGIN_USER = "admin"
#   $env:APP_LOGIN_PASSWORD_HASH = "<bcryptハッシュ>"
#   $env:APP_COOKIE_KEY = "<任意の乱数文字列>"
#   pwsh -File run_local.ps1
#
# .env ファイルから読み込みたい場合は -EnvFile で指定する
# （このリポジトリと同じ形式で ANAPLAN_USER="..." のように書かれたファイルを想定）:
#   pwsh -File run_local.ps1 -EnvFile "C:\path\to\.env"

param(
    [string]$EnvFile
)

if ($EnvFile) {
    if (-not (Test-Path $EnvFile)) {
        Write-Error "指定された .env ファイルが見つかりません: $EnvFile"
        exit 1
    }
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"?([^"]*)"?\s*$') {
            Set-Item -Path "env:$($matches[1])" -Value $matches[2]
        }
    }
}

$required = @('ANAPLAN_USER', 'ANAPLAN_PASSWORD', 'APP_LOGIN_USER', 'APP_LOGIN_PASSWORD_HASH', 'APP_COOKIE_KEY')
$missing = $required | Where-Object { -not (Get-Item -Path "env:$_" -ErrorAction SilentlyContinue) }
if ($missing) {
    Write-Error "以下の環境変数が未設定です: $($missing -join ', ')`nスクリプト冒頭のコメントを参照して設定してください。"
    exit 1
}

Set-Location $PSScriptRoot
uv run streamlit run libs/model_analyzer/dashboard.py
