@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 goto failed
if not exist "windows_quick\runner.bat" goto missing
if not exist "windows_quick\core-installed.flag" goto install
if not exist "frontend\node_modules\.bin\vite.cmd" goto install
if exist "backend\.venv\Scripts\python.exe" goto launch
if exist "backend\venv\Scripts\python.exe" goto launch
:install
call "windows_quick\runner.bat" install
if errorlevel 1 goto failedpop
:launch
call "windows_quick\start_all.bat"
if errorlevel 1 goto failedpop
popd
exit /b 0
:missing
echo Thieu windows_quick. Hay giai nen TOAN BO ZIP truoc khi chay.
:failedpop
popd
:failed
echo [LOI] Chua khoi dong thanh cong. Xem thong bao phia tren.
pause
exit /b 1
