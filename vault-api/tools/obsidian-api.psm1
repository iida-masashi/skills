# obsidian-api.psm1
# Obsidian Local REST API 共通モジュール
# 使い方: Import-Module '<vault-api>/tools/obsidian-api.psm1'

$script:configPath = Join-Path $PSScriptRoot '..\_secrets\obsidian.json'

function Get-ObsidianConfig {
    if (-not (Test-Path $script:configPath)) {
        throw "Obsidian config not found: $script:configPath"
    }
    return Get-Content -LiteralPath $script:configPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-ObsidianBaseUri {
    $cfg = Get-ObsidianConfig
    return ("{0}://{1}:{2}" -f $cfg.scheme, $cfg.host, $cfg.port)
}

function Get-ObsidianHeaders {
    $cfg = Get-ObsidianConfig
    return @{
        'Authorization' = "Bearer $($cfg.apiKey)"
        'Accept' = 'application/json'
    }
}

function Invoke-ObsidianApi {
    param(
        [string]$Method = 'GET',
        [string]$Path,
        $Body = $null,
        [string]$ContentType = 'application/json',
        [hashtable]$ExtraHeaders = @{}
    )
    $base = Get-ObsidianBaseUri
    $headers = Get-ObsidianHeaders
    foreach ($k in $ExtraHeaders.Keys) {
        $headers[$k] = $ExtraHeaders[$k]
    }
    $uri = "$base$Path"
    $params = @{
        Uri = $uri
        Method = $Method
        Headers = $headers
        SkipCertificateCheck = $true
        UseBasicParsing = $true
    }
    if ($Body) {
        if ($Body -is [string]) {
            $params['Body'] = $Body
        } else {
            $params['Body'] = ($Body | ConvertTo-Json -Depth 10)
        }
        $params['ContentType'] = $ContentType
    }
    try {
        return Invoke-RestMethod @params
    } catch {
        $detail = $_.ErrorDetails.Message
        if ($detail -match "ENOENT.*open '([^']+)'") {
            throw "Obsidian API error: 検索インデックスが旧パスを参照しています ('$($Matches[1])')。Invoke-ObsidianCommand -CommandId 'app:reload' でインデックスを再構築してください。 (元エラー: $detail)"
        }
        if ($detail) {
            throw "Obsidian API error [$Method $Path]: $detail"
        }
        throw
    }
}

# 公開関数

function Get-ObsidianVaultList {
    <#
    .SYNOPSIS
    Vaultルートディレクトリのファイル/フォルダ一覧を取得
    #>
    return Invoke-ObsidianApi -Method GET -Path '/vault/'
}

function Get-ObsidianDirList {
    <#
    .SYNOPSIS
    指定ディレクトリのファイル一覧
    .PARAMETER DirPath
    Vault相対パス (例: '式内社/01_阿波国/')
    #>
    param([Parameter(Mandatory)][string]$DirPath)
    # スラッシュで終わらせる
    if ($DirPath -notmatch '/$') { $DirPath += '/' }
    $encoded = [System.Uri]::EscapeDataString($DirPath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method GET -Path "/vault/$encoded"
}

function Get-ObsidianNote {
    <#
    .SYNOPSIS
    ファイル内容を取得
    .PARAMETER FilePath
    Vault相対パス (例: '式内社/01_阿波国/忌部神社.md')
    #>
    param([Parameter(Mandatory)][string]$FilePath)
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method GET -Path "/vault/$encoded"
}

function Search-ObsidianVault {
    <#
    .SYNOPSIS
    Vault全文検索（simple text）
    .PARAMETER Query
    検索文字列
    .PARAMETER ContextLength
    結果のコンテキスト文字数（デフォルト100）
    .PARAMETER Limit
    返却する結果件数の上限（デフォルト0=無制限）。API自体には上限機能がないため取得後に切り詰める。
    #>
    param(
        [Parameter(Mandatory)][string]$Query,
        [int]$ContextLength = 100,
        [int]$Limit = 0
    )
    $encodedQuery = [System.Uri]::EscapeDataString($Query)
    $path = "/search/simple/?query=$encodedQuery&contextLength=$ContextLength"
    $results = Invoke-ObsidianApi -Method POST -Path $path
    if ($Limit -gt 0 -and $results.Count -gt $Limit) {
        return $results | Select-Object -First $Limit
    }
    return $results
}

function Search-ObsidianVaultAdvanced {
    <#
    .SYNOPSIS
    JsonLogicクエリによる構造化検索（タグ・frontmatter・パス条件などで絞り込み）
    .PARAMETER Query
    JsonLogic形式のハッシュテーブルまたはJSON文字列
    .EXAMPLE
    # frontmatterのtagsに"神社"を含むノートを検索
    Search-ObsidianVaultAdvanced -Query @{ 'in' = @('神社', @{'var'='tags'}) }
    #>
    param(
        [Parameter(Mandatory)]$Query
    )
    return Invoke-ObsidianApi -Method POST -Path '/search/' -Body $Query -ContentType 'application/vnd.olrapi.jsonlogic+json'
}

function Append-ObsidianNote {
    <#
    .SYNOPSIS
    ファイル末尾に内容を追記
    .PARAMETER FilePath
    Vault相対パス
    .PARAMETER Content
    追記内容
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string]$Content
    )
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method POST -Path "/vault/$encoded" -Body $Content -ContentType 'text/markdown'
}

function Write-ObsidianNote {
    <#
    .SYNOPSIS
    ファイル作成/上書き
    .PARAMETER FilePath
    Vault相対パス
    .PARAMETER Content
    内容（完全上書き）
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string]$Content
    )
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method PUT -Path "/vault/$encoded" -Body $Content -ContentType 'text/markdown'
}

function Remove-ObsidianNote {
    <#
    .SYNOPSIS
    ファイル削除
    .PARAMETER FilePath
    Vault相対パス
    #>
    param([Parameter(Mandatory)][string]$FilePath)
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method DELETE -Path "/vault/$encoded"
}

function Move-ObsidianNote {
    <#
    .SYNOPSIS
    ファイルのリネーム/移動（PUTで新規作成→DELETEで旧パス削除の合成操作）
    .DESCRIPTION
    Local REST APIに専用のrename/moveエンドポイントは存在しないため、
    読み取り→新パスへ書き込み→旧パス削除の順で行う。
    wikilinkはbasename参照のためリンク切れは起きないが、
    basename自体を変える場合は他ノートの参照が手動更新必要。
    .PARAMETER FromPath
    移動元のVault相対パス
    .PARAMETER ToPath
    移動先のVault相対パス
    #>
    param(
        [Parameter(Mandatory)][string]$FromPath,
        [Parameter(Mandatory)][string]$ToPath
    )
    $content = Get-ObsidianNote -FilePath $FromPath
    Write-ObsidianNote -FilePath $ToPath -Content $content | Out-Null
    Remove-ObsidianNote -FilePath $FromPath | Out-Null
    return [PSCustomObject]@{ From = $FromPath; To = $ToPath; Bytes = $content.Length }
}

function Edit-ObsidianNoteSection {
    <#
    .SYNOPSIS
    見出し配下やブロック参照への相対挿入（PATCH）
    .PARAMETER FilePath
    Vault相対パス
    .PARAMETER TargetType
    'heading' | 'block' | 'frontmatter'
    .PARAMETER Target
    見出しテキスト（heading）、ブロックID（block）、frontmatterキー（frontmatter）
    .PARAMETER Operation
    'append' | 'prepend' | 'replace'
    .PARAMETER Content
    挿入する内容
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][ValidateSet('heading', 'block', 'frontmatter')][string]$TargetType,
        [Parameter(Mandatory)][string]$Target,
        [Parameter(Mandatory)][ValidateSet('append', 'prepend', 'replace')][string]$Operation,
        [Parameter(Mandatory)][string]$Content
    )
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    $headers = @{
        'Operation' = $Operation
        'Target-Type' = $TargetType
        'Target' = [System.Uri]::EscapeDataString($Target)
    }
    return Invoke-ObsidianApi -Method PATCH -Path "/vault/$encoded" -Body $Content -ContentType 'text/markdown' -ExtraHeaders $headers
}

function Get-ObsidianActiveNote {
    <#
    .SYNOPSIS
    Obsidianで現在開いているノートの内容を取得
    #>
    return Invoke-ObsidianApi -Method GET -Path '/active/'
}

function Get-ObsidianCommandList {
    <#
    .SYNOPSIS
    実行可能なObsidianコマンド一覧を取得
    #>
    return Invoke-ObsidianApi -Method GET -Path '/commands/'
}

function Invoke-ObsidianCommand {
    <#
    .SYNOPSIS
    指定したObsidianコマンドを実行（例: 'app:reload' で検索インデックス再構築）
    .PARAMETER CommandId
    Get-ObsidianCommandList で確認できるコマンドID
    #>
    param([Parameter(Mandatory)][string]$CommandId)
    return Invoke-ObsidianApi -Method POST -Path "/commands/$CommandId/"
}

function Test-ObsidianApi {
    <#
    .SYNOPSIS
    API疎通テスト（認証含む）
    #>
    return Invoke-ObsidianApi -Method GET -Path '/'
}

Export-ModuleMember -Function Get-ObsidianConfig, Get-ObsidianBaseUri, Get-ObsidianHeaders, Invoke-ObsidianApi, Get-ObsidianVaultList, Get-ObsidianDirList, Get-ObsidianNote, Search-ObsidianVault, Search-ObsidianVaultAdvanced, Append-ObsidianNote, Write-ObsidianNote, Remove-ObsidianNote, Move-ObsidianNote, Edit-ObsidianNoteSection, Get-ObsidianActiveNote, Get-ObsidianCommandList, Invoke-ObsidianCommand, Test-ObsidianApi
