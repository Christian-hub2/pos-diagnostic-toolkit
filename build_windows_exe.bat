@echo off
REM =============================================
REM Build POS Diagnostic Toolkit Windows Executable
REM Double-click this file on a Windows machine
REM with Python installed.
REM =============================================

echo.
echo === POS Diagnostic Toolkit - Windows Build ===
echo.
echo Checking Python...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed!
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

python --version

echo.
echo Installing dependencies...
pip install pyinstaller pyserial

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Building executable...
python build_enhanced.py

if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Executable built successfully!
    echo Check the dist\ folder for the .exe file.
) else (
    echo [ERROR] Build failed.
)

echo.
pause
