@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
echo Dong backend dang chay truoc khi test. Bo test tu mo backend chan doan cong 8111.
set "PROJECT=%~1"
if defined PROJECT goto found
if exist "%~dp0backend\app\main.py" set "PROJECT=%~dp0."
if defined PROJECT goto found
if exist "%~dp0..\backend\app\main.py" set "PROJECT=%~dp0.."
if defined PROJECT goto found
set /p "PROJECT=Nhap thu muc medical-ai-integrated co backend: "
:found
set "PROJECT=%PROJECT:"=%"
if not exist "%PROJECT%\backend\app\main.py" goto missing
if not exist "%~dp0test_queries.py" goto missing_helper
set "TEST_PYTHON="
if exist "%PROJECT%\backend\venv\Scripts\python.exe" set "TEST_PYTHON=%PROJECT%\backend\venv\Scripts\python.exe"
if exist "%PROJECT%\backend\.venv\Scripts\python.exe" set "TEST_PYTHON=%PROJECT%\backend\.venv\Scripts\python.exe"
if defined TEST_PYTHON goto run_venv
py -3 -c "import sys;sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto run_launcher
python -c "import sys;sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto run_python
echo [LOI] Khong tim thay Python. Can dung Python da cai thu vien backend.
goto failed
:run_venv
"%TEST_PYTHON%" "%~dp0test_queries.py" --project "%PROJECT%\." --quick
set "TEST_RESULT=%ERRORLEVEL%"
goto done
:run_launcher
py -3 "%~dp0test_queries.py" --project "%PROJECT%\." --quick
set "TEST_RESULT=%ERRORLEVEL%"
goto done
:run_python
python "%~dp0test_queries.py" --project "%PROJECT%\." --quick
set "TEST_RESULT=%ERRORLEVEL%"
:done
echo.
echo Xem dong SEND THIS ZIP phia tren. Gui ZIP log do cho tro ly.
echo Ma 2 nghia la phat hien loi hoac test gian doan; log van duoc luu.
pause
exit /b %TEST_RESULT%
:missing
echo [LOI] Khong tim thay backend\app\main.py. Chon dung thu muc du an.
goto failed
:missing_helper
echo [LOI] Thieu test_queries.py canh BAT. Hay giai nen va copy day du goi test.
:failed
pause
exit /b 1
