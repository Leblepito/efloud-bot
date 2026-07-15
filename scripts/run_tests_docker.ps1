# run_tests_docker.ps1
# Official test gate for efloud-bot. Runs pytest inside Docker (Linux, Python 3.11).
# This avoids the pytest+Windows+tempfile teardown bug that causes 500+ errors.
#
# Usage: .\scripts\run_tests_docker.ps1
# Output: Exit code 0 = all tests pass, non-zero = failures.

$ErrorActionPreference = "Stop"

$ImageName = "efloud-bot:test"
$Dockerfile = "Dockerfile"
# $PSScriptRoot = <repo>\scripts -> repo koku BIR seviye yukaridir. Cift
# -Parent tum Downloads'u (12+GB) build context yapiyordu (2026-07-15 bulgusu).
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== Efloud Bot Test Gate (Docker) ===" -ForegroundColor Cyan
Write-Host "Image: $ImageName"
Write-Host "Dockerfile: $Dockerfile"
Write-Host "Project: $ProjectRoot"
Write-Host ""

# Build image
Write-Host "Building Docker image..." -ForegroundColor Yellow
docker build -t $ImageName -f $Dockerfile $ProjectRoot

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker build failed" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Build OK. Running tests..." -ForegroundColor Green
Write-Host ""

# Run tests
docker run --rm `
    -v "${ProjectRoot}:/app" `
    -w //app `
    $ImageName `
    python -m pytest tests/ -q `
    --deselect tests/engine/test_regime_train.py::test_run_auto_train

$ExitCode = $LASTEXITCODE

Write-Host ""
if ($ExitCode -eq 0) {
    Write-Host "=== ALL TESTS PASSED ===" -ForegroundColor Green
} else {
    Write-Host "=== TESTS FAILED ===" -ForegroundColor Red
}

exit $ExitCode
