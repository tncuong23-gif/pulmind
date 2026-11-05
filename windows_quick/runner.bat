@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0.."
if errorlevel 1 exit /b 1
set "ROOT=%CD%"
if not exist "backend\requirements.txt" goto wrongfolder
if not exist "frontend\package.json" goto wrongfolder
if "%~1"=="install" goto install
if "%~1"=="install-start" goto install
if "%~1"=="start" goto start
if "%~1"=="backend" goto backend
if "%~1"=="frontend" goto frontend
if "%~1"=="install-clinical" goto installclinical
if "%~1"=="clinical" goto clinical
if "%~1"=="install-voice" goto installvoice
if "%~1"=="voice" goto voice
goto fail

:install
if exist "windows_quick\core-installed.flag" del "windows_quick\core-installed.flag"
call :node
if errorlevel 1 goto fail
call :python
if errorlevel 2 goto fail
if not errorlevel 1 goto pythonready
echo Dang tao backend\.venv bang Python 3.12...
py -3.12 -m venv "backend\.venv"
if errorlevel 1 goto needpython
call :python
if errorlevel 1 goto fail
:pythonready
if not exist "logs" mkdir "logs"
if not exist "logs" goto fail
echo [1/3] Cai thu vien backend. Co the mat nhieu phut.
echo Nhat ky: %ROOT%\logs\install-backend.log
"%PYTHON_EXE%" -m pip install -r "backend\requirements.txt" >"logs\install-backend.log" 2>&1
if errorlevel 1 goto pipfailed
"%PYTHON_EXE%" -m pip check >>"logs\install-backend.log" 2>&1
if errorlevel 1 goto pipfailed
echo [2/3] Cai thu vien frontend...
pushd "frontend"
if exist "package-lock.json" (call npm ci >"%ROOT%\logs\install-frontend.log" 2>&1) else (call npm install >"%ROOT%\logs\install-frontend.log" 2>&1)
set "NPM_RESULT=%ERRORLEVEL%"
popd
if not "%NPM_RESULT%"=="0" goto npmfailed
echo [3/3] Kiem tra cau hinh...
if not exist "backend\.env" goto missingenv
>"windows_quick\core-installed.flag" echo installed
echo [OK] Da cai thu vien backend va frontend.
echo Clinical IE va giong noi: dung cac file INSTALL rieng neu can.
echo CSDL va Ollama phai dang chay theo backend\.env.
if "%~1"=="install-start" goto start
goto success

:start
call :python
if errorlevel 1 goto notinstalled
call :node
if errorlevel 1 goto fail
if not exist "frontend\node_modules\.bin\vite.cmd" goto notinstalled
if not exist "backend\.env" goto missingenv
start "Medical AI - Backend" "%ComSpec%" /d /c ""%ROOT%\START_BACKEND.bat""
if errorlevel 1 goto fail
start "Medical AI - Frontend" "%ComSpec%" /d /c ""%ROOT%\START_FRONTEND.bat""
if errorlevel 1 goto fail
echo Da mo hai cua so khoi dong; day chua phai xac nhan dich vu san sang.
echo Cho backend bao Application startup complete va Vite hien dia chi Local.
echo Sau do mo http://127.0.0.1:5173 trong trinh duyet.
echo Dung Ctrl+C trong tung cua so de dung. Khong chay START nhieu lan.
echo Can Clinical IE hoac TTS: bam START_CLINICAL.bat / START_VOICE.bat.
goto success

:backend
call :python
if errorlevel 1 goto notinstalled
if not exist "backend\.env" goto missingenv
cd /d "%ROOT%\backend"
"%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --workers 1
if errorlevel 1 goto fail
goto success

:frontend
call :node
if errorlevel 1 goto fail
if not exist "frontend\node_modules\.bin\vite.cmd" goto notinstalled
cd /d "%ROOT%\frontend"
call npm run dev -- --host 127.0.0.1 --port 5173 --strictPort --open
if errorlevel 1 goto fail
goto success

:installclinical
if not exist "backend\install_clinical_windows.bat" goto missingmodule
call "backend\install_clinical_windows.bat"
set "MODULE_RESULT=%ERRORLEVEL%"
if "%MODULE_RESULT%"=="2" goto clinicalassets
if not "%MODULE_RESULT%"=="0" goto fail
goto success

:clinical
if not exist "backend\start_clinical_windows.bat" goto missingmodule
call "backend\start_clinical_windows.bat"
if errorlevel 1 goto fail
goto success

:installvoice
call :python
if errorlevel 1 goto notinstalled
if not exist "backend\requirements-voice.txt" goto missingmodule
"%PYTHON_EXE%" -m pip install -r "backend\requirements-voice.txt"
if errorlevel 1 goto fail
"%PYTHON_EXE%" -m pip check
if errorlevel 1 goto fail
if not exist "backend\setup_vieneu_windows.bat" goto missingmodule
call "backend\setup_vieneu_windows.bat"
if errorlevel 1 goto fail
echo Xem VOICE_VIENEU_GUIDE_VI.md de cau hinh STT/TTS trong .env.
goto success

:voice
if not exist "backend\start_vieneu_windows.bat" goto missingmodule
call "backend\start_vieneu_windows.bat"
if errorlevel 1 goto fail
goto success

:python
set "PYTHON_EXE="
if exist "%ROOT%\backend\.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%\backend\.venv\Scripts\python.exe"
if defined PYTHON_EXE goto validatepython
if exist "%ROOT%\backend\venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%\backend\venv\Scripts\python.exe"
if not defined PYTHON_EXE exit /b 1
:validatepython
"%PYTHON_EXE%" -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,12) else 1)" >nul 2>&1
if errorlevel 1 (
 echo Moi truong Python hien co khong chay duoc hoac khong phai 3.11/3.12.
 echo Hay doi ten thu muc venv cu de giu ban sao, roi chay lai INSTALL.
 exit /b 2
)
exit /b 0

:node
where node >nul 2>&1
if errorlevel 1 goto neednode
where npm >nul 2>&1
if errorlevel 1 goto neednode
node -e "const v=process.versions.node.split('.').map(Number);process.exit(v[0]>=22?0:1)"
if errorlevel 1 goto neednode
exit /b 0
:neednode
echo Can cai Node.js 22 hoac moi hon, gom npm, sau do mo lai file BAT.
echo Trinh cai dat: https://nodejs.org/
exit /b 1

:needpython
echo Can Python 3.12 va Python Launcher - tuy chon py trong trinh cai dat.
echo Trinh cai dat: https://www.python.org/downloads/windows/
goto fail
:notinstalled
echo Chua du moi truong. Hay chay INSTALL.bat truoc.
goto fail
:missingenv
echo Khong tim thay backend\.env. Ban ZIP goc co tep nay, hay khoi phuc cau hinh cua ban.
echo Script khong tao cau hinh CSDL/mat khau gia.
goto fail
:wrongfolder
echo Chep cac file BAT va thu muc windows_quick vao cung cap voi backend va frontend.
goto fail
:missingmodule
echo Thieu script hoac requirements cua module. Kiem tra lai ban du an day du.
goto fail
:pipfailed
type "logs\install-backend.log"
goto fail
:npmfailed
type "logs\install-frontend.log"
goto fail
:clinicalassets
echo Clinical IE bao thieu hoac sai checksum model. Khong phai cai dat hoan tat.
echo Xem CLINICAL_MULTIMODAL_UPDATE_VI.md va bo sung trong so dung phien ban.
popd
exit /b 2
:fail
popd
exit /b 1
:success
popd
exit /b 0
