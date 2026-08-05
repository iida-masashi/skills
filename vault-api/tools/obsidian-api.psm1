# obsidian-api.psm1
# Obsidian Local REST API 共通モジュール
# 使い方: Import-Module '<vault-api>/tools/obsidian-api.psm1'
#
# 複数Vault対応:
#   $env:OBSIDIAN_VAULT に 'awa' | 'religion' 等を設定するか、
#   Set-ObsidianVault -Vault 'awa' で切り替える。
#   未設定時は既定Vault（$script:defaultVault）を使う。
#   設定ファイルは _secrets/obsidian.<vault>.json （例: obsidian.awa.json）を読む。
#   後方互換: _secrets/obsidian.json のみ存在する環境では、それを既定として読む。

$script:secretsDir = Join-Path $PSScriptRoot '..\_secrets'
$script:defaultVault = 'religion'

function Set-ObsidianVault {
    <#
    .SYNOPSIS
    以降このセッション（このプロセス）で使うVaultを切り替える
    .PARAMETER Vault
    'awa' | 'religion' など、_secrets/obsidian.<vault>.json のvault名部分
    #>
    param([Parameter(Mandatory)][string]$Vault)
    $env:OBSIDIAN_VAULT = $Vault
}

function Get-ObsidianConfigPath {
    param([string]$Vault)
    if (-not $Vault) { $Vault = $env:OBSIDIAN_VAULT }
    if (-not $Vault) { $Vault = $script:defaultVault }

    $namedPath = Join-Path $script:secretsDir "obsidian.$Vault.json"
    if (Test-Path $namedPath) { return $namedPath }

    # 後方互換: obsidian.json のみの環境
    $legacyPath = Join-Path $script:secretsDir 'obsidian.json'
    if (Test-Path $legacyPath) { return $legacyPath }

    throw "Obsidian config not found for vault '$Vault'. Expected: $namedPath"
}

function Get-ObsidianConfig {
    param([string]$Vault)
    $path = Get-ObsidianConfigPath -Vault $Vault
    return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-ObsidianBaseUri {
    param([string]$Vault)
    $cfg = Get-ObsidianConfig -Vault $Vault
    return ("{0}://{1}:{2}" -f $cfg.scheme, $cfg.host, $cfg.port)
}

function Get-ObsidianHeaders {
    param([string]$Vault)
    $cfg = Get-ObsidianConfig -Vault $Vault
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
        [hashtable]$ExtraHeaders = @{},
        [string]$Vault
    )
    $base = Get-ObsidianBaseUri -Vault $Vault
    $headers = Get-ObsidianHeaders -Vault $Vault
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
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param([string]$Vault)
    return Invoke-ObsidianApi -Method GET -Path '/vault/' -Vault $Vault
}

function Get-ObsidianDirList {
    <#
    .SYNOPSIS
    指定ディレクトリのファイル一覧
    .PARAMETER DirPath
    Vault相対パス (例: '式内社/01_阿波国/')
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$DirPath,
        [string]$Vault
    )
    # スラッシュで終わらせる
    if ($DirPath -notmatch '/$') { $DirPath += '/' }
    $encoded = [System.Uri]::EscapeDataString($DirPath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method GET -Path "/vault/$encoded" -Vault $Vault
}

function Get-ObsidianNote {
    <#
    .SYNOPSIS
    ファイル内容を取得
    .PARAMETER FilePath
    Vault相対パス (例: '式内社/01_阿波国/忌部神社.md')
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string]$Vault
    )
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method GET -Path "/vault/$encoded" -Vault $Vault
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
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$Query,
        [int]$ContextLength = 100,
        [int]$Limit = 0,
        [string]$Vault
    )
    $encodedQuery = [System.Uri]::EscapeDataString($Query)
    $path = "/search/simple/?query=$encodedQuery&contextLength=$ContextLength"
    $results = Invoke-ObsidianApi -Method POST -Path $path -Vault $Vault
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
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    .EXAMPLE
    # frontmatterのtagsに"神社"を含むノートを検索
    Search-ObsidianVaultAdvanced -Query @{ 'in' = @('神社', @{'var'='tags'}) }
    #>
    param(
        [Parameter(Mandatory)]$Query,
        [string]$Vault
    )
    return Invoke-ObsidianApi -Method POST -Path '/search/' -Body $Query -ContentType 'application/vnd.olrapi.jsonlogic+json' -Vault $Vault
}

function Append-ObsidianNote {
    <#
    .SYNOPSIS
    ファイル末尾に内容を追記
    .PARAMETER FilePath
    Vault相対パス
    .PARAMETER Content
    追記内容
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string]$Content,
        [string]$Vault
    )
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method POST -Path "/vault/$encoded" -Body $Content -ContentType 'text/markdown' -Vault $Vault
}

function Write-ObsidianNote {
    <#
    .SYNOPSIS
    ファイル作成/上書き
    .PARAMETER FilePath
    Vault相対パス
    .PARAMETER Content
    内容（完全上書き）
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string]$Content,
        [string]$Vault
    )
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method PUT -Path "/vault/$encoded" -Body $Content -ContentType 'text/markdown' -Vault $Vault
}

function Remove-ObsidianNote {
    <#
    .SYNOPSIS
    ファイル削除
    .PARAMETER FilePath
    Vault相対パス
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string]$Vault
    )
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')
    return Invoke-ObsidianApi -Method DELETE -Path "/vault/$encoded" -Vault $Vault
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
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$FromPath,
        [Parameter(Mandatory)][string]$ToPath,
        [string]$Vault
    )
    $content = Get-ObsidianNote -FilePath $FromPath -Vault $Vault
    Write-ObsidianNote -FilePath $ToPath -Content $content -Vault $Vault | Out-Null
    Remove-ObsidianNote -FilePath $FromPath -Vault $Vault | Out-Null
    return [PSCustomObject]@{ From = $FromPath; To = $ToPath; Bytes = $content.Length }
}

function Edit-ObsidianNoteSection {
    <#
    .SYNOPSIS
    見出し配下やブロック参照への相対挿入（PATCH、markdown-patch 2.x形式）
    .DESCRIPTION
    Local REST API with MCP プラグイン 5.0以降のデフォルトである markdown-patch 2.x 形式でPATCHを行う。
    指示全体をJSON body(PatchInstruction)として送る。1.x形式（Operationヘッダー等でのヘッダー分散指定）は
    plugin 6.0 で廃止されるため使用しない。
    .PARAMETER FilePath
    Vault相対パス
    .PARAMETER TargetType
    'heading' | 'block' | 'frontmatter'
    .PARAMETER Target
    heading: ドキュメントルートから対象見出しまでの見出しテキストの配列（'#'は含めない）。
    例えば本文が「# タイトル」→「## 参考文献」という階層なら @('タイトル','参考文献') を指定する
    （単に @('参考文献') だとルート直下の見出しとして探され、見つからず 40400 になる）。
    文字列を渡した場合は単一要素の配列（ルート直下の見出し）として扱う。
    block: ブロックID（'^'なし）。frontmatter: キー名。
    .PARAMETER Operation
    'append' | 'prepend' | 'replace' | 'delete'
    .PARAMETER Content
    挿入する内容（heading/blockの文字列ペイロード）。TargetType='frontmatter'では使わない（Valueを使う）。
    .PARAMETER Value
    frontmatterターゲット用の型付きJSON値（文字列・数値・配列・オブジェクトなど）。
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][ValidateSet('heading', 'block', 'frontmatter')][string]$TargetType,
        [Parameter(Mandatory)]$Target,
        [Parameter(Mandatory)][ValidateSet('append', 'prepend', 'replace', 'delete')][string]$Operation,
        [string]$Content,
        $Value,
        [string]$Vault
    )
    $encoded = [System.Uri]::EscapeDataString($FilePath).Replace('%2F', '/')

    if ($TargetType -eq 'heading' -and $Target -is [string]) {
        $Target = @($Target)
    }

    $instruction = [ordered]@{
        targetType = $TargetType
        target = $Target
        operation = $Operation
    }
    if ($TargetType -eq 'frontmatter') {
        if (-not $PSBoundParameters.ContainsKey('Value')) {
            throw "TargetType='frontmatter' では -Value を指定してください（-Content ではなく、frontmatterの値はvalueフィールドで送る必要があります）"
        }
        $instruction['value'] = $Value
    } else {
        if ($PSBoundParameters.ContainsKey('Content')) {
            $instruction['content'] = $Content
        }
    }

    return Invoke-ObsidianApi -Method PATCH -Path "/vault/$encoded" -Body $instruction -ContentType 'application/json' -Vault $Vault
}

function Get-ObsidianActiveNote {
    <#
    .SYNOPSIS
    Obsidianで現在開いているノートの内容を取得
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param([string]$Vault)
    return Invoke-ObsidianApi -Method GET -Path '/active/' -Vault $Vault
}

function Get-ObsidianCommandList {
    <#
    .SYNOPSIS
    実行可能なObsidianコマンド一覧を取得
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param([string]$Vault)
    return Invoke-ObsidianApi -Method GET -Path '/commands/' -Vault $Vault
}

function Invoke-ObsidianCommand {
    <#
    .SYNOPSIS
    指定したObsidianコマンドを実行（例: 'app:reload' で検索インデックス再構築）
    .PARAMETER CommandId
    Get-ObsidianCommandList で確認できるコマンドID
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param(
        [Parameter(Mandatory)][string]$CommandId,
        [string]$Vault
    )
    return Invoke-ObsidianApi -Method POST -Path "/commands/$CommandId/" -Vault $Vault
}

function Test-ObsidianApi {
    <#
    .SYNOPSIS
    API疎通テスト（認証含む）
    .PARAMETER Vault
    'awa' | 'religion' 等。省略時は $env:OBSIDIAN_VAULT または既定Vault
    #>
    param([string]$Vault)
    return Invoke-ObsidianApi -Method GET -Path '/' -Vault $Vault
}

Export-ModuleMember -Function Get-ObsidianConfig, Get-ObsidianConfigPath, Set-ObsidianVault, Get-ObsidianBaseUri, Get-ObsidianHeaders, Invoke-ObsidianApi, Get-ObsidianVaultList, Get-ObsidianDirList, Get-ObsidianNote, Search-ObsidianVault, Search-ObsidianVaultAdvanced, Append-ObsidianNote, Write-ObsidianNote, Remove-ObsidianNote, Move-ObsidianNote, Edit-ObsidianNoteSection, Get-ObsidianActiveNote, Get-ObsidianCommandList, Invoke-ObsidianCommand, Test-ObsidianApi
