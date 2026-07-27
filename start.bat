@echo off
TITLE ORM Intelligence Platform Startup
echo Starting ORM Intelligence Platform...
echo Transferring control to PowerShell startup orchestrator...

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_platform.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Startup failed. Please check the errors above.
    pause
) else (
    echo.
    echo Platform is running. Press any key to shutdown all services...
    pause
    echo Shutting down...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8000,3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
    echo Shutdown complete.
)
