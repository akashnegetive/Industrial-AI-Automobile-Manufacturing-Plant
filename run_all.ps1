# One-command run for Windows (PowerShell):  .\run_all.ps1
# Creates the virtual environment on first run, (re)installs requirements whenever
# requirements.txt changes, then runs every pipeline step and the tests
# (same steps as `make all` on Mac/Linux).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Creating virtual environment (.venv) ..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Python 3.11+ is required: install it from python.org and tick 'Add to PATH'." }
    & $py -m pip install --upgrade pip
}

# Reinstall only when requirements.txt changed since the last install (stamp file inside .venv).
$stamp = Join-Path $PSScriptRoot ".venv\requirements.sha256"
$hash = (Get-FileHash (Join-Path $PSScriptRoot "requirements.txt") -Algorithm SHA256).Hash
$old = if (Test-Path $stamp) { Get-Content $stamp } else { "" }
if ($hash -ne $old) {
    Write-Host "Installing / updating requirements ..."
    & $py -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed - see the messages above." }
    Set-Content -Path $stamp -Value $hash
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
& $py -m ddn.pipeline @args
exit $LASTEXITCODE
