# vault-search.ps1
# Obsidian Vault 全文検索（Local REST API経由）
# 使い方: pwsh -NoProfile -File vault-search.ps1 -Query "<検索語>" [-Limit 20] [-ContextLength 100]

param(
    [Parameter(Mandatory)][string]$Query,
    [int]$Limit = 20,
    [int]$ContextLength = 100
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Import-Module 'C:\Users\iidam\claude-gemini-skills\vault-api\tools\obsidian-api.psm1' -Force -WarningAction SilentlyContinue

$results = Search-ObsidianVault -Query $Query -ContextLength $ContextLength
$totalCount = $results.Count

Write-Output ("検索: '" + $Query + "'")
Write-Output ("ヒット数: " + $totalCount)
Write-Output ""

$shown = if ($Limit -gt 0) { $results | Select-Object -First $Limit } else { $results }
foreach ($r in $shown) {
    Write-Output ("── " + $r.filename)
    foreach ($match in $r.matches) {
        $ctx = $match.context.Trim() -replace '\s+', ' '
        if ($ctx.Length -gt 200) { $ctx = $ctx.Substring(0, 200) + '...' }
        Write-Output ("    " + $ctx)
    }
    Write-Output ""
}

if ($Limit -gt 0 -and $totalCount -gt $Limit) {
    Write-Output ("... 残り " + ($totalCount - $Limit) + " 件は省略")
}
