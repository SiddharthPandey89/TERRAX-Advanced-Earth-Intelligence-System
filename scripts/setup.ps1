$root = Split-Path -Parent $PSScriptRoot
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install.ps1')
exit $LASTEXITCODE
