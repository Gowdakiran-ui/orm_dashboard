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

function Save-PlatformPid {
    # Item 13: Start-Process -PassThru handles ($BackendProcess/$WorkerProcess/
    # etc.) were already being captured but never used for shutdown, because
    # start.bat (the process that actually does the shutdown, after the user
    # presses a key) runs as a separate process from this script - its
    # PowerShell variables are gone the moment this script exits. Persisting
    # PIDs to a small state file is the smallest way to hand them across that
    # process boundary. Written incrementally (not once at the end) so that
    # whatever did start is still recorded even if a later step in this
    # script exits early on a failed health check.
    param([string]$Name, [int]$ProcessId)
    $script:PlatformPids[$Name] = $ProcessId
    $script:PlatformPids | ConvertTo-Json | Set-Content -Path $script:PidFile -Encoding utf8
}

function Stop-TrackedPlatformProcesses {
    # Item 14: replace (not refuse) already-running processes from a prior
    # launch. Confirmed live (PowerShell test against a cmd.exe /k child
    # process, matching this script's own launch pattern): Stop-Process on
    # the cmd.exe wrapper's PID leaves its python.exe child running,
    # orphaned - only `taskkill /F /T` (tree kill) takes down the whole
    # process tree. Same mechanism used here as in start.bat's shutdown.
    if (-not (Test-Path $script:PidFile)) { return }
    try {
        $prev = Get-Content $script:PidFile -Raw | ConvertFrom-Json
        foreach ($prop in $prev.PSObject.Properties) {
            $oldPid = $prop.Value
            if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {
                Write-Log "Replacing already-running $($prop.Name) process (PID $oldPid)..." -Type WARN
                taskkill /F /T /PID $oldPid *> $null
            }
        }
    } catch {
        Write-Log "Could not parse existing PID file ($($script:PidFile)), ignoring it: $_" -Type WARN
    }
    Remove-Item $script:PidFile -Force -ErrorAction SilentlyContinue
}

function Check-Queues {
    # TASK.md item 1(3): this used to be a single, non-retried
    # `inspect active_queues` call. INFRA_FINAL_VERIFICATION.md reproduced a
    # false failure live: the worker had just answered a ping (proving it
    # was up) but hadn't yet finished registering its queue consumers, so
    # this check reported queues "missing" that were confirmed correctly
    # bound moments later by a direct re-check -- a timing race, not a real
    # failure.
    #
    # First-pass fix here used a short 5x3s retry loop, which was NOT
    # enough: re-testing live showed queue registration can lag ping
    # readiness by close to the same order of magnitude as the model-load
    # time itself (a cold start's general-worker CPU time was observed at
    # ~7 minutes in one run), not a few seconds -- ping/mingle apparently
    # answers earlier in worker bootstrap than the point where queue
    # consumers actually register. So this uses the same ~180s budget as
    # the ping-wait above (a stopwatch loop, not a fixed attempt count),
    # plus an explicit longer per-call `--timeout` so a single slow-to-
    # respond `inspect` call doesn't itself get mistaken for "queue
    # missing".
    param([string]$PythonExe, [string]$OrmCollectionDir)
    Write-Log "Verifying Celery queues..." -Type INFO
    $prev = (Get-Location).Path
    Set-Location $OrmCollectionDir
    $env:PYTHONPATH = $OrmCollectionDir

    $required = @("io_queue", "cpu_queue", "nlp_queue", "aggregation_queue", "pipeline_queue")
    $missing = $true
    $missingThisAttempt = $required
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt 180) {
        $result = & $PythonExe -m celery -A app.core.celery_app.celery_app inspect active_queues --timeout=10 | Out-String
        $missingThisAttempt = @($required | Where-Object { $result -notmatch $_ })
        if ($missingThisAttempt.Count -eq 0) {
            $missing = $false
            break
        }
        Write-Log "Queues not yet fully registered (missing: $($missingThisAttempt -join ', ')) -- retrying..." -Type WARN
        Start-Sleep -Seconds 5
    }
    if ($missing) {
        foreach ($q in $missingThisAttempt) {
            Write-Log "Queue missing: $q" -Type ERROR
        }
    }

    $env:PYTHONPATH = ""
    Set-Location $prev
    return (-not $missing)
}

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$OrmCollectionDir = Join-Path $RootDir "orm_collection"
$OrmDashboardDir = Join-Path $RootDir "orm_dashboard"
$PythonExe = Join-Path $OrmCollectionDir "venv\Scripts\python.exe"
$script:PidFile = Join-Path $PSScriptRoot ".platform_pids.json"
$script:PlatformPids = @{}

# Environment-configurable endpoints (override via env vars for non-local deployments)
$BackendHost  = if ($env:BACKEND_HOST)  { $env:BACKEND_HOST }  else { "localhost" }
$BackendPort  = if ($env:BACKEND_PORT)  { $env:BACKEND_PORT }  else { "8000" }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { "3000" }
$BackendUrl   = "http://${BackendHost}:${BackendPort}"
$FrontendUrl  = "http://localhost:${FrontendPort}"


Write-Log "Starting Pre-flight Verification..." -Type INFO
$verifyScript = Join-Path $PSScriptRoot "verify_environment.py"
# Phase 5 item 26 / TASK.md (Remove Alembic): no --apply-schema here on
# purpose -- this runs on every start.bat startup, and re-checking schema.sql
# that often is one more DB round-trip than needed (install.bat is the one
# that applies it, via bootstrap_schema.py). This does a column-for-column
# check against schema.sql and aborts with instructions if anything's
# missing, rather than silently starting against a stale/partial schema.
& $PythonExe $verifyScript
if ($LASTEXITCODE -ne 0) {
    Write-Log "Pre-flight checks failed. Aborting startup." -Type ERROR
    exit 1
}

Write-Log "Cleaning up stale processes..." -Type INFO
Stop-TrackedPlatformProcesses
Kill-PortProcesses -Port $BackendPort
Kill-PortProcesses -Port $FrontendPort

Write-Log "Starting Backend API..." -Type INFO
$BackendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmCollectionDir"" && .\venv\Scripts\activate && python -m uvicorn app.main:app --port $BackendPort" -WindowStyle Normal -PassThru
Save-PlatformPid -Name "backend" -ProcessId $BackendProcess.Id
if (-not (Wait-ForHttp -Url "$BackendUrl/health" -TimeoutSeconds 30)) {
    Write-Log "Backend failed to become healthy." -Type ERROR
    exit 1
}
Write-Log "Backend is healthy." -Type SUCCESS

Write-Log "Starting General Celery Worker..." -Type INFO
$WorkerProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmCollectionDir"" && .\venv\Scripts\activate && python -m celery -A app.core.celery_app.celery_app worker --loglevel=info --hostname=general@%h --pool=solo --concurrency=1 -Q io_queue,cpu_queue,nlp_queue,aggregation_queue" -WindowStyle Normal -PassThru
Save-PlatformPid -Name "worker" -ProcessId $WorkerProcess.Id

Write-Log "Starting Pipeline Celery Worker..." -Type INFO
$PipelineWorkerProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmCollectionDir"" && .\venv\Scripts\activate && python -m celery -A app.core.celery_app.celery_app worker --loglevel=info --hostname=pipeline@%h --pool=solo --concurrency=1 -Q pipeline_queue" -WindowStyle Normal -PassThru
Save-PlatformPid -Name "pipeline_worker" -ProcessId $PipelineWorkerProcess.Id

# Wait for celery worker to ping
#
# TASK.md item 1(2): 60s was too short on this machine's real cold start.
# INFRA_FORENSICS.md's own live measurement (worker cold start: model
# loading) clocked ~40s for the *lighter* pipeline_queue-only worker; the
# general worker started here also loads the sentiment/NER models
# (FinBERT via sentiment_analyzer, spaCy via entity_extractor/
# entity_discovery, per the Processing-layer audit) on top of that, and
# INFRA_FINAL_VERIFICATION.md reproduced it live still loading (rising
# memory/CPU, not hung) past 100s. 180s gives real headroom above both
# observed numbers rather than guessing a bigger one.
$celeryPingOk = $false
$sw = [Diagnostics.Stopwatch]::StartNew()
$prev = (Get-Location).Path
Set-Location $OrmCollectionDir
$env:PYTHONPATH = $OrmCollectionDir

while ($sw.Elapsed.TotalSeconds -lt 180) {
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
Save-PlatformPid -Name "beat" -ProcessId $BeatProcess.Id

# Item 15(b): the "Celery Beat: OK" status line used to be printed
# unconditionally, with no check that beat actually started. There's no
# ping-style RPC for beat (unlike the worker check above), so the smallest
# real check available is liveness: confirm the cmd.exe wrapper AND a
# python child under it are still alive a few seconds after launch - a
# beat that failed immediately (bad schedule config, import error) leaves
# no python child even if cmd.exe itself is still sitting at its /k prompt.
Start-Sleep -Seconds 3
$beatChildAlive = [bool](Get-CimInstance Win32_Process -Filter "ParentProcessId=$($BeatProcess.Id)" -ErrorAction SilentlyContinue)
$beatProcessAlive = [bool](Get-Process -Id $BeatProcess.Id -ErrorAction SilentlyContinue)
$script:beatOk = $beatProcessAlive -and $beatChildAlive
if ($script:beatOk) {
    Write-Log "Celery Beat is running." -Type SUCCESS
} else {
    Write-Log "Celery Beat exited shortly after launch - check its window for errors." -Type ERROR
}

Write-Log "Starting Frontend..." -Type INFO
$FrontendProcess = Start-Process -FilePath "cmd.exe" -ArgumentList "/k cd /d ""$OrmDashboardDir"" && npm run dev" -WindowStyle Normal -PassThru
Save-PlatformPid -Name "frontend" -ProcessId $FrontendProcess.Id
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
# TASK.md item 2: this used to unconditionally claim "(Migrations applied)",
# which stopped being true once Phase 5 item 26 made this script's
# pre-flight check-only (no --apply-schema) -- it now only confirms the
# schema already matches schema.sql, never applies anything itself.
# install.bat is the only path that actually applies it (via
# bootstrap_schema.py); its own connectivity check output legitimately
# differs ("Database schema is up to date" from verify_environment.py's
# --apply-schema branch after a real schema bootstrap) rather than claiming
# an apply happened here too.
Write-Host "+ Database         : OK (schema up to date)" -ForegroundColor Green
Write-Host "+ Celery Worker    : OK" -ForegroundColor Green
if ($script:beatOk) {
    Write-Host "+ Celery Beat      : OK" -ForegroundColor Green
} else {
    Write-Host "+ Celery Beat      : FAILED (exited after launch)" -ForegroundColor Red
}
Write-Host "+ Backend API      : OK" -ForegroundColor Green
Write-Host "+ Frontend         : OK" -ForegroundColor Green
Write-Host "+ Pipeline Queue   : OK" -ForegroundColor Green

Write-Host ""
Write-Host "ORM Intelligence Platform Ready" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Backend API:   $BackendUrl"
Write-Host "Dashboard:     $FrontendUrl"
Write-Host "Close this window to shut down the orchestrator script."
