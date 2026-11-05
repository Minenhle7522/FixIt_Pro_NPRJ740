@echo off
setlocal
cd /d "%~dp0"

echo ===============================================
echo FixIt Pro - NRPJ740 Windows Setup
echo ===============================================

echo Checking for Python 3.11...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3.11 was not found.
  echo Install Python 3.11 and make sure the Python Launcher is enabled.
  pause
  exit /b 1
)

if not exist "venv\Scripts\python.exe" (
  echo Creating Python 3.11 virtual environment...
  py -3.11 -m venv venv
  if errorlevel 1 goto :error
)

echo Installing dependencies...
"venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo Applying database migrations...
"venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto :error

echo Creating demo accounts...
"venv\Scripts\python.exe" setup.py
if errorlevel 1 goto :error

echo Running Django system checks...
"venv\Scripts\python.exe" manage.py check
if errorlevel 1 goto :error

echo.
echo Setup complete.
echo Start the application with:
echo   venv\Scripts\activate

echo   python manage.py runserver

echo Then open http://127.0.0.1:8000/
pause
exit /b 0

:error
echo.
echo Setup failed. Read the error above and fix the reported issue.
pause
exit /b 1
