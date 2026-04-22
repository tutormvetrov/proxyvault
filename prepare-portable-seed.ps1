param(
    [string]$SourceDir
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $SourceDir) {
    $SourceDir = (& python -c "from app.paths import HOME_APP_DIR; print(HOME_APP_DIR)").Trim()
}

$root = (Get-Location).Path
$seedDir = Join-Path $root "portable-seed"
$dbSource = Join-Path $SourceDir "proxyvault.db"
$qrSource = Join-Path $SourceDir "qrcodes"
$dbTarget = Join-Path $seedDir "proxyvault.db"
$qrTarget = Join-Path $seedDir "qrcodes"

if (-not (Test-Path $dbSource) -and -not (Test-Path $qrSource)) {
    throw "No ProxyVault data found in '$SourceDir'."
}

New-Item -ItemType Directory -Path $seedDir -Force | Out-Null

if (Test-Path $dbTarget) {
    Remove-Item -LiteralPath $dbTarget -Force
}
if (Test-Path $qrTarget) {
    Remove-Item -LiteralPath $qrTarget -Recurse -Force
}

if (Test-Path $dbSource) {
    Copy-Item -LiteralPath $dbSource -Destination $dbTarget -Force
}
if (Test-Path $qrSource) {
    Copy-Item -LiteralPath $qrSource -Destination $qrTarget -Recurse -Force
}

$summary = [PSCustomObject]@{
    SourceDir = $SourceDir
    SeedDir = $seedDir
    DatabaseCopied = Test-Path $dbTarget
    QRCodesCopied = Test-Path $qrTarget
}
$summary | Format-List
