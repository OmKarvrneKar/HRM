@echo off
title AI Samrat HRMS — Local Development Server
cls
echo ============================================================
echo                    AI SAMRAT HRMS
echo       Enterprise Human Resource Management System
echo ============================================================
echo.

REM 1. Verify Python availability
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.11+ is required but was not found in your PATH.
    echo Please install Python and ensure "Add Python to PATH" is checked.
    echo.
    pause
    exit /b 1
)

REM 2. Check and clean any lingering processes on ports 5000 and 5173
echo [INFO] Ensuring ports 5000 and 5173 are free...
powershell -NoProfile -Command "foreach ($p in 5000, 5173) { $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($conns) { $conns | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force; Write-Host ('[INFO] Released previously occupied port ' + $p + ' (PID ' + $_.OwningProcess + ')') } } }"

REM 3. Ensure environment file exists
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Creating initial .env from .env.example...
        copy ".env.example" ".env" >nul
    )
)

REM 4. Display startup diagnostics
echo [INFO] Starting AI Samrat HRMS backend & React frontend...
echo [INFO] Backend API:    http://127.0.0.1:5000
echo [INFO] Built SPA URL:  http://127.0.0.1:5000/login
echo [INFO] React Dev URL:  http://localhost:5173/login (if Node/npm present)
echo [INFO] Health Check:   http://127.0.0.1:5000/api/health
echo.
echo Press Ctrl+C in the server windows to stop, or run stop-dev.bat.
echo.

REM 5. Start React Vite Dev Server (port 5173) if npm is available and open browser
where npm >nul 2>&1
if not errorlevel 1 (
    if exist "..\frontend\package.json" (
        echo [INFO] Launching React Vite Dev Server in a new window...
        start "AI Samrat HRMS — Frontend (Vite :5173)" /D "%~dp0..\frontend" cmd /k "npm run dev"
        start "" http://localhost:5173/login
        goto :run_flask
    )
)

start "" http://127.0.0.1:5000/login

:run_flask
REM 6. Run the Flask Backend Server (port 5000)
python app.py
if errorlevel 1 (
    echo.
    echo [ERROR] Server terminated with an error. Please inspect the log above.
    pause
)
