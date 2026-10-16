$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { py -3 -m venv .venv }
else { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "설치 완료. .env 파일에 RCON_PASSWORD, FM_PASSWORD를 설정하세요." -ForegroundColor Yellow
} else {
    Write-Host ".env 파일이 이미 있어 설정을 보존했습니다." -ForegroundColor Green
}
if (-not (Test-Path factories.json)) {
    Copy-Item factories.example.json factories.json
    Write-Host "factories.json을 만들었습니다. 실제 상자 좌표로 바꾼 후 실행하세요." -ForegroundColor Yellow
}
Write-Host "설정 완료 후 .\start_server.cmd 실행 => http://127.0.0.1:8000"
