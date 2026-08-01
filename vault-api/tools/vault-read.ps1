# vault-read.ps1
# Obsidian Vault ファイル読み取り（Local REST API経由）
# 使い方: pwsh -NoProfile -File vault-read.ps1 -Path "<Vault相対パス>" [-Lines N]

param(
    [Parameter(Mandatory)][string]$Path,
    [int]$Lines = 0  # 0なら全文
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Import-Module (Join-Path $PSScriptRoot 'obsidian-api.psm1') -Force -WarningAction SilentlyContinue

$content = Get-ObsidianNote -FilePath $Path

if ($Lines -gt 0) {
    $allLines = $content -split "`n"
    $output = ($allLines | Select-Object -First $Lines) -join "`n"
    Write-Output $output
    Write-Output ""
    Write-Output ("--- " + $Lines + " / " + $allLines.Count + " 行表示 ---")
} else {
    Write-Output $content
}
