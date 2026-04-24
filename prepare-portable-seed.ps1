param(
    [string]$SourceDb,
    [switch]$FromGitHead,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

& "$PSScriptRoot\run-dev.ps1" -CheckOnly | Out-Host

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$args = @(".\tools\create_portable_seed.py")
if ($SourceDb) {
    $args += @("--source-db", $SourceDb)
}
if ($FromGitHead) {
    $args += "--from-git-head"
}
if ($Force) {
    $args += "--force"
}

& $python @args
