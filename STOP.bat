@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
if errorlevel 1 (
  echo.
  echo Shutdown encountered an error. Review the messages above.
  pause
  exit /b 1
)
echo.
echo Project services have been stopped where ownership was verified.
pause
endlocal
