# One-command run for Windows (PowerShell):  .\run_all.ps1
# Creates the virtual environment on first run, installs requirements, then runs
# every pipeline step and the tests (same steps as `make all` on Mac/Linux).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Creating virtual environment (.venv) ..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Python 3.11+ is required: install it from python.org and tick 'Add to PATH'." }
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed - see the messages above." }
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
& $py -m ddn.pipeline @args
exit $LASTEXITCODE
