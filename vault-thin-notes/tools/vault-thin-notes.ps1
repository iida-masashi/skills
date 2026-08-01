# vault-thin-notes.ps1
# 指定したObsidian Vaultの薄ノートを検出
# 使い方: pwsh -NoProfile -File vault-thin-notes.ps1 -VaultRoot "<Vaultパス>" [-folder <部分一致名>] [-threshold <バイト数>]

param(
    [Parameter(Mandatory)][string]$VaultRoot,
    [string]$folder = '',
    [int]$threshold = 3000
)

$ErrorActionPreference = 'SilentlyContinue'
$root = $VaultRoot

# 検索パス決定
if ($folder) {
    $candidate = Get-ChildItem -LiteralPath $root -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*$folder*" } |
        Sort-Object FullName |
        Select-Object -First 1
    if ($candidate) {
        $searchPath = $candidate.FullName
        Write-Output ("検索フォルダ: " + $searchPath)
    } else {
        $searchPath = $root
        Write-Output ("⚠️  '$folder' に一致するフォルダなし。全体検索にフォールバック")
    }
} else {
    $searchPath = $root
    Write-Output ("検索対象: " + $root + " 全体")
}

Write-Output ("閾値: " + $threshold + "B")
Write-Output ""
Write-Output "=== 薄ノート一覧（サイズ昇順） ==="

$thin = Get-ChildItem -LiteralPath $searchPath -Recurse -File -Filter *.md -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Length -lt $threshold -and
        $_.FullName -notmatch '\\\.obsidian\\' -and
        $_.FullName -notmatch '\\templates\\' -and
        $_.FullName -notmatch '\\資料\\' -and
        $_.FullName -notmatch '\\_work\\'
    } |
    Sort-Object Length

foreach ($f in $thin) {
    $rel = $f.FullName.Substring($root.Length + 1)
    Write-Output ("  {0,6}B : {1}" -f $f.Length, $rel)
}

Write-Output ""
Write-Output ("合計: " + $thin.Count + " 件")
