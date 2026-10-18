# AETHER quickstart for Windows (PowerShell 5.1+). Run from the repository root:
#   powershell -ExecutionPolicy Bypass -File scripts\quickstart.ps1            # refresh real data
#   powershell -ExecutionPolicy Bypass -File scripts\quickstart.ps1 -Offline   # use the bundled snapshot
# Installs the backend and console, refreshes the real-data bundle (CelesTrak elements, NASA CMR),
# builds the console and serves it with the API on http://127.0.0.1:8080.
param([switch]$Offline, [int]$Port = 8080)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Need($name, $hint) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "$name not found. $hint" }
}
Need 'py' 'Install Python 3.12 or newer from https://www.python.org (with the py launcher).'
Need 'npm' 'Install Node.js 20 or newer from https://nodejs.org.'

# Some Python packages (astropy) install files about 150 characters below the venv. Without Windows
# long-path support, a deep clone location exceeds the 260-character limit and pip fails.
$longPaths = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
if ($longPaths -ne 1 -and $PWD.Path.Length -gt 80) {
  throw "This folder's path is $($PWD.Path.Length) characters long, and Windows long-path support is off, so the Python install would fail. Clone into a shorter path (for example C:\Users\you\AETHER), or enable long paths: https://pip.pypa.io/warnings/enable-long-paths"
}

$venvPython = 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
  Write-Host 'Creating the Python environment (backend\.venv)...'
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
  py -3 -m venv backend\.venv
}
Write-Host 'Installing the backend...'
& $venvPython -m pip install --quiet --disable-pip-version-check -e './backend[geo,api]'
if ($LASTEXITCODE -ne 0) { throw 'Backend install failed.' }

if (-not (Test-Path 'frontend\node_modules')) {
  Write-Host 'Installing the console...'
  npm --prefix frontend ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'Console install failed.' }
}

# Byte-identical replay needs a fixed BLAS thread count (docs/validation-report.md section 7).
$env:OMP_NUM_THREADS = '1'; $env:OPENBLAS_NUM_THREADS = '1'; $env:MKL_NUM_THREADS = '1'
$env:PYTHONPATH = "$PWD\backend;$PWD"
Write-Host ($(if ($Offline) { 'Using the bundled real-data snapshot...' } else { 'Refreshing real data (falls back to the bundled snapshot if offline)...' }))
if ($Offline) { & $venvPython -m scripts.build_globe_data --offline } else { & $venvPython -m scripts.build_globe_data }
if ($LASTEXITCODE -ne 0) { throw 'Building the real-data bundle failed.' }

Write-Host 'Building the console...'
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw 'Console build failed.' }

$url = "http://127.0.0.1:$Port/?view=globe"
Write-Host "Starting AETHER on $url (Ctrl+C to stop)"
Start-Job -ScriptBlock { param($u) Start-Sleep 4; Start-Process $u } -ArgumentList $url | Out-Null
& $venvPython -m uvicorn scripts.hosted_app:app --host 127.0.0.1 --port $Port
