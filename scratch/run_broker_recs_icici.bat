@echo off
setlocal
set ROOT=%~dp0..
set VENV_PY=%ROOT%\backend\venv\Scripts\python.exe
set LOGDIR=%ROOT%\scratch\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
echo ==== %date% %time% ==== >> "%LOGDIR%\broker_recs_icici.log"
"%VENV_PY%" "%ROOT%\scratch\auto_download_broker_recs_icici.py" >> "%LOGDIR%\broker_recs_icici.log" 2>&1
set RUN_EXIT=%ERRORLEVEL%
echo Exit code %RUN_EXIT% >> "%LOGDIR%\broker_recs_icici.log"
endlocal & exit /b %RUN_EXIT%
