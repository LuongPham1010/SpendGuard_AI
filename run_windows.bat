@echo off
rem SpendGuard AI one-click launcher for Windows.
rem First run: creates a private Python environment and installs the dependencies (a few minutes).
rem The environment lives at a short path (%USERPROFILE%\.spendguard\venv) because some packages nest deeply
rem and Windows limits paths to 260 characters. Set SG_VENV to put it elsewhere.
rem Later runs: start straight away. Needs Python 3.10 or newer: https://www.python.org/downloads/
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
  echo During setup, tick "Add python.exe to PATH". Then run this file again.
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul
rem pip does not read .env: take the proxy settings from it so installs work on a corporate network
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
  if /i "%%A"=="HTTP_PROXY" set "HTTP_PROXY=%%B"
  if /i "%%A"=="HTTPS_PROXY" set "HTTPS_PROXY=%%B"
  if /i "%%A"=="NO_PROXY" set "NO_PROXY=%%B"
)

if not defined SG_VENV set "SG_VENV=%USERPROFILE%\.spendguard\venv"
set "VPY=%SG_VENV%\Scripts\python.exe"

if not exist "%VPY%" (
  echo [1/3] Creating the Python environment...
  %PY% -m venv "%SG_VENV%"
  if errorlevel 1 goto :fail
)

rem A venv whose creation was interrupted can lack pip; add it before installing.
"%VPY%" -m pip --version >nul 2>nul
if errorlevel 1 (
  echo Adding pip to the Python environment...
  "%VPY%" -m ensurepip --upgrade --default-pip
  if errorlevel 1 goto :fail
)

if not exist "%SG_VENV%\installed.ok" (
  echo [2/3] Installing dependencies, first run only...
  "%VPY%" -m pip install --disable-pip-version-check --timeout 30 --retries 2 -q -r requirements.txt
  if errorlevel 1 goto :fail
  echo ok> "%SG_VENV%\installed.ok"
)

if not defined PORT set "PORT=8000"
set "RELOAD=0"
echo [3/3] Starting SpendGuard AI at http://127.0.0.1:%PORT%  (close this window to stop)
if not defined SG_NO_BROWSER start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:%PORT%"
"%VPY%" main.py
pause
exit /b 0

:fail
echo.
echo Setup failed. Check your internet connection and the message above, then run this file again.
echo On a company network, set HTTP_PROXY and HTTPS_PROXY in source\.env. Off that network, remove those lines.
pause
exit /b 1
