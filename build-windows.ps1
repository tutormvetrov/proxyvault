param(
    [switch]$SkipAudit,
    [switch]$SkipTests,
    [switch]$SkipLocalData
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE."
    }
}

$root = (Get-Location).Path
$releaseDir = Join-Path $root "release"
$stageDir = Join-Path $releaseDir "ProxyVault-win-x64"
$archivePath = Join-Path $releaseDir "ProxyVault-win-x64.zip"
$distDir = Join-Path $root "dist-windows"
$buildDir = Join-Path $root "build-windows"
$portableMarker = Join-Path $stageDir "proxyvault.portable"
$portableSeedDir = Join-Path $root "portable-seed"
$portableSourceDir = if (Test-Path $portableSeedDir) { $portableSeedDir } else { (& python -c "from app.paths import HOME_APP_DIR; print(HOME_APP_DIR)").Trim() }

foreach ($path in @($stageDir, $archivePath, $distDir, $buildDir)) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

Invoke-Checked { python -m pip install -r requirements-build.txt }

if (-not $SkipAudit) {
    $auditArgs = @("-m", "pip_audit", "-r", "requirements-build.txt")
    if (Test-Path "audit-waivers.txt") {
        foreach ($line in Get-Content "audit-waivers.txt") {
            $waiver = $line.Trim()
            if ($waiver -and -not $waiver.StartsWith("#")) {
                $auditArgs += @("--ignore-vuln", $waiver)
            }
        }
    }
    Invoke-Checked { python @auditArgs }
}

if (-not $SkipTests) {
    Invoke-Checked { python -m unittest discover -s tests -v }
}

Invoke-Checked { python -m PyInstaller --noconfirm --clean ".\proxyvault-windows.spec" --distpath $distDir --workpath $buildDir }

New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
Copy-Item -Path (Join-Path $distDir "ProxyVault\*") -Destination $stageDir -Recurse -Force
Copy-Item -LiteralPath "README.md" -Destination (Join-Path $stageDir "README.md") -Force
Set-Content -LiteralPath $portableMarker -Value "" -NoNewline

if (-not $SkipLocalData -and $portableSourceDir) {
    $dbSource = Join-Path $portableSourceDir "proxyvault.db"
    $qrSource = Join-Path $portableSourceDir "qrcodes"
    if (Test-Path $dbSource) {
        Copy-Item -LiteralPath $dbSource -Destination (Join-Path $stageDir "proxyvault.db") -Force
    }
    if (Test-Path $qrSource) {
        Copy-Item -LiteralPath $qrSource -Destination (Join-Path $stageDir "qrcodes") -Recurse -Force
    }
}

if (-not (Test-Path (Join-Path $stageDir "qrcodes"))) {
    New-Item -ItemType Directory -Path (Join-Path $stageDir "qrcodes") -Force | Out-Null
}

Compress-Archive -LiteralPath $stageDir -DestinationPath $archivePath -Force

$hashLines = @()
Get-ChildItem -Path $releaseDir -Filter "*.zip" | Sort-Object Name | ForEach-Object {
    $hash = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower()
    $hashLines += "$hash *$($_.Name)"
}
Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") -Value $hashLines

Write-Host "Built Windows release archive: $archivePath"
