@echo off
setlocal
TITLE ORM Intelligence Platform Startup

:: ============================================================
:: ORM Intelligence Platform -- start.bat
:: Startup launcher. Assumes install.bat has already been run.
:: DO NOT install dependencies here.
:: ============================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "VENV=%ROOT%\orm_collection\venv"

:: Guard: venv must already exist
if not exist "%VENV%\Scripts\activate.bat" (
    echo.
    echo  ERROR: Virtual environment not found.
    echo  Please run install.bat first.
    echo.
    pause
    exit /b 1
)

echo Starting ORM Intelligence Platform...
echo Transferring control to PowerShell startup orchestrator...

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_platform.ps1"

:: Item 13: shutdown below used to only kill whatever was listening on
:: 8000/3000, which stops the backend/frontend but leaves the Celery
:: worker(s) and beat process orphaned (they hold no listening port, so the
:: old port-scan never saw them). start_platform.ps1 now writes each
:: launched process's PID to scripts\.platform_pids.json as it starts them;
:: the shutdown command reads that file and tree-kills each one (a plain
:: Stop-Process on the tracked cmd.exe /k PID leaves its python.exe child
:: running, confirmed live) before falling back to the original port-based
:: cleanup, which still catches anything not in the PID file.
:: NOTE: this comment block is deliberately kept OUTSIDE the if/else below —
:: a "::" comment containing an unescaped ")" inside a parenthesized batch
:: block prematurely closes the block (a real cmd.exe parsing pitfall, not
:: just a style choice).

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Startup failed. Please check the errors above.
    pause
) else (
    echo.
    echo Platform is running. Press any key to shutdown all services...
    pause
    echo Shutting down...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_platform.ps1"
    echo Shutdown complete.
)
endlocal
