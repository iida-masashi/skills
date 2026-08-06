# vault-basename-collisions.ps1
# Obsidian Vault内で同一basename（拡張子除くファイル名）を持つ.mdファイルを検出する。
# wikilink（[[名前]]）はbasenameで解決されるため、同名ファイルが複数存在すると
# リンクがどちらか一方にのみ解決される「曖昧参照」が発生する（Obsidianの解決規則は
# 通常「最初に見つかったファイル」だが、Vault内の実際の解決結果は保証されない）。
# 典型例：「詳細論考ポータル」のような汎用的なファイル名を複数フォルダで使い回すケース。
# 使い方: pwsh -NoProfile -File vault-basename-collisions.ps1 -VaultRoot "<Vaultパス>" [-OutCsv path]

param(
    [Parameter(Mandatory)][string]$VaultRoot,
    [string]$OutCsv = ''
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$excludeDirs = @('.obsidian', 'templates', '_work')

$allFiles = Get-ChildItem -LiteralPath $VaultRoot -Recurse -File -Filter '*.md' -ErrorAction SilentlyContinue |
    Where-Object {
        $rel = $_.FullName.Substring($VaultRoot.Length).TrimStart('\')
        $topDir = ($rel -split '\\')[0]
        $excludeDirs -notcontains $topDir
    }

Write-Output ('走査対象ファイル数: ' + $allFiles.Count)

$groups = $allFiles | Group-Object { $_.BaseName } | Where-Object { $_.Count -gt 1 }

Write-Output ('basename衝突グループ数: ' + $groups.Count)
Write-Output ''

$rows = New-Object System.Collections.Generic.List[object]
foreach ($g in ($groups | Sort-Object Count -Descending)) {
    $paths = $g.Group | ForEach-Object { $_.FullName.Substring($VaultRoot.Length).TrimStart('\') }
    Write-Output ("[{0}件] {1}" -f $g.Count, $g.Name)
    foreach ($p in $paths) {
        Write-Output ("    - $p")
        $rows.Add([PSCustomObject]@{
            BaseName = $g.Name
            Count    = $g.Count
            Path     = $p
        })
    }
}

if ($OutCsv) {
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add('BaseName,Count,Path')
    foreach ($r in $rows) {
        [void]$lines.Add('"' + $r.BaseName + '",' + $r.Count + ',"' + $r.Path + '"')
    }
    [System.IO.File]::WriteAllLines($OutCsv, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Output ''
    Write-Output ('[CSV] ' + $OutCsv)
}
