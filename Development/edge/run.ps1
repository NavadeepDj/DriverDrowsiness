Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Always run using the project's virtual environment Python (avoids WindowsApps python.exe issues)
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root "venv\\Scripts\\python.exe"

if (-not (Test-Path $py)) {
  Write-Host "ERROR: venv python not found at: $py"
  Write-Host "Create it from repo root:"
  Write-Host "  python -m venv venv"
  Write-Host "  .\\venv\\Scripts\\python.exe -m pip install -r requirements.txt"
  exit 1
}

& $py (Join-Path $PSScriptRoot "main.py")

