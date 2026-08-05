# vault-orphans.ps1
# Obsidian Vault内の孤立ノート（どこからも [[wikilink]] されていないノート）を検出
# 使い方: pwsh -NoProfile -File vault-orphans.ps1 -VaultRoot "<Vaultパス>" [-SubPath "フォルダ"] [-ExcludeKeywords a,b] [-OutCsv path]

param(
    [Parameter(Mandatory)][string]$VaultRoot,
    [string]$SubPath = '',
    [string[]]$ExcludeKeywords = @(),
    [string]$OutCsv = '',
    [switch]$Summary,
    [int]$Top = 10
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = $VaultRoot

$allMd = Get-ChildItem -LiteralPath $root -Recurse -File -Filter *.md -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notmatch '\\\.obsidian\\' -and
        $_.FullName -notmatch '\\templates\\' -and
        $_.FullName -notmatch '\\資料\\' -and
        $_.FullName -notmatch 'MEMORY\.md$'
    }

$targetMd = if ($SubPath) {
    $targetPrefix = (Join-Path $root $SubPath)
    $allMd | Where-Object { $_.FullName.StartsWith($targetPrefix) }
} else {
    $allMd
}

$targetBn = New-Object System.Collections.Generic.HashSet[string]
foreach ($f in $targetMd) {
    [void]$targetBn.Add([System.IO.Path]::GetFileNameWithoutExtension($f.Name))
}

# 全ファイル（.obsidian除く）の本文からwikilinkを抽出し、basenameを収集
$referenced = New-Object System.Collections.Generic.HashSet[string]
$allMdForLinks = Get-ChildItem -LiteralPath $root -Recurse -File -Filter *.md -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\\.obsidian\\' }

foreach ($f in $allMdForLinks) {
    $content = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    $matches = [regex]::Matches($content, '\[\[([^\]\|#]+)(\|[^\]]+)?\]\]')
    foreach ($m in $matches) {
        $linkTarget = $m.Groups[1].Value
        $bn = Split-Path -Leaf $linkTarget
        $bn = $bn -replace '\.md$', ''
        [void]$referenced.Add($bn)
    }
}

$orphans = @()
foreach ($f in $targetMd) {
    $bn = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
    if ($referenced.Contains($bn)) { continue }
    $excluded = $false
    foreach ($kw in $ExcludeKeywords) {
        if ($bn -like "*$kw*") { $excluded = $true; break }
    }
    if (-not $excluded) { $orphans += $f }
}

$subPathLabel = if ($SubPath) { $SubPath } else { '(全体)' }
Write-Output ('Scanning... SubPath=' + $subPathLabel)
Write-Output ('総ノート数（資料系除外）: ' + $allMd.Count)
Write-Output ('孤立ノート数: ' + $orphans.Count)
Write-Output ''

$orphanItems = $orphans | Sort-Object Length -Descending

if ($Summary) {
    # フォルダ別集計 + 上位N件のみ表示（生一覧を出さずトークンを節約）
    Write-Output '=== フォルダ別集計 ==='
    $byFolder = $orphanItems | Group-Object { Split-Path ($_.FullName.Substring($root.Length).TrimStart('\')) -Parent } |
        Sort-Object Count -Descending
    foreach ($g in $byFolder) {
        $label = if ($g.Name) { $g.Name } else { '(ルート)' }
        Write-Output ("  {0,4}件 : {1}" -f $g.Count, $label)
    }
    Write-Output ''
    Write-Output ("=== 上位 $Top 件（サイズ降順） ===")
    foreach ($item in ($orphanItems | Select-Object -First $Top)) {
        $rel = $item.FullName.Substring($root.Length).TrimStart('\')
        Write-Output ("  {0,6}B : {1}" -f $item.Length, $rel)
    }
    if ($orphanItems.Count -gt $Top) {
        Write-Output ("  ... 残り " + ($orphanItems.Count - $Top) + " 件は省略（-OutCsv で全件出力可）")
    }
} else {
    Write-Output '=== 孤立ノート一覧（サイズ降順） ==='
    foreach ($item in $orphanItems) {
        $rel = $item.FullName.Substring($root.Length).TrimStart('\')
        Write-Output ("  {0,6}B : {1}" -f $item.Length, $rel)
    }
}

if ($OutCsv) {
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add('Path,Basename,Folder')
    foreach ($item in $orphanItems) {
        $rel = $item.FullName.Substring($root.Length).TrimStart('\')
        $bn = [System.IO.Path]::GetFileNameWithoutExtension($item.Name)
        $folder = Split-Path $rel -Parent
        [void]$lines.Add('"' + $rel + '","' + $bn + '","' + $folder + '"')
    }
    [System.IO.File]::WriteAllLines($OutCsv, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Output ''
    Write-Output ('[CSV] ' + $OutCsv)
}
