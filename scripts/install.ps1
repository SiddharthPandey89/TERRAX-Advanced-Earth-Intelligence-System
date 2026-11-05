$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

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

function Invoke-Checked([string]$File, [string[]]$Arguments, [string]$Label) {
    Write-Host "`n== $Label ==" -ForegroundColor Cyan
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE." }
}

try {
    $node = Get-Command node -ErrorAction SilentlyContinue
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
    if (-not $node -or -not $npm) { throw 'Node.js 20 or newer and npm were not found on PATH. Install Node.js, reopen this window, and retry.' }
    $nodeVersion = (& $node.Source --version 2>&1 | Out-String).Trim()
    if ($nodeVersion -notmatch '^v(\d+)\.' -or [int]$Matches[1] -lt 20) { throw "Node.js 20+ is required; detected '$nodeVersion'." }
    $py = Find-Python
    Assert-PythonVersion $py.File $py.Args

    $venv = Join-Path $root '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        Invoke-Checked $py.File ($py.Args + @('-m', 'venv', $venv)) 'Create Python virtual environment'
    }
    Assert-PythonVersion $venvPython @()
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '--upgrade', 'pip') 'Update pip in project environment'
    Invoke-Checked $venvPython @('-m', 'pip', 'install', '-r', (Join-Path $root 'geo-ml-service\requirements.txt')) 'Install Python dependencies'
    Invoke-Checked $npm.Source @('install', '--no-audit', '--no-fund') 'Install Node.js workspace dependencies'

    $envFile = Join-Path $root '.env'
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $root '.env.example') $envFile
        Write-Host 'Created .env from .env.example. Database/provider settings are optional; edit it before enabling them.' -ForegroundColor Yellow
    }
    $frontendEnv = Join-Path $root 'frontend\.env'
    if (-not (Test-Path $frontendEnv)) { Copy-Item (Join-Path $root 'frontend\.env.example') $frontendEnv }
    New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs') | Out-Null
    Write-Host "`nInstall complete. No service was started." -ForegroundColor Green
    exit 0
} catch {
    Write-Host "`nINSTALL ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
