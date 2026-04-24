param(
    [switch]$CheckOnly,
    [switch]$PauseOnError
)

try {
    $ErrorActionPreference = "Stop"
    Set-Location $PSScriptRoot

    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        python -m venv .venv
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $venvPython -c "import PyQt6, qrcode, PIL, cryptography, requests, yaml" *> $null
    $depsExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference

    if ($depsExitCode -ne 0) {
        & $venvPython -m pip install -r requirements.txt
    }

    if ($CheckOnly) {
        & $venvPython -c "import main; print('ProxyVault dev environment is ready')"
        exit $LASTEXITCODE
    }

    & $venvPython .\main.py
    exit $LASTEXITCODE
} catch {
    Write-Host ""
    Write-Host "ProxyVault dev launch failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($PauseOnError) {
        Write-Host ""
        Read-Host "Press Enter to close this window"
    }
    exit 1
}
