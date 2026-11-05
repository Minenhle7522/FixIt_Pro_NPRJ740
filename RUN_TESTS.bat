@echo off
setlocal
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Virtual environment not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
"venv\Scripts\python.exe" manage.py check
if errorlevel 1 goto :error
"venv\Scripts\python.exe" manage.py makemigrations --check --dry-run
if errorlevel 1 goto :error
"venv\Scripts\python.exe" manage.py test
if errorlevel 1 goto :error
echo.
echo ALL AUTOMATED CHECKS PASSED.
pause
exit /b 0
:error
echo.
echo TESTING FAILED. Review the error output above.
pause
exit /b 1
