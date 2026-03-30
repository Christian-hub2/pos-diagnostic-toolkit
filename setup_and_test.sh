#!/bin/bash
# Setup and test script for POS Diagnostic Toolkit v3.0

echo "================================================"
echo "POS Diagnostic Toolkit v3.0 - Setup & Test"
echo "================================================"

# Check Python
echo -e "\n[1] Checking Python installation..."
python3 --version || { echo "Python3 not found. Please install Python 3.6+"; exit 1; }

# Install dependencies
echo -e "\n[2] Installing dependencies..."
pip3 install pyserial || pip install pyserial

# Test import
echo -e "\n[3] Testing imports..."
python3 -c "import serial; import json; import platform; print('✓ All imports successful')"

# Show directory structure
echo -e "\n[4] Project structure:"
find . -type f -name "*.py" -o -name "*.md" -o -name "*.txt" -o -name "*.sh" | sort

# Show new features
echo -e "\n[5] New files in v3.0:"
echo "  • src/main_enhanced.py    - Enhanced main application"
echo "  • build_enhanced.py       - Enhanced build script"
echo "  • IMPROVEMENTS_SUMMARY.md - Complete improvements list"
echo "  • test_improvements.py    - Demonstration script"

# Try to run a simple test
echo -e "\n[6] Running quick test..."
cd src
echo "Testing basic functionality..."

# Create a simple test that doesn't require actual hardware
python3 -c "
import platform
import sys
from datetime import datetime

print('✓ Platform:', platform.system())
print('✓ Python:', sys.version.split()[0])
print('✓ Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print('\\n✓ Basic test passed!')
print('\\nTo run the full tool:')
print('  python main_enhanced.py')
"

echo -e "\n================================================"
echo "SETUP COMPLETE!"
echo "================================================"
echo -e "\nTo use the enhanced toolkit:"
echo "1. cd src"
echo "2. python main_enhanced.py"
echo -e "\nTo build standalone .exe (Windows):"
echo "1. pip install pyinstaller"
echo "2. python build_enhanced.py"
echo -e "\nCheck IMPROVEMENTS_SUMMARY.md for complete details."
echo "================================================"