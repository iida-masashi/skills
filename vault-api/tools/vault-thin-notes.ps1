# vault-thin-notes.ps1
# Obsidian Vault内の薄ノート（指定バイト数未満の.md）を検出し、強化対象を洗い出す
# 使い方: pwsh -NoProfile -File vault-thin-notes.ps1 -VaultRoot "<Vaultパス>" [-Folder "部分一致名"] [-Threshold 3000] [-OutCsv path]

param(
    [Parameter(Mandatory)][string]$VaultRoot,
    [string]$Folder = '',
    [int]$Threshold = 3000,
    [string]$OutCsv = '',
    [switch]$Summary,
    [int]$Top = 10
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
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

$allMd = Get-ChildItem -LiteralPath $searchPath -Recurse -File -Filter *.md -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notmatch '\\\.obsidian\\' -and
        $_.FullName -notmatch '\\templates\\' -and
        $_.FullName -notmatch '\\資料\\' -and
        $_.FullName -notmatch '\\_work\\'
    }

$thin = $allMd | Where-Object { $_.Length -lt $Threshold } | Sort-Object Length

Write-Output ('対象総数: ' + $allMd.Count)
Write-Output ('閾値: ' + $Threshold + 'B')
Write-Output ''
Write-Output ('- 500B未満: ' + @($allMd | Where-Object { $_.Length -lt 500 }).Count + ' 件')
Write-Output ('- 1000B未満: ' + @($allMd | Where-Object { $_.Length -lt 1000 }).Count + ' 件')
Write-Output ('- 2000B未満: ' + @($allMd | Where-Object { $_.Length -lt 2000 }).Count + ' 件')
Write-Output ('- 3000B未満: ' + @($allMd | Where-Object { $_.Length -lt 3000 }).Count + ' 件')
Write-Output ''
if ($Summary) {
    # フォルダ別集計 + 上位N件のみ表示（生一覧を出さずトークンを節約）
    Write-Output '=== フォルダ別集計 ==='
    $byFolder = $thin | Group-Object { Split-Path ($_.FullName.Substring($searchPath.Length).TrimStart('\')) -Parent } |
        Sort-Object Count -Descending
    foreach ($g in $byFolder) {
        $label = if ($g.Name) { $g.Name } else { '(ルート)' }
        Write-Output ("  {0,4}件 : {1}" -f $g.Count, $label)
    }
    Write-Output ''
    Write-Output ("=== 最小サイズ上位 $Top 件 ===")
    foreach ($f in ($thin | Select-Object -First $Top)) {
        $rel = $f.FullName.Substring($searchPath.Length).TrimStart('\')
        Write-Output ("  {0,6}B : {1}" -f $f.Length, $rel)
    }
    if ($thin.Count -gt $Top) {
        Write-Output ("  ... 残り " + ($thin.Count - $Top) + " 件は省略（-OutCsv で全件出力可）")
    }
} else {
    Write-Output '=== 薄ノート一覧（サイズ昇順） ==='
    foreach ($f in $thin) {
        $rel = $f.FullName.Substring($searchPath.Length).TrimStart('\')
        Write-Output ("  {0,6}B : {1}" -f $f.Length, $rel)
    }
}

Write-Output ''
Write-Output ('合計: ' + $thin.Count + ' 件')

if ($OutCsv) {
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add('Path,SizeBytes')
    foreach ($f in $thin) {
        $rel = $f.FullName.Substring($searchPath.Length).TrimStart('\')
        [void]$lines.Add('"' + $rel + '",' + $f.Length)
    }
    [System.IO.File]::WriteAllLines($OutCsv, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Output ''
    Write-Output ('[CSV] ' + $OutCsv)
}
