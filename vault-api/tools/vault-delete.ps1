# vault-delete.ps1
# Obsidian Vault ファイル削除（Local REST API経由）
# 使い方: pwsh -NoProfile -File vault-delete.ps1 -Path "<Vault相対パス>"

param(
    [Parameter(Mandatory)][string]$Path
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Import-Module (Join-Path $PSScriptRoot 'obsidian-api.psm1') -Force -WarningAction SilentlyContinue

$null = Remove-ObsidianNote -FilePath $Path
Write-Output ("削除完了: " + $Path)
