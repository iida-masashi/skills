# vault-search.ps1
# Obsidian Vault 全文検索（Local REST API経由）。出力は既定でトークン節約向けに絞る。
# 使い方: pwsh -NoProfile -File vault-search.ps1 -Query "<検索語>" [-Vault cpg]
#   -FilesOnly (別名 -Summary) : ファイル名とヒット数だけ（重複確認向け。約1KB）
#   -Limit N (別名 -Top)        : 表示ファイル数（既定5。0=無制限）
#   -MaxPerFile N               : 1ファイルで表示するヒット数（既定2）
#   -ContextLength N            : ヒット前後の文字数（既定40）
#   -IncludeSources             : sources/ node_modules/ dist/ _work/ quartz/ .obsidian/ 配下も対象にする（既定は除外）
# 並び順: ファイル名に検索語を含むノート → ヒット数の多いノートの順。

param(
    [Parameter(Mandatory)][string]$Query,
    [Alias('Top')][int]$Limit = 5,
    [int]$ContextLength = 40,
    [int]$MaxPerFile = 2,
    [Alias('Summary')][switch]$FilesOnly,
    [switch]$IncludeSources,
    [string]$Vault
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Import-Module (Join-Path $PSScriptRoot 'obsidian-api.psm1') -Force -WarningAction SilentlyContinue

$rawResults = @(Search-ObsidianVault -Query $Query -ContextLength $ContextLength -Vault $Vault)
$allCount = $rawResults.Count

# 既定ではノイズ源（一次資料の取込物・ビルド成果物・作業用）を除外する
$excludeRe = '^(sources|node_modules|dist|_work|quartz|\.obsidian|public|functions)/'
$excluded = 0
if (-not $IncludeSources) {
    $kept = @($rawResults | Where-Object { $_.filename -notmatch $excludeRe })
    $excluded = $allCount - $kept.Count
    $rawResults = $kept
}
$totalCount = $rawResults.Count

# ファイル名に検索語を含むものを先頭、次にヒット数の多い順
$sorted = @($rawResults | Sort-Object `
    @{ Expression = { if ([System.IO.Path]::GetFileNameWithoutExtension($_.filename) -like "*$Query*") { 0 } else { 1 } } }, `
    @{ Expression = { @($_.matches).Count }; Descending = $true })

Write-Output ("検索: '" + $Query + "'")
$head = "ヒット: " + $totalCount + " ファイル"
if ($excluded -gt 0) { $head += "（除外 " + $excluded + " 件: sources/ 等。-IncludeSources で表示）" }
Write-Output $head
Write-Output ""

$shown = if ($Limit -gt 0) { $sorted | Select-Object -First $Limit } else { $sorted }
if ($FilesOnly) {
    # ファイル名のみ。-Limit 未指定でも一覧として20件まで出す
    $shown = if ($PSBoundParameters.ContainsKey('Limit')) { $shown } else { $sorted | Select-Object -First 20 }
    foreach ($r in $shown) { Write-Output ($r.filename + "  [" + @($r.matches).Count + "]") }
}
else {
    foreach ($r in $shown) {
        Write-Output ("── " + $r.filename + "  [" + @($r.matches).Count + "]")
        $prev = ''
        $n = 0
        foreach ($match in $r.matches) {
            if ($n -ge $MaxPerFile) { break }
            $ctx = $match.context.Trim() -replace '\s+', ' '
            $ctx = $ctx -replace '\]\([^)]*\)', ']'           # Markdown リンクの URL を落とす
            $ctx = $ctx -replace 'https?://\S+', '<url>'      # 生 URL
            $ctx = $ctx -replace '\S{60,}', '<長い文字列>'     # URLエンコード等の長いトークン
            if ($ctx.Length -gt 160) { $ctx = $ctx.Substring(0, 160) + '...' }
            if ($ctx -eq $prev -or ($prev -and ($prev.Contains($ctx) -or $ctx.Contains($prev)))) { continue }
            Write-Output ("    " + $ctx)
            $prev = $ctx
            $n++
        }
    }
}

$omitted = $totalCount - @($shown).Count
if ($omitted -gt 0) {
    Write-Output ""
    Write-Output ("... 残り " + $omitted + " ファイルは省略（-Limit 0 で全件、-FilesOnly で名前のみ）")
}
