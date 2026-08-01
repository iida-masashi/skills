# vault-list.ps1
# Obsidian Vault ディレクトリ一覧（Local REST API経由）
# 使い方: pwsh -NoProfile -File vault-list.ps1 [-Path "<Vault相対パス>"]

param(
    [string]$Path = ''
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Import-Module (Join-Path $PSScriptRoot 'obsidian-api.psm1') -Force -WarningAction SilentlyContinue

if ($Path) {
    $result = Get-ObsidianDirList -DirPath $Path
    Write-Output ("ディレクトリ: " + $Path)
} else {
    $result = Get-ObsidianVaultList
    Write-Output "Vaultルート"
}

Write-Output ""
$dirs = $result.files | Where-Object { $_ -match '/$' }
$files = $result.files | Where-Object { $_ -notmatch '/$' }

Write-Output ("ディレクトリ: " + $dirs.Count + " / ファイル: " + $files.Count)
Write-Output ""

Write-Output "📁 ディレクトリ:"
$dirs | Sort-Object | ForEach-Object { Write-Output ("  " + $_) }

Write-Output ""
Write-Output "📄 ファイル:"
$files | Sort-Object | ForEach-Object { Write-Output ("  " + $_) }
