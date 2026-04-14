@echo off
title Invoice System — Starting...
color 0A

echo.
echo  ================================================
echo   INVOICE PROCESSING SYSTEM
echo   Multi-Agent System - SPADE + XMPP + Ollama
echo  ================================================
echo.

REM === Step 1: Check Docker is running ===
echo [1/5] Checking Docker...
docker info >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)
echo  Docker OK

REM === Step 2: Start ejabberd ===
echo [2/5] Starting ejabberd...
docker compose up -d
timeout /t 5 /nobreak >nul
echo  ejabberd OK

REM === Step 3: Register XMPP accounts ===
echo [3/5] Registering agent accounts...
for %%A in (ingestion_agent validation_agent decision_agent communication_agent audit_agent orchestrator api_gateway) do (
    docker compose exec ejabberd ejabberdctl register %%A localhost invoice123 >nul 2>&1
)
echo  Accounts OK (already existing accounts are skipped automatically)

REM === Step 4: Start agents in a new terminal ===
echo [4/5] Starting SPADE agents...
start "Invoice Agents" cmd /k ".venv\Scripts\python.exe main.py"
timeout /t 4 /nobreak >nul
echo  Agents starting...

REM === Step 5: Start FastAPI in a new terminal ===
echo [5/5] Starting web dashboard...
start "Invoice Dashboard" cmd /k ".venv\Scripts\uvicorn.exe api.main:app --port 8000"
timeout /t 3 /nobreak >nul
echo  Dashboard starting...

echo.
echo  ================================================
echo   All systems starting!
echo   Open your browser at: http://127.0.0.1:8000
echo  ================================================
echo.
echo  (Ollama should already be running in background)
echo  (If not, run: ollama serve)
echo.

REM === Open browser automatically ===
timeout /t 3 /nobreak >nul
start http://127.0.0.1:8000

echo  Press any key to stop everything...
pause >nul

REM === Shutdown ===
echo.
echo  Stopping services...
docker compose down
echo  Done. Goodbye!
pause