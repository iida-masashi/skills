# vault-batch-summary.ps1
# 複数ノートのfrontmatter + 先頭数行だけをまとめて取得（分類・下調べフェーズのトークン節約用）
# 使い方: pwsh -NoProfile -File vault-batch-summary.ps1 -Paths "a.md","b.md" [-Lines 5] [-Vault awa|religion]
#        pwsh -NoProfile -File vault-batch-summary.ps1 -PathsFile paths.txt [-Lines 5] [-Vault awa|religion]

param(
    [string[]]$Paths = @(),
    [string]$PathsFile = '',
    [int]$Lines = 5,
    [string]$Vault
)

# UTF-8 出力（Bash経由のpwsh呼び出しで日本語が文字化けするのを防ぐ）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Import-Module (Join-Path $PSScriptRoot 'obsidian-api.psm1') -Force -WarningAction SilentlyContinue

if ($PathsFile) {
    $filePaths = Get-Content -LiteralPath $PathsFile -Encoding UTF8 | Where-Object { $_.Trim() -ne '' }
    $Paths = @($Paths) + @($filePaths)
}

if ($Paths.Count -eq 0) {
    throw "対象ファイルがありません。-Paths または -PathsFile を指定してください。"
}

Write-Output ("対象: " + $Paths.Count + " 件")
Write-Output ""

foreach ($p in $Paths) {
    Write-Output ("── " + $p)
    try {
        $content = Get-ObsidianNote -FilePath $p -Vault $Vault
    } catch {
        Write-Output ("    [ERROR] " + $_.Exception.Message)
        Write-Output ""
        continue
    }

    $allLines = $content -split "`n"

    # frontmatter抽出（先頭が --- で始まる場合のみ）
    $fm = @()
    $bodyStartIdx = 0
    if ($allLines.Count -gt 0 -and $allLines[0].Trim() -eq '---') {
        for ($i = 1; $i -lt $allLines.Count; $i++) {
            if ($allLines[$i].Trim() -eq '---') {
                $bodyStartIdx = $i + 1
                break
            }
            $fm += $allLines[$i]
        }
    }

    if ($fm.Count -gt 0) {
        Write-Output "    [frontmatter]"
        foreach ($line in $fm) {
            Write-Output ("      " + $line)
        }
    }

    # 本文先頭N行（空行スキップなし、そのまま）
    $bodyLines = $allLines[$bodyStartIdx..($allLines.Count - 1)] | Where-Object { $_.Trim() -ne '' }
    $shown = $bodyLines | Select-Object -First $Lines
    if ($shown.Count -gt 0) {
        Write-Output "    [本文冒頭]"
        foreach ($line in $shown) {
            $t = $line.Trim()
            if ($t.Length -gt 150) { $t = $t.Substring(0, 150) + '...' }
            Write-Output ("      " + $t)
        }
    }

    Write-Output ("    (全" + $allLines.Count + "行 / " + $content.Length + "文字)")
    Write-Output ""
}
