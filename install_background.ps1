#Requires -RunAsAdministrator
# Install Factory Monitor as a persistent Windows startup task.
# Run once from an elevated PowerShell:
# powershell -ExecutionPolicy Bypass -File .\install_background.ps1

$ErrorActionPreference = "Stop"
$TaskName = "CNSH Factory Monitor"
$Root = $PSScriptRoot
$Launcher = Join-Path $Root "start_server.cmd"
$Python = Join-Path $Root ".conda\python.exe"
$App = Join-Path $Root "app.py"

foreach ($Path in @($Launcher, $Python, $App)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file missing: $Path. Run setup_windows.ps1 first."
    }
}

Import-Module ScheduledTasks

# cmd.exe is noninteractive when Task Scheduler starts it as SYSTEM.
# Use start_server.cmd so stdout and stderr still append to logs\server.log.
$Cmd = Join-Path $env:SystemRoot "System32\cmd.exe"
$CmdArgs = '/d /c ""{0}""' -f $Launcher
$Action = New-ScheduledTaskAction -Execute $Cmd -Argument $CmdArgs -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3 -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Minecraft factory inventory dashboard and RCON collector" -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName" -ForegroundColor Green
Write-Host "Runs as SYSTEM at Windows startup, without a PowerShell window."

# Never kill a running application automatically: it might be the user's
# already-running foreground server or another program on this port.
$Port = 8000
$EnvFile = Join-Path $Root ".env"
if (Test-Path -LiteralPath $EnvFile) {
    $PortLine = Get-Content -LiteralPath $EnvFile |
        Where-Object { $_ -match '^\s*FM_PORT\s*=\s*(\d+)\s*$' } |
        Select-Object -Last 1
    if ($PortLine -match '^\s*FM_PORT\s*=\s*(\d+)\s*$') {
        $Port = [int]$Matches[1]
    }
}
$Listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($Listeners.Count -gt 0) {
    Write-Host "Port $Port is already in use. The startup task was installed but not started." -ForegroundColor Yellow
    Write-Host "Stop the old foreground server (Ctrl+C), then run:"
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
} else {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 2
    $Task = Get-ScheduledTask -TaskName $TaskName
    Write-Host "Scheduled task state: $($Task.State)"
    Write-Host "Open http://127.0.0.1:$Port after startup."
}

Write-Host "Logs: $Root\logs\server.log"
Write-Host "Check: Get-ScheduledTask -TaskName '$TaskName'"
