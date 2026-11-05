@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0.."
if errorlevel 1 exit /b 1
set "ROOT=%CD%"
call "windows_quick\runner.bat" start
if errorlevel 1 goto failed
if not exist "backend\.venv-clinical\Scripts\python.exe" goto noclinical
start "Medical AI - Clinical IE" "%ComSpec%" /d /c ""%ROOT%\START_CLINICAL.bat""
if errorlevel 1 goto failed
goto voice
:noclinical
echo Clinical IE chua cai. Dung INSTALL_CLINICAL.bat khi can phan tich TXT/anh.
:voice
if not exist "backend\.venv-vieneu\Scripts\python.exe" goto novoice
start "Medical AI - Voice" "%ComSpec%" /d /c ""%ROOT%\START_VOICE.bat""
if errorlevel 1 goto failed
goto done
:novoice
echo VieNeu chua cai. Dung INSTALL_VOICE.bat khi can giong noi.
:done
echo CSDL va Ollama can dang chay theo .env. Cac cua so dich vu hien loi neu co.
popd
exit /b 0
:failed
popd
exit /b 1
