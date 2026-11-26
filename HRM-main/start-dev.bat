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

REM 2. Check and clean any lingering process on port 5000
echo [INFO] Ensuring port 5000 is free...
powershell -NoProfile -Command "$conns = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue; if ($conns) { $conns | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force; Write-Host ('[INFO] Released previously occupied port 5000 (PID ' + $_.OwningProcess + ')') } }"

REM 3. Ensure environment file exists
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Creating initial .env from .env.example...
        copy ".env.example" ".env" >nul
    )
)

REM 4. Display startup diagnostics
echo [INFO] Starting AI Samrat HRMS application server...
echo [INFO] Server URL:    http://localhost:5000
echo [INFO] Login Portal:  http://localhost:5000/login
echo [INFO] Health Check:  http://localhost:5000/api/health
echo.
echo ============================================================
echo   LOCAL DEVELOPMENT ACCESS:
echo   1. Dev Test Employee: EMP-TEST-999 / test.employee@aisamrat.com
echo      - Click "Access Test Employee Dashboard" on the login page
echo      - Fully isolated QA sandbox (attendance, breaks, leaves, tasks)
echo   2. Team Lead:  lead.kavita@aisamrat.com     / Lead@Kavita2026!
echo   3. Manager:    admin@aisamrat.com           / Admin@Samrat2026!
echo   4. HR:         ramya.hr@aisamrat.com        / Hr@Ramya2026!
echo                  (aliases: hr.ramya@aisamrat.com, hr.priya@aisamrat.com)
echo.
echo   * Real employees activate accounts with Gmail OTP at:
echo     http://localhost:5000/activate
echo   * Development Mode: Disabled by default in .env for safety.
echo ============================================================
echo.
echo Press Ctrl+C in this window to stop the server at any time.
echo.

REM 5. Open browser automatically after 2 seconds
start "" http://localhost:5000/login

REM 6. Run the application
python app.py
if errorlevel 1 (
    echo.
    echo [ERROR] Server terminated with an error. Please inspect the log above.
    pause
)
