@echo off
title AI Samrat HRMS — Shutdown
cls
echo ============================================================
echo                 AI SAMRAT HRMS — SHUTDOWN
echo ============================================================
echo.

echo [INFO] Checking for active server process on port 5000...
powershell -NoProfile -Command "$conns = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue; if ($conns) { $conns | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }; Write-Host '[SUCCESS] Stopped process listening on port 5000.' } else { Write-Host '[INFO] No active server process found on port 5000.' }"
echo.
pause
