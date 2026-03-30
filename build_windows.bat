@echo off
echo ========================================
echo  POS Diagnostic Toolkit v3.0 - Windows Builder
echo ========================================
echo.
echo This script will build the Windows executable for v3.0.0
echo.
echo Requirements:
echo   1. Python 3.6 or later installed
echo   2. Internet connection for downloading packages
echo   3. Administrator privileges (recommended)
echo.
echo Press Ctrl+C to cancel or any key to continue...
pause > nul

echo.
echo Step 1: Checking Python installation...
python --version > nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python from https://python.org
    echo Then add Python to your PATH and try again.
    pause
    exit /b 1
)

python --version
echo ✓ Python found

echo.
echo Step 2: Installing required packages...
echo Installing pyserial...
pip install pyserial --quiet
if errorlevel 1 (
    echo ERROR: Failed to install pyserial
    echo Try: pip install pyserial
    pause
    exit /b 1
)
echo ✓ pyserial installed

echo Installing pyinstaller...
pip install pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: Failed to install pyinstaller
    echo Try: pip install pyinstaller
    pause
    exit /b 1
)
echo ✓ pyinstaller installed

echo.
echo Step 3: Building executable...
echo This may take a few minutes...
python build_release.py
if errorlevel 1 (
    echo ERROR: Build failed!
    echo Check the error messages above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  BUILD COMPLETE!
echo ========================================
echo.
echo The following files have been created:
echo   releases\v3.0.0\pos-diagnostic-toolkit-v3.0.0.exe
echo   releases\v3.0.0\README.txt
echo   releases\v3.0.0\Run-Toolkit.bat
echo   releases\v3.0.0\CHANGELOG.txt
echo.
echo To run the toolkit:
echo   1. Navigate to releases\v3.0.0\
echo   2. Double-click Run-Toolkit.bat
echo   3. Or run pos-diagnostic-toolkit-v3.0.0.exe directly
echo.
echo Features included in v3.0.0:
echo   • Sequential COM port testing
echo   • USB device scanning
echo   • Device auto-detection
echo   • Parallel network testing
echo   • Configuration management
echo   • Enhanced logging for tickets
echo   • Full system diagnostics
echo.
echo Press any key to exit...
pause > nul