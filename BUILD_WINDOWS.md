# Building Windows Executable for v3.0

## Requirements:
1. Windows 10/11
2. Python 3.6+ installed
3. Internet connection

## Steps:

### 1. Install Python Dependencies
```cmd
pip install pyserial pyinstaller
```

### 2. Build the Executable
```cmd
python build_release.py
```

### 3. Output Files
The build will create:
- `releases/v3.0.0/pos-diagnostic-toolkit-v3.0.0.exe`
- `releases/v3.0.0/README.txt`
- `releases/v3.0.0/Run-Toolkit.bat`
- `releases/v3.0.0/CHANGELOG.txt`

## Alternative: Manual Build
```cmd
pyinstaller --onefile --console --name=pos-diagnostic-toolkit-v3.0.0 --clean src/main_enhanced.py
```

## Features Included in v3.0.0:
- Sequential COM port testing
- USB device scanning
- Device auto-detection
- Parallel network testing
- Configuration management
- Enhanced logging
- Full system diagnostics

