# POS Diagnostic Toolkit v2.0 — Field Tech Edition

A lightweight, portable utility for troubleshooting Point-of-Sale systems in the field.
Runs as a single `.exe` — no installation required on store computers.

## Features

- **Serial Port Lister** — detect all RS-232/COM devices connected to the machine
- **Device-Aware Serial Test** — sends correct test command per device (Verifone, Ingenico, Epson, Generic)
- **Cross-Platform Ping** — works on Windows, Linux, and macOS
- **TCP Port Tester** — with quick presets for common POS endpoints:
  - Verifone VHQ (443)
  - Epson Printer (9100)
  - Payment Host (8443)
- **System Network Info** — full IP, gateway, DNS display
- **Timestamped Session Logging** — every action saved to `logs/pos-diag-YYYY-MM-DD.log`

## Requirements

```
pyserial
pyinstaller  (for building .exe)
```

Install dependencies:
```bash
pip install pyserial pyinstaller
```

## Usage

```bash
cd src
python main.py
```

## Build Standalone EXE (Windows)

```bash
python build_exe.py
```

Output: `dist/pos-diagnostic-toolkit.exe`

## Log Files

All diagnostic results are automatically saved to:
```
logs/pos-diag-YYYY-MM-DD.log
```

Useful for SMS Loc documentation — copy/paste log entries directly into your ticket notes.

## Author

Christian J. Sanchez Avila — POS Field Technician
