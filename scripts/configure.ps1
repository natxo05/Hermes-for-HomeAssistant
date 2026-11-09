<#
.SYNOPSIS
    Omple els placeholders __OWNER__ i __REPO__ del repositori d'add-ons.

.DESCRIPTION
    Substitueix els placeholders de repository.yaml, README.md i assistent_ha/config.yaml
    pel teu usuari i nom de repositori de GitHub.

    Amb -UsePrebuiltImages també descomenta la línia 'image:' de config.yaml perquè
    Home Assistant descarregui la imatge de GHCR en lloc de compilar-la al dispositiu.
    Fes-ho només després que el workflow hagi publicat la imatge i l'hagis fet pública.

.EXAMPLE
    .\scripts\configure.ps1 -Owner elmeuusuari

.EXAMPLE
    .\scripts\configure.ps1 -Owner elmeuusuari -UsePrebuiltImages
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9-]*$')]
    [string]$Owner,

    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$Repo = 'Hermes-for-HomeAssistant',

    [switch]$UsePrebuiltImages
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$ownerLower = $Owner.ToLowerInvariant()
$repoLower = $Repo.ToLowerInvariant()

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

$files = @(
    (Join-Path $root 'repository.yaml'),
    (Join-Path $root 'README.md'),
    (Join-Path $root 'assistent_ha\config.yaml')
)

foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file)) {
        Write-Warning "No trobo $file; el salto."
        continue
    }
    $content = Get-Content -LiteralPath $file -Raw -Encoding UTF8
    $updated = $content.Replace('__OWNER__', $ownerLower).Replace('__REPO__', $repoLower)
    if ($updated -ne $content) {
        Write-Utf8NoBom -Path $file -Content $updated
        Write-Host "Actualitzat $file"
    }
}

if ($UsePrebuiltImages) {
    $config = Join-Path $root 'assistent_ha\config.yaml'
    $content = Get-Content -LiteralPath $config -Raw -Encoding UTF8
    $updated = $content.Replace('# image: "ghcr.io/', 'image: "ghcr.io/')
    if ($updated -ne $content) {
        Write-Utf8NoBom -Path $config -Content $updated
        Write-Host "Imatge precompilada activada a assistent_ha/config.yaml"
    }
    else {
        Write-Host "La línia 'image:' ja estava activada."
    }
}

$url = "https://github.com/$ownerLower/$repoLower"
$badge = "https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=" +
    [System.Uri]::EscapeDataString($url)

Write-Host ""
Write-Host "Repositori: $url" -ForegroundColor Green
Write-Host "Afegeix-lo a Home Assistant: $badge"
if (-not $UsePrebuiltImages) {
    Write-Host ""
    Write-Host "Recorda: la imatge precompilada encara no està activada (caldrà executar" -ForegroundColor Yellow
    Write-Host "aquest script amb -UsePrebuiltImages després del primer build a GitHub)." -ForegroundColor Yellow
}
