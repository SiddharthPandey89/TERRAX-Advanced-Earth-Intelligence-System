$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logs = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$started = @()
$ownershipFile = Join-Path $logs 'project-processes.json'

function Find-Python {
    $candidates = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { foreach ($v in '3.12', '3.11', '3.13', '3.10') { $candidates += ,@{ File = $py.Source; Args = @("-$v") } } }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { $candidates += ,@{ File = $python.Source; Args = @() } }
    foreach ($c in $candidates) {
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        $out = (& $c.File @($c.Args) --version 2>&1 | Out-String).Trim()
        $ErrorActionPreference = $prev
        if ($out -match '^Python 3\.(10|11|12|13)(\.|$)') { return $c }
    }
    throw 'Python 3.10 to 3.13 was not found. Install it from python.org (tick "Add python.exe to PATH") and run this script again.'
}
function Assert-PythonVersion([string]$File, [string[]]$Arguments) {
    $output = (& $File @Arguments --version 2>&1 | Out-String).Trim()
    if ($output -notmatch '^Python 3\.(10|11|12|13)(\.|$)') { throw "Python 3.10 to 3.13 is required; detected '$output'." }
}
function Import-LocalEnv {
    $file = Join-Path $root '.env'
    if (-not (Test-Path $file)) {
        Copy-Item (Join-Path $root '.env.example') $file
        Write-Host 'Created .env from .env.example. Weather analysis works without editing it; optional database/provider settings remain disabled.' -ForegroundColor Yellow
    }
    foreach ($line in Get-Content $file) {
        $text = $line.Trim()
        if (-not $text -or $text.StartsWith('#') -or $text -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { continue }
        $name = $Matches[1]; $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) { $value = $value.Substring(1, $value.Length - 2) }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}
function Assert-PortFree([int]$Port, [string]$Service) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { return }
    # A leftover process from THIS project (command line contains the project folder) is safe to replace.
    if (Test-ProjectProcess ([int]$listener.OwningProcess) $root) {
        Write-Host "Port $Port is held by a previous GeoIntelligence process (PID $($listener.OwningProcess)); stopping it." -ForegroundColor Yellow
        & taskkill.exe /PID ([string]$listener.OwningProcess) /T /F | Out-Null
        $deadline = (Get-Date).AddSeconds(10)
        while ((Get-Date) -lt $deadline -and (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 500 }
        if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) { return }
    }
    throw "Port $Port needed by $Service is in use by another application (PID $($listener.OwningProcess)). Close it or change the port in .env; this script never stops unrelated processes."
}
function Test-ProjectProcess([int]$ProcessId, [string]$Needle) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    return ($proc -and $proc.CommandLine -and $proc.CommandLine.IndexOf($Needle, [StringComparison]::OrdinalIgnoreCase) -ge 0)
}
function Start-ProjectService([string]$Name, [string]$File, [string[]]$Arguments, [string]$WorkingDirectory, [int]$Port, [string]$Needle) {
    Assert-PortFree $Port $Name
    $out = Join-Path $logs "$Name.log"
    $err = Join-Path $logs "$Name.err.log"
    $quotedArgs = foreach ($item in $Arguments) {
        $value = [string]$item
        if ($value -match '[\s"]') { '"' + ($value -replace '"', '\"') + '"' } else { $value }
    }
    $process = Start-Process -FilePath $File -ArgumentList ($quotedArgs -join ' ') -WorkingDirectory $WorkingDirectory -PassThru -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    $script:started += [pscustomobject]@{ name = $Name; pid = $process.Id; match = $Needle }
    Write-Host "Started $Name (PID $($process.Id)); logs: logs/$Name.log" -ForegroundColor Green
}
function Wait-Http([string]$Name, [string]$Url, [int]$ProcessId, [string]$Needle, [int]$Seconds = 60) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-ProjectProcess $ProcessId $Needle)) {
            $log = Join-Path $logs "$Name.err.log"
            $tail = if (Test-Path $log) { (Get-Content $log -Tail 15 -ErrorAction SilentlyContinue) -join "`n" } else { '' }
            throw "$Name stopped before readiness. $tail"
        }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { Write-Host "$Name ready at $Url" -ForegroundColor Green; return }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw "$Name did not become ready at $Url within $Seconds seconds. See logs/$Name.log and logs/$Name.err.log."
}
function Stop-Started {
    foreach ($entry in $script:started) {
        if (Test-ProjectProcess ([int]$entry.pid) $entry.match) {
            & taskkill.exe /PID ([string]$entry.pid) /T /F | Out-Null
        }
    }
}

try {
    if (Test-Path $ownershipFile) {
        $old = Get-Content $ownershipFile -Raw | ConvertFrom-Json
        foreach ($entry in $old.processes) {
            if (Test-ProjectProcess ([int]$entry.pid) ([string]$entry.match)) { throw "This project already has $($entry.name) running (PID $($entry.pid)). Use STOP.bat first." }
        }
    }

    $node = Get-Command node -ErrorAction SilentlyContinue
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $node -or -not $npm) { throw 'Node.js 20+ and npm are required. Run INSTALL.bat after installing Node.js.' }
    $nodeVersion = (& $node.Source --version 2>&1 | Out-String).Trim()
    if ($nodeVersion -notmatch '^v(\d+)\.' -or [int]$Matches[1] -lt 20) { throw "Node.js 20+ is required; detected '$nodeVersion'." }
    $py = Find-Python
    Assert-PythonVersion $py.File $py.Args
    $venvPython = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) { Write-Host 'Project Python environment is missing; running INSTALL.bat setup first.' -ForegroundColor Yellow; & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install.ps1'); if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' } }
    Assert-PythonVersion $venvPython @()
    if (-not (Test-Path (Join-Path $root 'node_modules\vite\bin\vite.js'))) { Write-Host 'Node dependencies are missing; running INSTALL.bat setup first.' -ForegroundColor Yellow; & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install.ps1'); if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' } }
    Import-LocalEnv

    $dbStarted = $false
    $dbStartFailed = $false
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    $password = [Environment]::GetEnvironmentVariable('POSTGRES_PASSWORD', 'Process')
    if ($docker -and $password -and $password -notmatch 'replace-with|change-me|placeholder') {
        $ErrorActionPreference = 'Continue'
        $existing = & $docker.Source compose ps -q postgres 2>$null
        if (-not $existing) {
            $composeOutput = & $docker.Source compose up -d postgres 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0) {
                $dbStartFailed = $true
                Write-Host "Optional PostGIS could not start. $($composeOutput.Trim()) The website will still start without database features." -ForegroundColor Yellow
            } else { $dbStarted = $true }
        } else { Write-Host 'PostGIS container is already running; leaving it untouched.' }
        $ErrorActionPreference = 'Stop'
    } elseif ($docker) {
        Write-Host 'Optional PostGIS skipped: configure a unique POSTGRES_PASSWORD and matching DATABASE_URL in .env to enable it.' -ForegroundColor Yellow
    } else {
        Write-Host 'Optional PostGIS skipped: Docker is not installed. Weather analysis does not require a database.' -ForegroundColor Yellow
    }

    $backendPort = if ($env:PORT -match '^\d+$') { [int]$env:PORT } else { 5000 }
    $mlPort = if ($env:ML_SERVICE_PORT -match '^\d+$') { [int]$env:ML_SERVICE_PORT } else { 8000 }
    $frontPort = if ($env:VITE_PORT -match '^\d+$') { [int]$env:VITE_PORT } else { 5173 }
    $nodeExe = $node.Source
    $vite = Join-Path $root 'node_modules\vite\bin\vite.js'
    $mlAppDir = Join-Path $root 'geo-ml-service'
    $backendScript = Join-Path $root 'backend\server.js'
    Start-ProjectService 'ml-service' $venvPython @('-m','uvicorn','main:app','--app-dir',$mlAppDir,'--host','127.0.0.1','--port',[string]$mlPort) $root $mlPort $mlAppDir
    Start-ProjectService 'backend' $nodeExe @($backendScript) (Join-Path $root 'backend') $backendPort $backendScript
    Start-ProjectService 'frontend' $nodeExe @($vite,'--host','127.0.0.1','--port',[string]$frontPort,'--strictPort') (Join-Path $root 'frontend') $frontPort $vite

    $databaseReady = (-not $dbStarted -and -not $dbStartFailed)
    if ($dbStarted) {
        $deadline = (Get-Date).AddSeconds(90)
        do { & $docker.Source compose exec -T postgres pg_isready -U $env:POSTGRES_USER -d $env:POSTGRES_DB *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep -Seconds 3 } while ((Get-Date) -lt $deadline)
        $databaseReady = ($LASTEXITCODE -eq 0)
        if (-not $databaseReady) { Write-Host 'PostGIS did not become ready; app remains available without database features.' -ForegroundColor Yellow }
    }
    if ($databaseReady -and $env:DATABASE_URL -and $env:DATABASE_URL -notmatch 'replace-with|change-me|placeholder') {
        & $venvPython (Join-Path $root 'scripts\migrate.py')
        if ($LASTEXITCODE -ne 0) { Write-Host 'Database migration did not complete; app remains available without database features.' -ForegroundColor Yellow }
    }

    $processes = $script:started
    $data = [ordered]@{ startedAt = (Get-Date).ToString('o'); processes = @($processes); stopPostgres = $dbStarted }
    $data | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $ownershipFile
    foreach ($entry in $script:started) {
        $url = switch ($entry.name) { 'ml-service' { "http://127.0.0.1:$mlPort/health" } 'backend' { "http://127.0.0.1:$backendPort/api/health" } 'frontend' { "http://127.0.0.1:$frontPort/" } }
        Wait-Http $entry.name $url ([int]$entry.pid) $entry.match
    }
    $site = "http://127.0.0.1:$frontPort"
    Start-Process $site
    Write-Host "`nGeoIntelligence is ready at $site. Keep this window open for status; use STOP.bat to close services." -ForegroundColor Green
    Read-Host 'Press Enter to close this status window'
    exit 0
} catch {
    Stop-Started
    if ($dbStarted -and $docker) { & $docker.Source compose stop postgres *> $null }
    Write-Host "`nSTART ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'See service logs under logs/ for details.' -ForegroundColor Yellow
    Read-Host 'Press Enter to close this window'
    exit 1
}
