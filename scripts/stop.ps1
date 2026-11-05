$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$ownershipFile = Join-Path $root 'logs\project-processes.json'
function Test-ProjectProcess([int]$ProcessId, [string]$Needle) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    return ($proc -and $proc.CommandLine -and $proc.CommandLine.IndexOf($Needle, [StringComparison]::OrdinalIgnoreCase) -ge 0)
}
if (-not (Test-Path $ownershipFile)) { Write-Host 'No project-owned process record found; no process was stopped.' -ForegroundColor Yellow; exit 0 }
try {
    $state = Get-Content $ownershipFile -Raw | ConvertFrom-Json
    foreach ($entry in $state.processes) {
        if (Test-ProjectProcess ([int]$entry.pid) ([string]$entry.match)) {
            Write-Host "Stopping $($entry.name) (PID $($entry.pid))..."
            & taskkill.exe /PID ([string]$entry.pid) /T /F | Out-Null
        } else { Write-Host "Leaving PID $($entry.pid) untouched; it is no longer the verified $($entry.name) process." -ForegroundColor Yellow }
    }
    if ($state.stopPostgres) {
        $docker = Get-Command docker -ErrorAction SilentlyContinue
        if ($docker) { & $docker.Source compose stop postgres; if ($LASTEXITCODE -ne 0) { Write-Host 'Could not stop this project PostGIS container; inspect Docker Desktop.' -ForegroundColor Yellow } }
    }
    Remove-Item $ownershipFile -Force -ErrorAction SilentlyContinue
    Write-Host 'Shutdown complete.' -ForegroundColor Green
} catch { Write-Host "STOP ERROR: $($_.Exception.Message)" -ForegroundColor Red; exit 1 }
