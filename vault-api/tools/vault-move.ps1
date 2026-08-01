# vault-move.ps1
# Obsidian Vault ファイルのリネーム/移動（Local REST API経由）
# 使い方: pwsh -NoProfile -File vault-move.ps1 -From "<旧Vault相対パス>" -To "<新Vault相対パス>"

param(
    [Parameter(Mandatory)][string]$From,
    [Parameter(Mandatory)][string]$To
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Import-Module (Join-Path $PSScriptRoot 'obsidian-api.psm1') -Force -WarningAction SilentlyContinue

$result = Move-ObsidianNote -FromPath $From -ToPath $To
Write-Output ("移動完了: " + $result.From + " -> " + $result.To + " (" + $result.Bytes + " 文字)")
Write-Output "注意: wikilinkはbasename参照のため、拡張子のみ変更やフォルダ移動ではリンクは切れない。basename自体を変えた場合は他ノートの参照を手動で確認すること。"
