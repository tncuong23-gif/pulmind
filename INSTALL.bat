@echo off
setlocal DisableDelayedExpansion
call "%~dp0windows_quick\runner.bat" install
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [LOI] Tac vu that bai, ma loi %RESULT%. Xem thong bao phia tren.
pause
exit /b %RESULT%
