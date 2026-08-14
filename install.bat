@echo off
setlocal EnableDelayedExpansion
TITLE ORM Intelligence Platform -- Installer

:: ============================================================
:: ORM Intelligence Platform -- install.bat
:: First-time installation script for internal Windows deployment
:: Run once before running start.bat
:: ============================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "ORM_COLLECTION=%ROOT%\orm_collection"
set "ORM_DASHBOARD=%ROOT%\orm_dashboard"
set "VENV=%ORM_COLLECTION%\venv"
set "PYTHON_EXE=%VENV%\Scripts\python.exe"

echo.
echo ============================================================
echo   ORM Intelligence Platform -- First-Time Installation
echo ============================================================
echo.

:: ============================================================
:: STEP 1 -- Verify Python exists
:: ============================================================
echo [1/9] Checking for Python...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: Python is not installed or not in PATH.
    echo  Please install Python 3.11 or later from:
    echo    https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        Found: %%v
echo        [OK]

:: ============================================================
:: STEP 2 -- Verify Node.js exists
:: ============================================================
echo.
echo [2/9] Checking for Node.js...
node --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: Node.js is not installed or not in PATH.
    echo  Please install Node.js 18 LTS or later from:
    echo    https://nodejs.org/en/download
    echo  NOTE: Do NOT attempt to install it automatically.
    echo        Manual installation is required.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo        Found: Node.js %%v
echo        [OK]

:: ============================================================
:: STEP 3 -- Create virtual environment (ONLY if missing)
:: ============================================================
echo.
echo [3/9] Setting up Python virtual environment...
if exist "%VENV%\Scripts\activate.bat" (
    echo        Virtual environment already exists -- skipping creation.
    echo        [OK]
) else (
    echo        Creating virtual environment at: %VENV%
    python -m venv "%VENV%"
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo  ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo        [OK]
)

:: ============================================================
:: STEP 4 -- Activate virtual environment
:: ============================================================
echo.
echo [4/9] Activating virtual environment...
call "%VENV%\Scripts\activate.bat"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)
echo        [OK]

:: ============================================================
:: STEP 5 -- Install Python dependencies
:: ============================================================
echo.
echo [5/9] Installing Python dependencies from orm_collection\requirements.txt...
pip install -r "%ORM_COLLECTION%\requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ERROR: pip install failed. Check the output above for details.
    pause
    exit /b 1
)
echo        [OK]

:: ============================================================
:: STEP 6 -- Install Node / frontend dependencies (ONLY if missing)
:: ============================================================
echo.
echo [6/9] Checking frontend Node.js dependencies...
if exist "%ORM_DASHBOARD%\node_modules" (
    echo        node_modules already exists -- skipping npm install.
    echo        [OK]
) else (
    echo        Running npm install in orm_dashboard...
    pushd "%ORM_DASHBOARD%"
    npm install
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo  ERROR: npm install failed. Check the output above for details.
        popd
        pause
        exit /b 1
    )
    popd
    echo        [OK]
)

:: ============================================================
:: STEP 7 -- Download spaCy model (ONLY if missing)
:: ============================================================
echo.
echo [7/9] Checking spaCy model (en_core_web_sm)...
"%PYTHON_EXE%" -c "import spacy; spacy.load('en_core_web_sm')" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo        Downloading en_core_web_sm...
    "%PYTHON_EXE%" -m spacy download en_core_web_sm
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo  ERROR: Failed to download spaCy model en_core_web_sm.
        pause
        exit /b 1
    )
    echo        [OK]
) else (
    echo        spaCy model already installed -- skipping download.
    echo        [OK]
)

:: ============================================================
:: STEP 8 -- Install Playwright Chromium (ONLY if missing)
:: ============================================================
echo.
echo [8/9] Checking Playwright Chromium browser...
"%PYTHON_EXE%" -m playwright install --dry-run 2>&1 | findstr /i "chromium" >nul 2>&1
"%PYTHON_EXE%" -c "from playwright.sync_api import sync_playwright; p = sync_playwright().__enter__(); b = p.chromium.launch(); b.close(); p.stop()" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo        Installing Playwright Chromium...
    "%PYTHON_EXE%" -m playwright install chromium
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo  ERROR: Failed to install Playwright Chromium.
        pause
        exit /b 1
    )
    echo        [OK]
) else (
    echo        Playwright Chromium already installed -- skipping.
    echo        [OK]
)

:: ============================================================
:: STEP 9 -- Generate .env from .env.example (ONLY if missing)
:: ============================================================
echo.
echo [9/9] Checking environment configuration...

:: Backend .env (orm_collection\.env)
if exist "%ORM_COLLECTION%\.env" (
    echo        Backend .env already exists -- not overwriting.
) else (
    if exist "%ORM_COLLECTION%\.env.example" (
        copy /Y "%ORM_COLLECTION%\.env.example" "%ORM_COLLECTION%\.env" >nul
        echo.
        echo  *** ACTION REQUIRED ***
        echo  A new backend .env has been created at:
        echo    %ORM_COLLECTION%\.env
        echo.
        echo  You MUST update the following values before starting:
        echo    DB_HOST      -- hostname of your PostgreSQL server
        echo    DB_PORT      -- PostgreSQL port (default: 5432)
        echo    DB_USER      -- PostgreSQL username
        echo    DB_PASSWORD  -- PostgreSQL password
        echo    DB_NAME      -- PostgreSQL database name
        echo    REDIS_URL    -- Redis connection URL (e.g. redis://localhost:6379/0)
        echo    GROQ_API_KEY -- your Groq API key (required for AI features)
        echo.
        echo  S3 variables are only required if ENABLE_S3_STORAGE=true.
        echo  *** END ACTION REQUIRED ***
        echo.
    ) else (
        echo  WARNING: .env.example not found -- please create %ORM_COLLECTION%\.env manually.
    )
)

:: Frontend .env.local (orm_dashboard\.env.local)
if exist "%ORM_DASHBOARD%\.env.local" (
    echo        Frontend .env.local already exists -- not overwriting.
) else (
    if exist "%ORM_DASHBOARD%\.env.example" (
        copy /Y "%ORM_DASHBOARD%\.env.example" "%ORM_DASHBOARD%\.env.local" >nul
        echo        Frontend .env.local created from .env.example.
        echo        Update NEXT_PUBLIC_API_URL if the backend is not on localhost:8000.
    ) else (
        echo  WARNING: %ORM_DASHBOARD%\.env.example not found -- skipping frontend env setup.
    )
)
echo        [OK]

:: ============================================================
:: VERIFY -- PostgreSQL and Redis (using existing utility)
:: ============================================================
echo.
echo Verifying connectivity (PostgreSQL + Redis)...
echo (Skipped if .env has not been configured yet.)
echo.

set "VERIFY_SCRIPT=%ROOT%\scripts\verify_environment.py"
if exist "%VERIFY_SCRIPT%" (
    pushd "%ORM_COLLECTION%"
    "%PYTHON_EXE%" "%VERIFY_SCRIPT%" --apply-schema
    set VERIFY_EXIT=!ERRORLEVEL!
    popd
    if !VERIFY_EXIT! NEQ 0 (
        echo.
        echo  WARNING: Connectivity check reported failures.
        echo  This is normal if you have not yet updated .env with real credentials.
        echo  Update %ORM_COLLECTION%\.env and re-run install.bat,
        echo  or run scripts\verify_environment.py directly after updating credentials.
        echo.
    ) else (
        echo  [OK] PostgreSQL and Redis are reachable.
    )
) else (
    echo  WARNING: verify_environment.py not found -- skipping connectivity check.
)

:: ============================================================
:: DONE
:: ============================================================
echo.
echo ============================================================
echo   INSTALLATION SUCCESSFUL
echo ============================================================
echo.
echo   Next step: double-click start.bat to launch the platform.
echo.
echo   If you have not yet updated .env, do so before starting.
echo.
pause
endlocal
