$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "Conda was not found. Open Anaconda PowerShell Prompt (or run conda init powershell) and retry."
}

# A project-local Conda environment does not depend on the Windows py launcher,
# and remains available to Task Scheduler even when no Conda shell is activated.
$envPath = Join-Path $PSScriptRoot ".conda"
$python = Join-Path $envPath "python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Creating Conda environment in $envPath ..."
    & conda create --yes --prefix $envPath python=3.13 pip
    if ($LASTEXITCODE -ne 0) { throw "Conda environment creation failed (exit $LASTEXITCODE)." }
}
if (-not (Test-Path $python)) { throw "Missing Conda Python: $python" }

Write-Host "Installing Python dependencies ..."
& $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed (exit $LASTEXITCODE)." }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env. Set RCON_PASSWORD and FM_PASSWORD." -ForegroundColor Yellow
} else {
    Write-Host "Existing .env preserved." -ForegroundColor Green
}
if (-not (Test-Path "factories.json")) {
    Copy-Item "factories.example.json" "factories.json"
    Write-Host "Created factories.json. Set your actual chest coordinates." -ForegroundColor Yellow
} else {
    Write-Host "Existing factories.json preserved." -ForegroundColor Green
}
Write-Host "Ready. Edit .env and factories.json, then run .\start_server.cmd."
Write-Host "Dashboard: http://127.0.0.1:8000"
