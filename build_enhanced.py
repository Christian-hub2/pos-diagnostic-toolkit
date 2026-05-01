#!/usr/bin/env python3
"""
Build script for POS Diagnostic Toolkit v3.0
Creates standalone executable for Windows
"""

import os
import sys
import shutil
from datetime import datetime

# PyInstaller configuration
APP_NAME = "pos-diagnostic-toolkit"
VERSION = "3.1"
AUTHOR = "Christian J. Sanchez Avila"

# Files to include
MAIN_FILE = "src/main_enhanced.py"
ICON_FILE = None  # Optional: "assets/icon.ico"

# Additional data files (folders to include)
DATA_FILES = [
    ("configs", "configs"),
    ("logs", "logs"),
]

def clean_build():
    """Remove previous build artifacts"""
    print("[*] Cleaning previous builds...")
    folders = ["build", "dist"]
    for folder in folders:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"  [-] Removed {folder}/")

def create_directories():
    """Create necessary directories"""
    print("[*] Creating directories...")
    for folder in ["configs", "logs"]:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"  [+] Created {folder}/")

def build_exe():
    """Build the executable using PyInstaller"""
    print("[*] Building executable...")
    
    # Base PyInstaller command
    cmd = [
        "pyinstaller",
        "--onefile",  # Single executable
        "--console",  # Console application
        f"--name={APP_NAME}-v{VERSION}",
        "--clean",
        "--noconfirm",
    ]
    
    # Add icon if available
    if ICON_FILE and os.path.exists(ICON_FILE):
        cmd.append(f"--icon={ICON_FILE}")
    
    # Add version info
    cmd.extend([
        f"--version-file=version_info.txt",
    ])
    
    # Add hidden imports if needed
    hidden_imports = [
        "serial",
        "serial.tools.list_ports",
        "queue",
        "json",
        "datetime",
    ]
    
    for imp in hidden_imports:
        cmd.append(f"--hidden-import={imp}")
    
    # Add main file
    cmd.append(MAIN_FILE)
    
    print(f"  [*] Command: {' '.join(cmd)}")
    
    # Run PyInstaller
    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("[+] Build successful!")
        
        # Check output
        exe_path = os.path.join("dist", f"{APP_NAME}-v{VERSION}.exe")
        if os.path.exists(exe_path):
            size = os.path.getsize(exe_path) / (1024 * 1024)  # MB
            print(f"  [+] Executable: {exe_path}")
            print(f"  [+] Size: {size:.2f} MB")
        else:
            print("  [!] Executable not found in expected location")
            
        # Copy additional files to dist folder
        print("[*] Copying support files...")
        for src, dst in DATA_FILES:
            src_path = src
            dst_path = os.path.join("dist", dst)
            if os.path.exists(src_path):
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dst_path)
                print(f"  [+] Copied {src} -> {dst_path}")
    else:
        print("[!] Build failed!")
        print(f"  [!] Error: {result.stderr}")
        sys.exit(1)

def create_version_info():
    """Create version info file for Windows executable"""
    print("[*] Creating version info...")
    
    version_info = f"""# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({VERSION.replace('.', ', ')}, 0),
    prodvers=({VERSION.replace('.', ', ')}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{AUTHOR}'),
        StringStruct(u'FileDescription', u'POS Diagnostic Toolkit - Field Tech Utility'),
        StringStruct(u'FileVersion', u'{VERSION}'),
        StringStruct(u'InternalName', u'{APP_NAME}'),
        StringStruct(u'LegalCopyright', u'Copyright © {datetime.now().year} {AUTHOR}'),
        StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
        StringStruct(u'ProductName', u'POS Diagnostic Toolkit'),
        StringStruct(u'ProductVersion', u'{VERSION}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [0x409, 0x4B0])])
  ]
)
"""
    
    with open("version_info.txt", "w") as f:
        f.write(version_info)
    
    print("  [+] Created version_info.txt")

def create_readme():
    """Create README for the built application"""
    print("[*] Creating README...")
    
    readme = f"""# POS Diagnostic Toolkit v{VERSION}

## What's New in v3.0

### Major Improvements:
1. **Sequential Port Testing** - Test all COM ports at once with detailed results
2. **USB Device Scanning** - Detect and list USB devices (Windows/Linux/Mac)
3. **Parallel Network Tests** - Test multiple network endpoints simultaneously
4. **Device Auto-Detection** - Automatically identifies device type from port description
5. **Enhanced Logging** - Comprehensive logs with timestamps and results
6. **Configuration Management** - Save/load store-specific test configurations
7. **Full System Diagnostics** - Complete system check in one command

### Device Support:
- Verifone pin pads
- Ingenico terminals  
- Epson printers
- Zebra/Symbol scanners
- Scales (Mettler Toledo, etc.)
- Cash drawers
- Generic serial devices

## Usage

Run the executable: `pos-diagnostic-toolkit-v{VERSION}.exe`

### Key Features:

1. **List All Serial/USB Ports** - Detailed port information
2. **Test Serial Ports (Sequential)** - Test all ports automatically
3. **Test Single Serial Port** - Manual testing with device detection
4. **Scan USB Devices** - List all connected USB hardware
5. **Parallel Network Tests** - Test common POS services simultaneously
6. **Full System Diagnostics** - Comprehensive system check

## Log Files

All results are saved to: `logs/pos-diag-YYYY-MM-DD.log`

Perfect for copying into SMS Loc/CRC Dispatch ticket remarks.

## Requirements

- Windows 7/8/10/11 (built as .exe)
- Python 3.6+ (for source version)
- pyserial library

## Building from Source

```bash
pip install pyserial pyinstaller
python build_enhanced.py
```

## Author

{AUTHOR} - POS Field Technician
"""
    
    with open("dist/README.txt", "w") as f:
        f.write(readme)
    
    print("  [+] Created README.txt in dist/")

def main():
    """Main build process"""
    print("=" * 60)
    print(f"POS Diagnostic Toolkit v{VERSION} - Build Script")
    print("=" * 60)
    
    # Check for PyInstaller
    try:
        import PyInstaller
        print("[+] PyInstaller found")
    except ImportError:
        print("[!] PyInstaller not installed. Install with: pip install pyinstaller")
        sys.exit(1)
    
    # Check for pyserial
    try:
        import serial
        print("[+] pyserial found")
    except ImportError:
        print("[!] pyserial not installed. Install with: pip install pyserial")
        sys.exit(1)
    
    # Run build steps
    clean_build()
    create_directories()
    create_version_info()
    build_exe()
    create_readme()
    print(f"[+] Note: Vendor ID file at src/data/vendor_ids.json is packaged alongside")
    print(f"[+] To add new USB devices, edit that file and rebuild.")
    
    print("\n" + "=" * 60)
    print("[+] Build completed successfully!")
    print(f"[+] Output in: dist/")
    print("[+] Files created:")
    print(f"    - pos-diagnostic-toolkit-v{VERSION}.exe")
    print("    - configs/ (directory)")
    print("    - logs/ (directory)")
    print("    - README.txt")
    print("=" * 60)

if __name__ == "__main__":
    main()
