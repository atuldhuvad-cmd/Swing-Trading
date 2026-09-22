@echo off
setlocal
set ROOT=%~dp0..
set VENV_PY=%ROOT%\backend\venv\Scripts\python.exe
set LOGDIR=%ROOT%\scratch\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
echo ==== %date% %time% ==== >> "%LOGDIR%\fundamentals.log"
"%VENV_PY%" "%ROOT%\scratch\auto_download_fundamentals.py" >> "%LOGDIR%\fundamentals.log" 2>&1
set RUN_EXIT=%ERRORLEVEL%
echo Exit code %RUN_EXIT% >> "%LOGDIR%\fundamentals.log"
endlocal & exit /b %RUN_EXIT%
