@echo off
rem People Sight - run locally on Windows: finds Python 3.11+, installs requirements, builds the database if missing,
rem builds the frontend if missing (needs Node), then serves http://localhost:8000
setlocal
cd /d "%~dp0"
rem Show output live and keep a copy in run_local.log (for troubleshooting)
if /i not "%~1"=="--logged" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "& cmd /c '""%~f0"" --logged' 2>&1 | Tee-Object -FilePath 'run_local.log'"
  pause
  exit /b
)
set "PY="
echo Looking for Python 3.11 or newer ...
call :try "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
call :try "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
call :try "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
call :try "%LOCALAPPDATA%\Programs\Thonny\python.exe"
call :try "%USERPROFILE%\miniconda3\python.exe"
call :try "%USERPROFILE%\anaconda3\python.exe"
if not defined PY for /f "delims=" %%E in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do call :try "%%E"
if not defined PY for /f "delims=" %%E in ('python -c "import sys; print(sys.executable)" 2^>nul') do call :try "%%E"
if not defined PY ( echo Python 3.11 or newer was not found. Install it from python.org and run this file again. & pause & exit /b 1 )
echo Using Python: %PY%
"%PY%" -m pip install --disable-pip-version-check -q -r backend\requirements.txt || ( echo Package install failed. & pause & exit /b 1 )
if not exist data\people.duckdb (
  echo Building the database from data\raw ...
  "%PY%" pipeline\02_clean_enps.py && "%PY%" pipeline\03_clean_recruitment.py && "%PY%" pipeline\04_build_db.py || ( pause & exit /b 1 )
)
if not exist frontend\dist\index.html (
  echo Building the frontend ...
  pushd frontend
  call npm ci
  call npm run build
  popd
)
echo.
echo People Sight is running at http://localhost:8000  (close this window to stop it)
start "" cmd /c "timeout /t 5 >/dev/null & start http://localhost:8000/sentiment"
"%PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
exit /b 0

:try
if defined PY exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>nul
if errorlevel 1 ( echo   skipped %~1 ^(older than 3.11^) & exit /b 0 )
set "PY=%~1"
exit /b 0
