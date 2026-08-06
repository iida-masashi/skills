# vault-shousai-triage.ps1
# Obsidian Vault内の「<親>_詳細/<子>.md」型分割構造を洗い出し、統合候補を判別する
# 子ノートが「実質空のリンク集」か「独立した論考」かを見分けるため、frontmatter/見出し/箇条書き/
# blockquoteを除いた「地の文（prose）」の行数で判定する。prose=0〜1はほぼ確実にリンク集で
# 機械的統合の安全候補、多いほど内容を読んでから判断する必要がある（サイズだけでは判定しない
# — 短い論考と長いリンク集は同じバイト数域に混在しうるため）。
# 使い方: pwsh -NoProfile -File vault-shousai-triage.ps1 -VaultRoot "<Vaultパス>" [-Folder "部分一致名"] [-OutCsv path] [-Summary [-Top 10]]

param(
    [Parameter(Mandatory)][string]$VaultRoot,
    [string]$Folder = '',
    [string]$OutCsv = '',
    [switch]$Summary,
    [int]$Top = 20
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = $VaultRoot
$searchPath = $root
if ($Folder) {
    $found = Get-ChildItem -LiteralPath $root -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*$Folder*" } | Select-Object -First 1 -ExpandProperty FullName
    if ($found) {
        $searchPath = $found
        Write-Output ('検索フォルダ: ' + $searchPath)
    } else {
        Write-Output ("⚠️  '$Folder' に一致するフォルダなし。全体検索にフォールバック")
    }
} else {
    Write-Output ('検索対象: ' + $root + ' 全体')
}

function Get-ProseLineCount([string]$text) {
    # frontmatter（先頭の --- ... --- ブロック）を除去
    $lines = $text -split "`r`n|`n"
    $fmCount = 0
    $bodyStart = 0
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq '---') {
            $fmCount++
            if ($fmCount -eq 2) { $bodyStart = $i + 1; break }
        }
    }
    $body = $lines[$bodyStart..($lines.Count - 1)]
    $prose = 0
    foreach ($line in $body) {
        $t = $line.Trim()
        if ($t -eq '') { continue }
        if ($t -match '^#') { continue }
        if ($t -match '^[-*|>]') { continue }
        if ($t -match '^\*※') { continue }
        $prose++
    }
    return $prose
}

$shousaiFolders = Get-ChildItem -LiteralPath $searchPath -Recurse -Directory -Filter '*_詳細' -ErrorAction SilentlyContinue

$rows = foreach ($d in $shousaiFolders) {
    $children = Get-ChildItem -LiteralPath $d.FullName -File -Filter '*.md' -ErrorAction SilentlyContinue
    $parentPath = $d.FullName -replace '_詳細$', '.md'
    $parentExists = Test-Path -LiteralPath $parentPath
    $parentSize = if ($parentExists) { (Get-Item -LiteralPath $parentPath).Length } else { 0 }

    if ($children.Count -eq 0) {
        [PSCustomObject]@{
            FolderPath   = $d.FullName.Substring($searchPath.Length).TrimStart('\')
            ChildCount   = 0
            MaxProse     = 0
            TotalChildSz = 0
            ParentSize   = $parentSize
            Shape        = 'EMPTY'
        }
        continue
    }

    $proseVals = @()
    $totalSz = 0
    foreach ($c in $children) {
        $text = Get-Content -LiteralPath $c.FullName -Raw -Encoding UTF8
        $proseVals += (Get-ProseLineCount $text)
        $totalSz += $c.Length
    }
    $maxProse = ($proseVals | Measure-Object -Maximum).Maximum

    $shape = if ($children.Count -eq 1 -and $maxProse -le 1) { 'LINK_STUB' }
             elseif ($children.Count -eq 1 -and $maxProse -le 4) { 'SHORT' }
             elseif ($totalSz -gt $parentSize) { 'CHILD_LARGER' }
             else { 'NEEDS_READ' }

    [PSCustomObject]@{
        FolderPath   = $d.FullName.Substring($searchPath.Length).TrimStart('\')
        ChildCount   = $children.Count
        MaxProse     = $maxProse
        TotalChildSz = $totalSz
        ParentSize   = $parentSize
        Shape        = $shape
    }
}

$sorted = $rows | Sort-Object ChildCount, MaxProse

Write-Output ('_詳細フォルダ総数: ' + $rows.Count)
Write-Output ''
Write-Output '=== 統合しやすさ別の内訳 ==='
$rows | Group-Object Shape | Sort-Object Count -Descending | ForEach-Object {
    Write-Output ("  {0,4}件 : {1}" -f $_.Count, $_.Name)
}
Write-Output ''
Write-Output '  EMPTY        = 子ノート0件（フォルダのみ残存、削除可）'
Write-Output '  LINK_STUB    = 子1件・地の文ほぼ0行（リンク集。機械的統合の最有力候補）'
Write-Output '  SHORT        = 子1件・地の文少数行（統合候補だが軽く目を通す）'
Write-Output '  CHILD_LARGER = 子の合計サイズが親を上回る（統合方向が逆転する可能性、要通読）'
Write-Output '  NEEDS_READ   = 上記以外（子が複数件、または内容量が中程度、通読して判断）'
Write-Output ''

if ($Summary) {
    Write-Output ("=== prose少ない順 上位 $Top 件 ===")
    foreach ($r in ($sorted | Select-Object -First $Top)) {
        Write-Output ("  [{0,-12}] 子{1}件 prose={2,3} : {3}" -f $r.Shape, $r.ChildCount, $r.MaxProse, $r.FolderPath)
    }
    if ($sorted.Count -gt $Top) {
        Write-Output ("  ... 残り " + ($sorted.Count - $Top) + " 件は省略（-OutCsv で全件出力可）")
    }
} else {
    Write-Output '=== 全件（prose少ない順） ==='
    foreach ($r in $sorted) {
        Write-Output ("  [{0,-12}] 子{1}件 prose={2,3} : {3}" -f $r.Shape, $r.ChildCount, $r.MaxProse, $r.FolderPath)
    }
}

if ($OutCsv) {
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add('FolderPath,ChildCount,MaxProse,TotalChildSizeBytes,ParentSizeBytes,Shape')
    foreach ($r in $sorted) {
        [void]$lines.Add('"' + $r.FolderPath + '",' + $r.ChildCount + ',' + $r.MaxProse + ',' + $r.TotalChildSz + ',' + $r.ParentSize + ',' + $r.Shape)
    }
    [System.IO.File]::WriteAllLines($OutCsv, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Output ''
    Write-Output ('[CSV] ' + $OutCsv)
}
