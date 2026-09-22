@echo off
title Swing Trading - Stop
echo Stopping the Swing Trading backend and frontend...

taskkill /FI "WINDOWTITLE eq Swing Trading - Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Swing Trading - Frontend*" /T /F >nul 2>&1

echo Done. If a "Backend" or "Frontend" window is still open, you can
echo just close it by hand as well.
pause
