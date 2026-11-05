@echo off
setlocal
cd /d "%~dp0"
python "%~dp0backup_models_and_data.py" --dry-run
if errorlevel 1 exit /b %errorlevel%
echo.
echo Da xem truoc danh sach. Neu an toan, nhan phim bat ky de tao ZIP...
pause >nul
python "%~dp0backup_models_and_data.py"
pause
