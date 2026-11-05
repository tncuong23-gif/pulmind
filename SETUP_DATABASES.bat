@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
echo Bo CSDL: Neo4j, MongoDB, Qdrant. Ollama Windows duoc quan ly rieng.
if not exist "%~dp0medical_db_tools\launch.bat" (
  echo Thieu medical_db_tools. Hay giai nen toan bo goi vao thu muc du an.
  pause
  exit /b 1
)
call "%~dp0medical_db_tools\launch.bat" setup
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Chua hoan tat. Xem thong bao loi phia tren.
pause
exit /b %RESULT%
