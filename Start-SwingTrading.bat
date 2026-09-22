@echo off
title Swing Trading - Launcher
cd /d "%~dp0"

echo Starting the backend (server + database)...
start "Swing Trading - Backend (leave this open)" cmd /k "cd /d "%~dp0backend" && venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"

echo Starting the frontend (the app itself)...
start "Swing Trading - Frontend (leave this open)" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --port 5173 --strictPort"

echo.
echo Waiting a few seconds for both to start...
timeout /t 8 /nobreak >nul

echo Opening the app in your browser...
start "" "http://localhost:5173/"

echo.
echo ============================================================
echo  Two new windows opened: "Backend" and "Frontend".
echo  Leave BOTH of them open while you use the app.
echo  If the browser page did not load, wait a few more seconds
echo  and refresh it, or check those two windows for an error.
echo.
echo  To stop the app later, close those two windows, or run
echo  Stop-SwingTrading.bat.
echo ============================================================
echo.
echo You can close this window now.
pause
