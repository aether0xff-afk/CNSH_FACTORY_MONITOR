@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
set "PYTHON_EXE=%~dp0.conda\python.exe"
if not exist "%PYTHON_EXE%" (
    echo Factory Monitor Conda environment not found. Run setup_windows.ps1 first.
    exit /b 1
)
"%PYTHON_EXE%" "%~dp0app.py" >> "%~dp0logs\server.log" 2>&1
if errorlevel 1 (
    echo Factory Monitor stopped with an error. Check logs\server.log.
    exit /b 1
)
