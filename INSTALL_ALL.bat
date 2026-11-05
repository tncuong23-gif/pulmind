@echo off
setlocal DisableDelayedExpansion
call "%~dp0windows_quick\runner.bat" install
if errorlevel 1 goto failed
call "%~dp0windows_quick\runner.bat" install-clinical
set "CLINICAL_RESULT=%ERRORLEVEL%"
if "%CLINICAL_RESULT%"=="2" goto modelwarning
if not "%CLINICAL_RESULT%"=="0" goto failed
goto voice
:modelwarning
echo [CANH BAO] Clinical IE con thieu/sai model. Tiep tuc cai thu vien giong noi.
:voice
call "%~dp0windows_quick\runner.bat" install-voice
if errorlevel 1 goto failed
if "%CLINICAL_RESULT%"=="2" goto incomplete
echo Da cai cac thu vien. Chay RUN.bat. CSDL/Ollama va cau hinh phai san sang.
pause
exit /b 0
:incomplete
echo Da cai thu vien, NHUNG Clinical IE chua du model. Xem huong dan Clinical.
pause
exit /b 2
:failed
echo [LOI] Cai dat dung tai buoc bi loi. Xem thong bao phia tren.
pause
exit /b 1
