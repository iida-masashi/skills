# vault-orphan-check.ps1
# D:\Vault の孤立ノート（wikilink されていない .md）を検出
# 出力: C:\Users\iidam\gemini\_work\_orphan_list.txt

$ErrorActionPreference = 'SilentlyContinue'
$root = 'D:\Vault'
$outputFile = 'C:\Users\iidam\gemini\_work\_orphan_list.txt'

# 出力ディレクトリ確認
$outputDir = Split-Path -Parent $outputFile
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

$results = @()

# 全ノートを収集（資料系・テンプレ・.obsidianは除外）
$allNotes = Get-ChildItem -LiteralPath $root -Recurse -File -Filter *.md |
    Where-Object {
        $_.FullName -notmatch '\\\.obsidian\\' -and
        $_.FullName -notmatch '\\templates\\' -and
        $_.FullName -notmatch '\\資料\\' -and
        $_.FullName -notmatch 'MEMORY\.md$'
    }

$results += "総ノート数（資料系除外）: " + $allNotes.Count

# 全ノートのbasename（拡張子なし）を辞書化
$basenames = @{}
foreach ($f in $allNotes) {
    $bn = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
    if (-not $basenames.ContainsKey($bn)) {
        $basenames[$bn] = $f.FullName
    }
}

# 全ファイルの本文を読み込み、wikilink (basename部分のみ) を抽出
$linkedBasenames = @{}
$allMdFiles = Get-ChildItem -LiteralPath $root -Recurse -File -Filter *.md |
    Where-Object { $_.FullName -notmatch '\\\.obsidian\\' }

foreach ($f in $allMdFiles) {
    $content = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8
    if ($content) {
        $matches = [regex]::Matches($content, '\[\[([^\]\|#]+)(\|[^\]]+)?\]\]')
        foreach ($m in $matches) {
            $linkTarget = $m.Groups[1].Value
            $bn = Split-Path -Leaf $linkTarget
            $bn = $bn -replace '\.md$', ''
            if (-not $linkedBasenames.ContainsKey($bn)) {
                $linkedBasenames[$bn] = $true
            }
        }
    }
}

$results += "全wikilink basename種類数: " + $linkedBasenames.Count

# 孤立ノートを抽出
$orphans = @()
foreach ($bn in $basenames.Keys) {
    if (-not $linkedBasenames.ContainsKey($bn)) {
        $orphans += $basenames[$bn]
    }
}

$results += "孤立ノート数: " + $orphans.Count
$results += ""
$results += "=== 孤立ノート一覧（サイズ降順） ==="

$orphanItems = $orphans | ForEach-Object { Get-Item -LiteralPath $_ } | Sort-Object Length -Descending

foreach ($item in $orphanItems) {
    $rel = $item.FullName.Substring($root.Length + 1)
    $results += ("  {0,6}B : {1}" -f $item.Length, $rel)
}

$results | Out-File -Encoding utf8 -FilePath $outputFile
Write-Output ("✅ vault-orphan-check 完了。結果: " + $outputFile)
Write-Output ("孤立ノート数: " + $orphans.Count)
