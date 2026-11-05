@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
echo Dong backend truoc khi ap dung ban cap nhat.
set "PROJECT=%~1"
if defined PROJECT goto project_ready
if exist "%~dp0backend\app\direct_import\store.py" set "PROJECT=%~dp0."
if defined PROJECT goto project_ready
if exist "%~dp0..\backend\app\direct_import\store.py" set "PROJECT=%~dp0.."
if defined PROJECT goto project_ready
set /p "PROJECT=Nhap duong dan thu muc goc medical-ai-integrated, vi du D:\medical-ai-integrated: "
:project_ready
set "PROJECT=%PROJECT:"=%"
if not defined PROJECT goto missing_project
if not exist "%PROJECT%\backend\app\direct_import\store.py" goto missing_project
set "PATCH_PYTHON="
if exist "%PROJECT%\backend\venv\Scripts\python.exe" set "PATCH_PYTHON=%PROJECT%\backend\venv\Scripts\python.exe"
if exist "%PROJECT%\backend\.venv\Scripts\python.exe" set "PATCH_PYTHON=%PROJECT%\backend\.venv\Scripts\python.exe"
if defined PATCH_PYTHON goto venv_python
py -3 -c "import sys;sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto launcher_python
python -c "import sys;sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto system_python
echo [LOI] Can Python 3.10 tro len de ap dung patch. Du an su dung Python 3.12.
goto failed
:venv_python
"%PATCH_PYTHON%" "%~dp0update_code.py" apply --project "%PROJECT%\."
set "PATCH_RESULT=%ERRORLEVEL%"
goto checked
:launcher_python
py -3 "%~dp0update_code.py" apply --project "%PROJECT%\."
set "PATCH_RESULT=%ERRORLEVEL%"
goto checked
:system_python
python "%~dp0update_code.py" apply --project "%PROJECT%\."
set "PATCH_RESULT=%ERRORLEVEL%"
:checked
if not "%PATCH_RESULT%"=="0" goto failed
echo Cap nhat thanh cong. Khoi dong lai backend va thu lai cau hoi.
pause
exit /b 0
:missing_project
echo [LOI] Chon thu muc goc co backend\app\direct_import\store.py.
:failed
echo Tac vu chua hoan tat. Xem loi phia tren. Khong tu khoi dong ung dung.
pause
exit /b 1
