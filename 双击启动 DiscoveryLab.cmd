@echo off
setlocal

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch.ps1" %*
if errorlevel 1 (
  echo.
  echo DiscoveryLab failed to start. Keep this window open and send the message above to Codex.
  pause
)

endlocal
