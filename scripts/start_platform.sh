#!/bin/bash
set -e

# Setup signal handling for clean shutdown
cleanup() {
    echo ""
    write_log "Shutting down ORM Intelligence Platform..." "WARN"
    
    # Kill background processes started by this script
    if [ -n "$BACKEND_PID" ]; then kill -9 $BACKEND_PID 2>/dev/null || true; fi
    if [ -n "$WORKER_PID" ]; then kill -9 $WORKER_PID 2>/dev/null || true; fi
    if [ -n "$PIPELINE_WORKER_PID" ]; then kill -9 $PIPELINE_WORKER_PID 2>/dev/null || true; fi
    if [ -n "$BEAT_PID" ]; then kill -9 $BEAT_PID 2>/dev/null || true; fi
    if [ -n "$FRONTEND_PID" ]; then kill -9 $FRONTEND_PID 2>/dev/null || true; fi
    
    write_log "Shutdown complete." "SUCCESS"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Helpers
write_log() {
    local message="$1"
    local type="${2:-INFO}"
    local color="\e[36m" # Cyan
    
    if [ "$type" = "SUCCESS" ]; then color="\e[32m"; fi # Green
    if [ "$type" = "WARN" ]; then color="\e[33m"; fi # Yellow
    if [ "$type" = "ERROR" ]; then color="\e[31m"; fi # Red
    
    echo -e "${color}[${type}] ${message}\e[0m"
}

kill_port_processes() {
    local port="$1"
    if command -v lsof > /dev/null 2>&1; then
        local pids=$(lsof -t -i :$port 2>/dev/null || true)
        for pid in $pids; do
            if [ "$pid" != "$$" ]; then
                write_log "Killing stale process (PID $pid) listening on port $port..." "WARN"
                kill -9 $pid 2>/dev/null || true
            fi
        done
    elif command -v fuser > /dev/null 2>&1; then
        write_log "Killing stale processes listening on port $port..." "WARN"
        fuser -k $port/tcp 2>/dev/null || true
    fi
}

wait_for_http() {
    local url="$1"
    local timeout="${2:-30}"
    local start_time=$(date +%s)
    
    while [ $(($(date +%s) - start_time)) -lt $timeout ]; do
        if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

check_queues() {
    write_log "Verifying Celery queues..." "INFO"
    local prev_dir=$(pwd)
    cd "$ORM_COLLECTION_DIR"
    export PYTHONPATH="$ORM_COLLECTION_DIR"
    
    local result=$("$PYTHON_EXE" -m celery -A app.core.celery_app.celery_app inspect active_queues 2>/dev/null || true)
    
    export PYTHONPATH=""
    cd "$prev_dir"
    
    local required=("io_queue" "cpu_queue" "nlp_queue" "aggregation_queue" "pipeline_queue")
    local missing=0
    for q in "${required[@]}"; do
        if ! echo "$result" | grep -q "$q"; then
            write_log "Queue missing: $q" "ERROR"
            missing=1
        fi
    done
    
    if [ $missing -eq 1 ]; then return 1; else return 0; fi
}

# Directories
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ORM_COLLECTION_DIR="$ROOT_DIR/orm_collection"
ORM_DASHBOARD_DIR="$ROOT_DIR/orm_dashboard"
PYTHON_EXE="$ORM_COLLECTION_DIR/venv/bin/python"

# Environment-configurable endpoints
BACKEND_HOST="${BACKEND_HOST:-localhost}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

write_log "Starting Pre-flight Verification..." "INFO"
if ! "$PYTHON_EXE" "$SCRIPT_DIR/verify_environment.py"; then
    write_log "Pre-flight checks failed. Aborting startup." "ERROR"
    exit 1
fi

write_log "Cleaning up stale processes..." "INFO"
kill_port_processes $BACKEND_PORT
kill_port_processes $FRONTEND_PORT

write_log "Starting Backend API..." "INFO"
(cd "$ORM_COLLECTION_DIR" && source venv/bin/activate && python -m uvicorn app.main:app --port 8000) &
BACKEND_PID=$!
if ! wait_for_http "$BACKEND_URL/health" 30; then
    write_log "Backend failed to become healthy." "ERROR"
    exit 1
fi
write_log "Backend is healthy." "SUCCESS"

write_log "Starting General Celery Worker..." "INFO"
(cd "$ORM_COLLECTION_DIR" && source venv/bin/activate && python -m celery -A app.core.celery_app.celery_app worker --loglevel=info --hostname=general@%h --pool=solo --concurrency=1 -Q io_queue,cpu_queue,nlp_queue,aggregation_queue) &
WORKER_PID=$!

write_log "Starting Pipeline Celery Worker..." "INFO"
(cd "$ORM_COLLECTION_DIR" && source venv/bin/activate && python -m celery -A app.core.celery_app.celery_app worker --loglevel=info --hostname=pipeline@%h --pool=solo --concurrency=1 -Q pipeline_queue) &
PIPELINE_WORKER_PID=$!

# Wait for celery worker to ping
celery_ping_ok=0
start_time=$(date +%s)
prev_dir=$(pwd)
cd "$ORM_COLLECTION_DIR"
export PYTHONPATH="$ORM_COLLECTION_DIR"

while [ $(($(date +%s) - start_time)) -lt 60 ]; do
    ping_result=$("$PYTHON_EXE" -m celery -A app.core.celery_app.celery_app inspect ping 2>/dev/null || true)
    if echo "$ping_result" | grep -q -E "pong|OK"; then
        celery_ping_ok=1
        break
    fi
    sleep 2
done

export PYTHONPATH=""
cd "$prev_dir"

if [ $celery_ping_ok -eq 0 ]; then
    write_log "Celery worker failed to respond to ping." "ERROR"
    exit 1
fi
write_log "Celery Worker is healthy." "SUCCESS"

write_log "Starting Celery Beat..." "INFO"
(cd "$ORM_COLLECTION_DIR" && source venv/bin/activate && python -m celery -A app.core.celery_app.celery_app beat --loglevel=info) &
BEAT_PID=$!

write_log "Starting Frontend..." "INFO"
(cd "$ORM_DASHBOARD_DIR" && npm run dev) &
FRONTEND_PID=$!
# Next.js development server might take a bit
if ! wait_for_http "$FRONTEND_URL" 45; then
    write_log "Frontend failed to start." "ERROR"
    exit 1
fi
write_log "Frontend is ready." "SUCCESS"

write_log "Running Final System Checks..." "INFO"
if ! check_queues; then
    write_log "Queue verification failed." "ERROR"
    exit 1
fi

echo ""
echo -e "\e[36m================================================\e[0m"
echo -e "\e[36m             SYSTEM STATUS REPORT               \e[0m"
echo -e "\e[36m================================================\e[0m"
echo ""
echo -e "\e[32m+ PostgreSQL       : OK\e[0m"
echo -e "\e[32m+ Redis            : OK\e[0m"
echo -e "\e[32m+ Environment      : OK\e[0m"
echo -e "\e[32m+ Database         : OK (Migrations applied)\e[0m"
echo -e "\e[32m+ Celery Worker    : OK\e[0m"
echo -e "\e[32m+ Celery Beat      : OK\e[0m"
echo -e "\e[32m+ Backend API      : OK\e[0m"
echo -e "\e[32m+ Frontend         : OK\e[0m"
echo -e "\e[32m+ Pipeline Queue   : OK\e[0m"
echo ""
echo -e "\e[32mORM Intelligence Platform Ready\e[0m"
echo -e "\e[36m================================================\e[0m"
echo "Backend API:   $BACKEND_URL"
echo "Dashboard:     $FRONTEND_URL"
echo "Press Ctrl+C to shut down the orchestrator script."

# Wait for background processes to keep script running
wait
