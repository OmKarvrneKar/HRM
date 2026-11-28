@echo off
title AI Samrat HRMS — Shutdown
cls
echo ============================================================
echo                 AI SAMRAT HRMS — SHUTDOWN
echo ============================================================
echo.

echo [INFO] Checking for active backend (5000) and frontend (5173) processes...
powershell -NoProfile -Command "foreach ($p in 5000, 5173) { $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($conns) { $conns | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }; Write-Host ('[SUCCESS] Stopped process listening on port ' + $p + '.') } else { Write-Host ('[INFO] No active server process found on port ' + $p + '.') } }"
echo.
pause
