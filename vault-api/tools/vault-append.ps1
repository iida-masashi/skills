# vault-append.ps1
# Obsidian Vault ファイル末尾追記（Local REST API経由）
# 使い方:
#   pwsh -NoProfile -File vault-append.ps1 -Path "<Vault相対パス>" -Content "<追記内容>" [-Vault awa|religion]
#   または
#   pwsh -NoProfile -File vault-append.ps1 -Path "<Vault相対パス>" -ContentFile "<追記内容ファイルパス>" [-Vault awa|religion]

param(
    [Parameter(Mandatory)][string]$Path,
    [string]$Content = '',
    [string]$ContentFile = '',
    [string]$Vault
)

Import-Module (Join-Path $PSScriptRoot 'obsidian-api.psm1') -Force -WarningAction SilentlyContinue

if ($ContentFile) {
    if (-not (Test-Path -LiteralPath $ContentFile)) {
        throw "ContentFile not found: $ContentFile"
    }
    $Content = Get-Content -LiteralPath $ContentFile -Raw -Encoding UTF8
}

if (-not $Content) {
    throw "Content または ContentFile を指定してください"
}

$null = Append-ObsidianNote -FilePath $Path -Content $Content -Vault $Vault
Write-Output ("✅ 追記完了: " + $Path + " (" + $Content.Length + " 文字)")
