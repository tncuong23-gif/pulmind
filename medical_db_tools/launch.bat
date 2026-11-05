@echo off
setlocal DisableDelayedExpansion
set "DB_SCRIPT=%~dp0manage.py"
set "DB_MODE=%~1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if exist "%~dp0..\backend\.venv\Scripts\python.exe" (
  "%~dp0..\backend\.venv\Scripts\python.exe" -u "%DB_SCRIPT%" "%DB_MODE%"
  exit /b
)
if exist "%~dp0..\backend\venv\Scripts\python.exe" (
  "%~dp0..\backend\venv\Scripts\python.exe" -u "%DB_SCRIPT%" "%DB_MODE%"
  exit /b
)
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Can Python 3.12. Hay cai Python nhu bo chay du an yeu cau.
  exit /b 1
)
py -3.12 -u "%DB_SCRIPT%" "%DB_MODE%"
exit /b %ERRORLEVEL%
