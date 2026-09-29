@echo off
title YUKTI
cd /d "%~dp0"

echo.
echo  ============================================
echo   YUKTI - Starting...
echo  ============================================
echo.

:: Start backend in a new window
echo  [1/2] Starting Backend (port 8000)...
start "Backend - Digital Twin" cmd /k "cd /d %~dp0 && python -m uvicorn backend.app.main:app --port 8000"

:: Wait 5 seconds for backend to initialize
timeout /t 5 /nobreak >nul

:: Start frontend in a new window
echo  [2/2] Starting Frontend (port 5173)...
start "Frontend - Digital Twin" cmd /k "cd /d %~dp0\frontend && npm run dev"

:: Wait 4 more seconds then open browser
timeout /t 4 /nobreak >nul

echo.
echo  [3/3] Opening browser...
start http://localhost:5173

echo.
echo  ============================================
echo   Both servers are starting!
echo   Backend  -> http://localhost:8000
echo   Frontend -> http://localhost:5173
echo   API Docs -> http://localhost:8000/docs
echo  ============================================
echo.
echo  Close the Backend and Frontend windows to stop.
echo.
pause
