param(
    [switch]$SkipAudit,
    [switch]$SkipTests,
    [switch]$IncludeLocalData,
    [string]$PortableSourceDir,
    [switch]$NoPauseOnError
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

trap {
    Write-Host ""
    Write-Host "ProxyVault Windows build failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if (-not $NoPauseOnError) {
        Write-Host ""
        Read-Host "Press Enter to close this window"
    }
    exit 1
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action,
        [int]$Retries = 0,
        [int]$RetryDelaySeconds = 2,
        [int[]]$RetryExitCodes = @()
    )

    for ($attempt = 0; $attempt -le $Retries; $attempt++) {
        & $Action
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {
            $global:LASTEXITCODE = 0
            return
        }

        $shouldRetry = $attempt -lt $Retries -and (
            $RetryExitCodes.Count -eq 0 -or $RetryExitCodes -contains $exitCode
        )
        if ($shouldRetry) {
            Write-Host "Command failed with exit code $exitCode. Retrying in $RetryDelaySeconds second(s)..."
            Start-Sleep -Seconds $RetryDelaySeconds
            continue
        }

        throw "Command failed with exit code $exitCode."
    }
}

function Invoke-ProcessChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList,
        [int]$Retries = 0,
        [int]$RetryDelaySeconds = 2
    )

    for ($attempt = 0; $attempt -le $Retries; $attempt++) {
        $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -PassThru -NoNewWindow
        $exitCode = $process.ExitCode
        if ($exitCode -eq 0) {
            $global:LASTEXITCODE = 0
            return
        }

        if ($attempt -lt $Retries) {
            Write-Host "Process '$FilePath' failed with exit code $exitCode. Retrying in $RetryDelaySeconds second(s)..."
            Start-Sleep -Seconds $RetryDelaySeconds
            continue
        }

        throw "Process '$FilePath' failed with exit code $exitCode."
    }
}

function Assert-FileExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LiteralPath,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
        throw "$Description is missing: $LiteralPath"
    }
}

$root = (Get-Location).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$releaseDir = Join-Path $root "release"
$stageDir = Join-Path $releaseDir "ProxyVault-win-x64"
$archivePath = Join-Path $releaseDir "ProxyVault-win-x64.zip"
$distDir = Join-Path $root "dist-windows"
$buildDir = Join-Path $root "build-windows"
$portableMarker = Join-Path $stageDir "proxyvault.portable"
$portableSeedDir = Join-Path $root "portable-seed"
$resolvedPortableSourceDir = $null

if ($PortableSourceDir) {
    if (-not (Test-Path -LiteralPath $PortableSourceDir -PathType Container)) {
        throw "Portable source directory does not exist: $PortableSourceDir"
    }
    $resolvedPortableSourceDir = (Resolve-Path -LiteralPath $PortableSourceDir).Path
}
elseif (Test-Path -LiteralPath $portableSeedDir -PathType Container) {
    $resolvedPortableSourceDir = (Resolve-Path -LiteralPath $portableSeedDir).Path
}

foreach ($path in @($stageDir, $archivePath, $distDir, $buildDir)) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

$repoSingBox = Join-Path $root "engines\sing-box\windows\sing-box.exe"
$repoCronet = Join-Path $root "engines\sing-box\windows\libcronet.dll"
$repoWireGuardHelper = Join-Path $root "engines\wireguard\windows\proxyvault-wireguard-windows.exe"
$repoWireGuardBootstrapManifest = Join-Path $root "engines\wireguard\windows\wireguard-bootstrap.json"
$repoWireGuardBootstrapMsi = Join-Path $root "engines\wireguard\windows\wireguard-amd64-0.6.1.msi"
$repoAmneziaWGHelper = Join-Path $root "engines\amneziawg\windows\proxyvault-amneziawg-windows.exe"
$repoAmneziaWGExe = Join-Path $root "engines\amneziawg\windows\AmneziaWG\amneziawg.exe"
$repoAmneziaWGAwg = Join-Path $root "engines\amneziawg\windows\AmneziaWG\awg.exe"
$repoAmneziaWGWintun = Join-Path $root "engines\amneziawg\windows\AmneziaWG\wintun.dll"
$repoThirdPartyNotices = Join-Path $root "tools\runtime_assets\THIRD_PARTY_NOTICES.md"
$repoLicenseReadme = Join-Path $root "tools\runtime_assets\LICENSES\README.md"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    python -m venv .venv
}

Invoke-Checked { & $python -m pip install -r requirements-build.txt }
Invoke-Checked { & $python ".\tools\runtime_assets\bootstrap_runtime_assets.py" --target windows --rebuild-helper }

Assert-FileExists -LiteralPath $repoSingBox -Description "Bundled sing-box executable"
Assert-FileExists -LiteralPath $repoCronet -Description "Bundled libcronet.dll"
Assert-FileExists -LiteralPath $repoWireGuardHelper -Description "Bundled WireGuard Windows helper"
Assert-FileExists -LiteralPath $repoWireGuardBootstrapManifest -Description "Bundled WireGuard bootstrap manifest"
Assert-FileExists -LiteralPath $repoWireGuardBootstrapMsi -Description "Bundled WireGuard bootstrap installer"
Assert-FileExists -LiteralPath $repoAmneziaWGHelper -Description "Bundled AmneziaWG Windows helper"
Assert-FileExists -LiteralPath $repoAmneziaWGExe -Description "Bundled AmneziaWG executable"
Assert-FileExists -LiteralPath $repoAmneziaWGAwg -Description "Bundled awg.exe"
Assert-FileExists -LiteralPath $repoAmneziaWGWintun -Description "Bundled AmneziaWG wintun.dll"
Assert-FileExists -LiteralPath $repoThirdPartyNotices -Description "Third-party notices bundle"
Assert-FileExists -LiteralPath $repoLicenseReadme -Description "Third-party license bundle"

Invoke-Checked {
    & $python -c "from app.runtime.paths import resolve_sing_box_asset_layout, sing_box_support_asset_names; resolve_sing_box_asset_layout(platform_name='windows', required_support_files=sing_box_support_asset_names('windows')); print('Validated bundled sing-box assets for Windows.')"
}

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
    Invoke-Checked { & $python @auditArgs }
}

if (-not $SkipTests) {
    Invoke-Checked { & $python ".\tools\run_unittest_shards.py" --root tests --verbose }
}

Invoke-ProcessChecked -FilePath $python -ArgumentList @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    ".\proxyvault-windows.spec",
    "--distpath",
    ('"{0}"' -f $distDir),
    "--workpath",
    ('"{0}"' -f $buildDir)
) -Retries 1

New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
Copy-Item -Path (Join-Path $distDir "ProxyVault\*") -Destination $stageDir -Recurse -Force
Invoke-Checked { & $python ".\tools\release_bundle.py" copy-payload --platform windows --stage-dir $stageDir }
Set-Content -LiteralPath $portableMarker -Value "" -NoNewline

$stagedSingBox = Join-Path $stageDir "engines\sing-box\windows\sing-box.exe"
$stagedCronet = Join-Path $stageDir "engines\sing-box\windows\libcronet.dll"
$stagedWireGuardHelper = Join-Path $stageDir "engines\wireguard\windows\proxyvault-wireguard-windows.exe"
$stagedWireGuardBootstrapManifest = Join-Path $stageDir "engines\wireguard\windows\wireguard-bootstrap.json"
$stagedWireGuardBootstrapMsi = Join-Path $stageDir "engines\wireguard\windows\wireguard-amd64-0.6.1.msi"
$stagedAmneziaWGHelper = Join-Path $stageDir "engines\amneziawg\windows\proxyvault-amneziawg-windows.exe"
$stagedAmneziaWGExe = Join-Path $stageDir "engines\amneziawg\windows\AmneziaWG\amneziawg.exe"
$stagedAmneziaWGAwg = Join-Path $stageDir "engines\amneziawg\windows\AmneziaWG\awg.exe"
$stagedAmneziaWGWintun = Join-Path $stageDir "engines\amneziawg\windows\AmneziaWG\wintun.dll"
$stagedThirdPartyNotices = Join-Path $stageDir "THIRD_PARTY_NOTICES.md"
$stagedLicenseReadme = Join-Path $stageDir "LICENSES\README.md"
$stagedHelpContentRu = Join-Path $stageDir "_internal\app\help\content_ru.md"
$stagedHelpWelcomeRu = Join-Path $stageDir "_internal\app\help\welcome_ru.md"

Assert-FileExists -LiteralPath $stagedSingBox -Description "Staged sing-box executable"
Assert-FileExists -LiteralPath $stagedCronet -Description "Staged libcronet.dll"
Assert-FileExists -LiteralPath $stagedWireGuardHelper -Description "Staged WireGuard Windows helper"
Assert-FileExists -LiteralPath $stagedWireGuardBootstrapManifest -Description "Staged WireGuard bootstrap manifest"
Assert-FileExists -LiteralPath $stagedWireGuardBootstrapMsi -Description "Staged WireGuard bootstrap installer"
Assert-FileExists -LiteralPath $stagedAmneziaWGHelper -Description "Staged AmneziaWG Windows helper"
Assert-FileExists -LiteralPath $stagedAmneziaWGExe -Description "Staged AmneziaWG executable"
Assert-FileExists -LiteralPath $stagedAmneziaWGAwg -Description "Staged awg.exe"
Assert-FileExists -LiteralPath $stagedAmneziaWGWintun -Description "Staged AmneziaWG wintun.dll"
Assert-FileExists -LiteralPath $stagedThirdPartyNotices -Description "Staged third-party notices bundle"
Assert-FileExists -LiteralPath $stagedLicenseReadme -Description "Staged third-party license bundle"
Assert-FileExists -LiteralPath $stagedHelpContentRu -Description "Staged Russian help content"
Assert-FileExists -LiteralPath $stagedHelpWelcomeRu -Description "Staged Russian welcome content"
Invoke-Checked { & $python ".\tools\release_bundle.py" validate-stage --platform windows --stage-dir $stageDir }

if ($IncludeLocalData) {
    if (-not $resolvedPortableSourceDir) {
        throw "IncludeLocalData was requested, but no portable seed directory was provided or found."
    }
    $dbSource = Join-Path $resolvedPortableSourceDir "proxyvault.db"
    $qrSource = Join-Path $resolvedPortableSourceDir "qrcodes"
    if (Test-Path $dbSource) {
        Copy-Item -LiteralPath $dbSource -Destination (Join-Path $stageDir "proxyvault.db") -Force
    }
    if (Test-Path $qrSource) {
        Copy-Item -LiteralPath $qrSource -Destination (Join-Path $stageDir "qrcodes") -Recurse -Force
    }
}
else {
    Write-Host "Staging Windows release. Private portable-seed payload is bundled when present."
}

if (-not (Test-Path (Join-Path $stageDir "qrcodes"))) {
    New-Item -ItemType Directory -Path (Join-Path $stageDir "qrcodes") -Force | Out-Null
}

if (-not $IncludeLocalData) {
    $stagedDatabase = Join-Path $stageDir "proxyvault.db"
    if (Test-Path -LiteralPath $stagedDatabase -PathType Leaf) {
        throw "Clean Windows release unexpectedly contains staged local data: $stagedDatabase"
    }
}

Compress-Archive -LiteralPath $stageDir -DestinationPath $archivePath -Force
Invoke-Checked { & $python ".\tools\release_bundle.py" validate-archive --platform windows --archive-path $archivePath }

$hashLines = @()
Get-ChildItem -Path $releaseDir -Filter "*.zip" | Sort-Object Name | ForEach-Object {
    $hash = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower()
    $hashLines += "$hash *$($_.Name)"
}
Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") -Value $hashLines

Write-Host "Built Windows release archive: $archivePath"
exit 0
