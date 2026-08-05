# vault-mkdir.ps1
# Obsidian Vault フォルダ新規作成（Local REST API経由。`.gitkeep`書き込みによる合成操作）
# 使い方: pwsh -NoProfile -File vault-mkdir.ps1 -Path "<Vault相対フォルダパス>" [-Vault awa|religion]

param(
    [Parameter(Mandatory)][string]$Path,
    [string]$Vault
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Import-Module (Join-Path $PSScriptRoot 'obsidian-api.psm1') -Force -WarningAction SilentlyContinue

$result = New-ObsidianFolder -FolderPath $Path -Vault $Vault
Write-Output ("フォルダ作成完了: " + $result.Folder)
Write-Output ("(マーカーファイル: " + $result.MarkerFile + " — このフォルダに実ノートを書き込んだら削除して構わない)")
