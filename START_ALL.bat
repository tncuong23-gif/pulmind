@echo off
setlocal DisableDelayedExpansion
call "%~dp0windows_quick\start_all.bat"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
