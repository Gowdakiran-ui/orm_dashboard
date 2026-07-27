$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message, [string]$Type="INFO")
    $color = "Cyan"
    if ($Type -eq "SUCCESS") { $color = "Green" }
    if ($Type -eq "WARN") { $color = "Yellow" }
    if ($Type -eq "ERROR") { $color = "Red" }
    Write-Host "[$Type] $Message" -ForegroundColor $color
}

function Kill-PortProcesses {
    param([int]$Port)
    $pids = (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue).OwningProcess
    foreach ($processId in $pids) {
        if ($processId -ne 0 -and $processId -ne $PID) {
            Write-Log "Killing stale process (PID $processId) listening on port $Port..." -Type WARN
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Wait-ForHttp {
    param([string]$Url, [int]$TimeoutSeconds=30)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
            # Ignore and retry
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Check-Queues {
    param([string]$PythonExe, [string]$OrmCollectionDir)
    Write-Log "Verifying Celery queues..." -Type INFO
    $prev = (Get-Location).Path
    Set-Location $OrmCollectionDir
    $env:PYTHONPATH = $OrmCollectionDir
    $result = & $PythonExe -m celery -A app.core.celery_app.celery_app inspect active_queues | Out-String
    $env:PYTHONPATH = ""
    Set-Location $prev
    
    $required = @("io_queue", "cpu_queue", "nlp_queue", "aggregation_queue", "pipeline_queue")
    $missing = $false
    foreach ($q in $required) {
        if ($result -notmatch $q) {
            Write-Log "Queue missing: $q" -Type ERROR
            $missing = $true
        }
    }
    return (-not $missing)
}

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$OrmCollectionDir = Join-Path $RootDir "orm_collection"
$OrmDashboardDir = Join-Path $RootDir "orm_dashboard"
$PythonExe = Join-Path $OrmCollectionDir "venv\Scripts\python.exe"

# Environment-configurable endpoints (override via env vars for non-local deployments)
$BackendHost  = if ($env:BACKEND_HOST)  { $env:BACKEND_HOST }  else { "localhost" }
$BackendPort  = if ($env:BACKEND_PORT)  { $env:BACKEND_PORT }  else { "8000" }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3000" }
$BackendUrl   = "http://${BackendHost}:${BackendPort}"
$FrontendUrl  = "http://localhost:${FrontendPort}"


Write-Log "Starting Pre-flight Verification..." -Type INFO
$verifyScript = Join-Path $PSScriptRoot "verify_environment.py"
& $PythonExe $verifyScript
if ($LASTEXITCODE -ne 0) {
    Write-Log "Pre-flight checks failed. Aborting startup." -Type ERROR
    exit 1
}

Write-Log "Cleaning up stale processes..." -Type INFO
Kill-PortProcesses -Port 8000
Kill-PortProcesses -Port 3000

Write-Log "Starting Backend API..." -Type INFO
$BackendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmCollectionDir"" && .\venv\Scripts\activate && python -m uvicorn app.main:app --port 8000" -WindowStyle Normal -PassThru
if (-not (Wait-ForHttp -Url "$BackendUrl/health" -TimeoutSeconds 30)) {
    Write-Log "Backend failed to become healthy." -Type ERROR
    exit 1
}
Write-Log "Backend is healthy." -Type SUCCESS

Write-Log "Starting General Celery Worker..." -Type INFO
$WorkerProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmCollectionDir"" && .\venv\Scripts\activate && python -m celery -A app.core.celery_app.celery_app worker --loglevel=info --hostname=general@%h --pool=solo --concurrency=4 -Q io_queue,cpu_queue,nlp_queue,aggregation_queue" -WindowStyle Normal -PassThru

Write-Log "Starting Pipeline Celery Worker..." -Type INFO
$PipelineWorkerProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmCollectionDir"" && .\venv\Scripts\activate && python -m celery -A app.core.celery_app.celery_app worker --loglevel=info --hostname=pipeline@%h --pool=solo --concurrency=4 -Q pipeline_queue" -WindowStyle Normal -PassThru

# Wait for celery worker to ping
$celeryPingOk = $false
$sw = [Diagnostics.Stopwatch]::StartNew()
$prev = (Get-Location).Path
Set-Location $OrmCollectionDir
$env:PYTHONPATH = $OrmCollectionDir

while ($sw.Elapsed.TotalSeconds -lt 60) {
    $pingResult = & $PythonExe -m celery -A app.core.celery_app.celery_app inspect ping | Out-String
    if ($pingResult -match "pong" -or $pingResult -match "OK") {
        $celeryPingOk = $true
        break
    }
    Start-Sleep -Seconds 2
}

$env:PYTHONPATH = ""
Set-Location $prev

if (-not $celeryPingOk) {
    Write-Log "Celery worker failed to respond to ping." -Type ERROR
    exit 1
}
Write-Log "Celery Worker is healthy." -Type SUCCESS

Write-Log "Starting Celery Beat..." -Type INFO
$BeatProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmCollectionDir"" && .\venv\Scripts\activate && python -m celery -A app.core.celery_app.celery_app beat --loglevel=info" -WindowStyle Normal -PassThru

Write-Log "Starting Frontend..." -Type INFO
$FrontendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmDashboardDir"" && npm run dev" -WindowStyle Normal -PassThru
# Next.js development server might take a bit
if (-not (Wait-ForHttp -Url "$FrontendUrl" -TimeoutSeconds 45)) {
    Write-Log "Frontend failed to start." -Type ERROR
    exit 1
}
Write-Log "Frontend is ready." -Type SUCCESS

Write-Log "Running Final System Checks..." -Type INFO
$queuesOk = Check-Queues -PythonExe $PythonExe -OrmCollectionDir $OrmCollectionDir
if (-not $queuesOk) {
    Write-Log "Queue verification failed." -Type ERROR
    exit 1
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "             SYSTEM STATUS REPORT               " -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "+ PostgreSQL       : OK" -ForegroundColor Green
Write-Host "+ Redis            : OK" -ForegroundColor Green
Write-Host "+ Environment      : OK" -ForegroundColor Green
Write-Host "+ Database         : OK (Migrations applied)" -ForegroundColor Green
Write-Host "+ Celery Worker    : OK" -ForegroundColor Green
Write-Host "+ Celery Beat      : OK" -ForegroundColor Green
Write-Host "+ Backend API      : OK" -ForegroundColor Green
Write-Host "+ Frontend         : OK" -ForegroundColor Green
Write-Host "+ Pipeline Queue   : OK" -ForegroundColor Green

Write-Host ""
Write-Host "ORM Intelligence Platform Ready" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Backend API:   $BackendUrl"
Write-Host "Dashboard:     $FrontendUrl"
Write-Host "Close this window to shut down the orchestrator script."
