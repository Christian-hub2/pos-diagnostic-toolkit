#!/usr/bin/env python3
"""
POS Diagnostic Toolkit v3.1 — Enhanced Field Technician Edition
Author: Christian J. Sanchez Avila
Company: AM PM Services

Fixes in v3.1:
  - Fixed full_diagnostics() — picks one serial mode (simultaneous), not both
  - USB PowerShell query retry + timeout + fallback to WMIC
  - Store-specific network endpoints via config
  - OPOS/JavaPOS service object checks (Windows registry)
  - Vendor ID database externalized to vendor_ids.json
  - Admin/elevation check at startup
  - Structured ticket output (clean copy-paste block)
  - Quick Test from Config in menu
"""

import os
import sys
import json
import time
import socket
import platform
import threading
import subprocess
import datetime
import inspect
from pathlib import Path

# ─────────────────────────────────────────────
# SERIAL AVAILABILITY
# ─────────────────────────────────────────────

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


# ─────────────────────────────────────────────
# FILE PATHS (resolved relative to this script)
# ─────────────────────────────────────────────

SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = SCRIPT_DIR.parent
LOG_DIR = PROJECT_DIR / "logs"
CONFIG_DIR = PROJECT_DIR / "configs"
DATA_DIR = SCRIPT_DIR / "data"

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# VERSION
# ─────────────────────────────────────────────

VERSION = "3.1.0"
APP_NAME = "POS Diagnostic Toolkit"


# ─────────────────────────────────────────────
# DEVICE DETECTION PATTERNS (hardcoded baseline)
# ─────────────────────────────────────────────

DEVICE_PATTERNS = {
    "verifone":   {"keywords": ["verifone", "vx", "mx9"],  "test_cmd": b"STATUS\r\n"},
    "ingenico":   {"keywords": ["ingenico", "ipp", "isc"], "test_cmd": b"STATUS\r\n"},
    "epson":      {"keywords": ["epson", "tm-", "receipt"], "test_cmd": bytes([0x1B, 0x40])},
    "zebra":      {"keywords": ["zebra", "symbol", "ls"],  "test_cmd": bytes([0x05])},
    "scale":      {"keywords": ["scale", "mettler", "toledo"], "test_cmd": b"W\r\n"},
    "cashdrawer": {"keywords": ["cash", "drawer", "apd"],   "test_cmd": bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])},
}

# ─────────────────────────────────────────────
# VENDOR ID DATABASE — loaded from external file
# ─────────────────────────────────────────────

def _load_vendor_db() -> dict:
    """
    Load USB vendor ID database from external file.
    Ships with built-in defaults; users can add new VID entries without recompiling.
    """
    fallback = {
        "04b8": ("Epson",        "Printer/Scanner"),
        "0525": ("Verifone",     "Pin Pad"),
        "0b00": ("Ingenico",     "Pin Pad/Terminal"),
        "05e0": ("Symbol/Zebra", "Scanner"),
        "0a5f": ("Zebra",        "Scanner/Printer"),
        "1fc9": ("NCR",          "POS Device"),
        "0403": ("FTDI",         "USB-Serial Adapter"),
        "067b": ("Prolific",     "USB-Serial Adapter"),
        "10c4": ("Silicon Labs", "USB-Serial Adapter"),
        "1a86": ("CH340",        "USB-Serial Adapter"),
        "0557": ("ATEN",         "USB-Serial/KVM"),
        "045e": ("Microsoft",    "HID/Keyboard/Mouse"),
        "046d": ("Logitech",     "HID/Keyboard/Mouse"),
        "0458": ("KYE/Genius",   "HID Device"),
        "05ac": ("Apple",        "HID/Hub"),
        "0424": ("Microchip",    "USB Hub"),
        "2341": ("Arduino",      "USB-Serial"),
        "0451": ("Texas Instrs", "USB Hub"),
        "1d6b": ("Linux",        "USB Hub/Virtual"),
    }
    vendor_file = DATA_DIR / "vendor_ids.json"
    if vendor_file.is_file():
        try:
            with open(vendor_file) as f:
                user_data = json.load(f)
            fallback.update(user_data)
        except (json.JSONDecodeError, OSError):
            pass
    return fallback

USB_DEVICE_SIGNATURES = _load_vendor_db()


# ─────────────────────────────────────────────
# DEFAULT NETWORK ENDPOINTS
# ─────────────────────────────────────────────

DEFAULT_NETWORK_ENDPOINTS = [
    ("8.8.8.8",     53,  "Google DNS"),
    ("192.168.1.1",  80,  "Default Gateway"),
]

# Known POS utility paths for detection
POS_UTILITY_PATHS = {
    "123Scan": [
        r"C:\Program Files (x86)\Zebra Technologies\123Scan\123Scan.exe",
        r"C:\Program Files\Zebra Technologies\123Scan\123Scan.exe",
        r"C:\Program Files (x86)\Motorola\123Scan\123Scan.exe",
        r"C:\Program Files\Motorola\123Scan\123Scan.exe",
    ],
    "OPOS Sample App": [
        r"C:\Program Files (x86)\Zebra Technologies\OPOS\Sample Application\ScannerOPOSTest.exe",
        r"C:\Program Files\Zebra Technologies\OPOS\Sample Application\ScannerOPOSTest.exe",
        r"C:\Program Files (x86)\Zebra Technologies\OPOS\Sample Application\ScaleOPOSTest.exe",
        r"C:\Program Files\Zebra Technologies\OPOS\Sample Application\ScaleOPOSTest.exe",
    ],
    "SMS Store Manager": [
        r"C:\Program Files (x86)\SMS\StoreMan\storeman.exe",
        r"C:\Program Files\SMS\StoreMan\storeman.exe",
        r"C:\storeman\storeman.exe",
    ],
}

STORE_CONFIG_REQUIRED_FIELDS = {
    "store_name": str,
    "store_address": str,
    "endpoints": list,
    "notes": str,
}


# ─────────────────────────────────────────────
# LOGGER
# ─────────────────────────────────────────────

class Logger:
    """File + console logger. Also captures structured ticket output."""

    def __init__(self):
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.log_file = LOG_DIR / f"pos-diag-{today}.log"
        self._buf = []
        self._structured_entries = []
        self._store_name = None
        self._troubleshooting_notes = []

    def set_store(self, name: str):
        self._store_name = name

    def write(self, text: str):
        print(text)
        self._buf.append(text)
        with open(self.log_file, "a") as f:
            f.write(text + "\n")

    def section(self, title: str):
        line = "=" * 60
        self.write(f"\n{line}")
        self.write(f"  {title}")
        self.write(line)

    def result(self, label: str, status: str, detail: str = ""):
        icon = "[OK]" if status.upper() in ("OK", "OPEN", "FOUND", "PASS") else "[FAIL]"
        msg = f"  {icon} {label:<35} {status}"
        if detail:
            msg += f" — {detail}"
        self.write(msg)
        self._structured_entries.append({
            "label": label, "status": status, "detail": detail,
            "timestamp": datetime.datetime.now().isoformat()
        })

    def add_troubleshooting_note(self, note: str):
        """Add a note that goes into the ticket remarks section."""
        self._troubleshooting_notes.append(note)
        self.write(f"  [*] Note: {note}")

    def get_ticket_remarks(self) -> str:
        """
        Generate a clean, structured ticket remark block.
        Ready to copy-paste into AM PM work order system.
        """
        now = datetime.datetime.now()
        lines = []
        lines.append("=" * 60)
        lines.append("  TICKET REMARKS — Copy below into work order")
        lines.append("=" * 60)
        lines.append(f"  Date: {now.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"  Tech: Christian Sanchez")
        if self._store_name:
            lines.append(f"  Store: {self._store_name}")
        lines.append(f"  Tool: {APP_NAME} v{VERSION}")
        lines.append("")

        if self._structured_entries:
            lines.append("  Results:")
            for e in self._structured_entries:
                icon = "[OK]" if e["status"].upper() in ("OK", "OPEN", "FOUND", "PASS") else "[FAIL]"
                lines.append(f"    {icon} {e['label']}: {e['status']}")
                if e["detail"]:
                    lines.append(f"      - {e['detail']}")

        if self._troubleshooting_notes:
            lines.append("")
            lines.append("  Troubleshooting Notes:")
            for note in self._troubleshooting_notes:
                lines.append(f"    • {note}")

        lines.append("")
        lines.append(f"  Log file: {self.log_file}")
        lines.append("=" * 60)
        return "\n".join(lines)

    def print_ticket_block(self):
        """Print the structured ticket block to console."""
        print("\n" + self.get_ticket_remarks())


log = Logger()


# ─────────────────────────────────────────────
# ADMIN / ELEVATION CHECK
# ─────────────────────────────────────────────

def is_admin() -> bool:
    """Check if the process has admin/root privileges."""
    if platform.system() == "Windows":
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def _relaunch_as_admin_windows():
    """Auto-relaunch with admin privileges on Windows."""
    try:
        import ctypes
        args = ' '.join(f'"{a}"' for a in sys.argv)
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
        if ret > 32:
            print("  [*] Relaunching as administrator...")
            sys.exit(0)
        else:
            print("  [!] Admin elevation cancelled.")
            return False
    except Exception:
        return False
    return True


def check_elevation():
    """Check admin status. On Windows .exe, offer auto-relaunch."""
    if is_admin():
        log.write("  * Running with admin privileges")
        return

    log.write("  ! WARNING: Not running as administrator")
    log.write("  Some features (serial ports, USB scanning) may not work.")

    if platform.system() == "Windows":
        log.write("")
        log.write("  [A] Auto-relaunch as Administrator")
        log.write("  [S] Skip - continue with limited functionality")
        confirm = input("  Choice: ").strip().upper()
        if confirm == "A":
            _relaunch_as_admin_windows()
            return
        log.write("  Continuing without admin privileges.")

    log.add_troubleshooting_note(
        "Ran without admin elevation. Some USB/serial operations may have limited results."
    )


# ─────────────────────────────────────────────
# ELEVATION-AWARE TOOL RUNNER
# ─────────────────────────────────────────────

def run_system_command(cmd: list, timeout: int = 15) -> str:
    """
    Run a system command with timeout and error handling.
    Returns stdout string or empty on failure.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        )
        return result.stdout or ""
    except subprocess.TimeoutExpired:
        log.add_troubleshooting_note(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        return ""
    except Exception as e:
        log.write(f"  [!] Command failed: {e}")
        return ""


# ─────────────────────────────────────────────
# SERIAL PORT TESTING
# ─────────────────────────────────────────────

def detect_device_type(port_description: str) -> str:
    desc_lower = port_description.lower()
    for device, info in DEVICE_PATTERNS.items():
        if any(kw in desc_lower for kw in info["keywords"]):
            return device
    return "generic"


def test_single_port(port_name: str, baud: int = 9600, timeout: float = 2.0) -> dict:
    result = {
        "port": port_name,
        "status": "FAIL",
        "device": "unknown",
        "response": "",
        "error": "",
    }
    if not SERIAL_AVAILABLE:
        result["error"] = "pyserial not installed"
        return result

    try:
        with serial.Serial(port_name, baud, timeout=timeout) as ser:
            result["status"] = "OPEN"
            ports = {p.device: p for p in serial.tools.list_ports.comports()}
            desc = ports.get(port_name, None)
            desc_str = desc.description if desc else ""
            device_type = detect_device_type(desc_str)
            result["device"] = device_type
            cmd = DEVICE_PATTERNS.get(device_type, {}).get("test_cmd", b"TEST\r\n")
            ser.write(cmd)
            time.sleep(0.5)
            if ser.in_waiting:
                raw = ser.read(64)
                result["response"] = raw.hex()
                result["status"] = "OK"
    except serial.SerialException as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Unexpected: {e}"
    return result


def test_all_ports_simultaneous():
    """
    Test ALL serial/COM ports simultaneously using threads.
    This is the primary scan mode — fast, non-blocking for the user.
    """
    log.section("SERIAL PORT SCAN (Simultaneous — All at Once)")

    if not SERIAL_AVAILABLE:
        log.write("  [!] pyserial not available — skipping serial tests")
        return []

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        log.write("  [!] No serial/COM ports detected")
        return []

    log.write(f"  Found {len(ports)} port(s). Testing all simultaneously...\n")

    results = {}
    lock = threading.Lock()

    def worker(port):
        res = test_single_port(port.device)
        with lock:
            results[port.device] = res

    threads = []
    start_time = time.time()
    for port in ports:
        t = threading.Thread(target=worker, args=(port,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10)

    elapsed = time.time() - start_time
    log.write(f"  All ports tested in {elapsed:.1f}s\n")

    accessible = 0
    for port in ports:
        res = results.get(port.device, {"status": "TIMEOUT", "device": "?", "error": "timeout", "response": ""})
        if res["status"] in ("OK", "OPEN"):
            accessible += 1
        log.result(
            port.device,
            res["status"],
            f"{res['device']} | {res['error'] or res['response'] or 'no response'}"
        )
        if res["error"] and "Access denied" in res.get("error", ""):
            log.add_troubleshooting_note(f"{port.device} — access denied. Try running as admin.")

    log.write(f"\n  Summary: {accessible}/{len(ports)} ports accessible | Time: {elapsed:.1f}s")
    return list(results.values())


# ─────────────────────────────────────────────
# USB DEVICE SCANNING
# ─────────────────────────────────────────────

def _classify_usb_device(vid: str, desc: str) -> str:
    vid_lower = vid.lower()
    match = USB_DEVICE_SIGNATURES.get(vid_lower)
    if match:
        return f"{match[0]} — {match[1]}"
    desc_lower = desc.lower()
    if any(k in desc_lower for k in ["epson", "receipt", "printer"]):
        return "Printer"
    if any(k in desc_lower for k in ["verifone", "ingenico", "pinpad", "pin pad"]):
        return "Pin Pad"
    if any(k in desc_lower for k in ["zebra", "symbol", "scanner", "barcode"]):
        return "Scanner"
    if any(k in desc_lower for k in ["serial", "com port", "ftdi", "ch340", "prolific"]):
        return "USB-Serial Adapter"
    if any(k in desc_lower for k in ["hub"]):
        return "USB Hub"
    if any(k in desc_lower for k in ["keyboard", "mouse", "hid"]):
        return "HID Device"
    return "Unknown Device"


def scan_usb_devices_windows_powershell() -> str:
    """
    Get USB device list via PowerShell, with retry logic.
    Returns raw text output.
    """
    ps_script = """
    Get-PnpDevice -PresentOnly |
        Where-Object { $_.InstanceId -like 'USB*' } |
        Select-Object Status, Class, FriendlyName, DeviceID |
        ConvertTo-Json -Compress
    """
    for attempt in range(2):
        out = run_system_command(
            ["powershell", "-NoProfile", "-Command", ps_script],
            timeout=20
        )
        if out.strip():
            return out
        if attempt == 0:
            log.write("  [!] PowerShell query incomplete, retrying once...")
            time.sleep(1)
    return ""


def scan_usb_devices_windows_wmic() -> str:
    """Fallback: use WMIC to list USB devices."""
    log.write("  [*] Falling back to WMIC...")
    out = run_system_command(
        ["wmic", "path", "Win32_USBControllerDevice", "get", "/format:list"],
        timeout=15
    )
    return out


def scan_usb_devices():
    log.section("USB DEVICE SCAN")

    os_name = platform.system()
    log.write(f"  Platform: {os_name}\n")

    try:
        if os_name == "Windows":
            raw = scan_usb_devices_windows_powershell()
            if not raw.strip():
                log.write("  [!] PowerShell method returned nothing")
                raw = scan_usb_devices_windows_wmic()
            if raw.strip():
                log.write("  Connected USB Devices:")
                # Try parsing as JSON (PowerShell array output)
                devices = []
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        devices = parsed
                    elif isinstance(parsed, dict):
                        devices = [parsed]
                except json.JSONDecodeError:
                    # Not valid JSON — just dump raw output
                    for line in raw.strip().splitlines():
                        if line.strip():
                            log.write(f"    {line.strip()}")
                    return

                for dev in devices:
                    fn = dev.get("FriendlyName", "") or dev.get("friendlyName", "") or ""
                    status = dev.get("Status", "") or dev.get("status", "") or ""
                    dev_id = dev.get("DeviceID", "") or dev.get("deviceID", "") or ""
                    cls = dev.get("Class", "") or dev.get("class", "") or ""
                    # Extract VID from DeviceID
                    vid = ""
                    if "VID_" in dev_id.upper():
                        parts = dev_id.upper().split("VID_")
                        if len(parts) > 1:
                            vid = parts[1][:4].lower()
                    if not vid and fn:
                        # Fallback to description keywords
                        pass
                    device_type = _classify_usb_device(vid, fn)
                    log.write(f"    • {fn or 'Unknown Device'}")
                    log.write(f"      Status: {status or 'Unknown'} | Class: {cls or 'N/A'} | Type: {device_type}")

        elif os_name == "Linux":
            raw = run_system_command(["lsusb"], timeout=10)
            if raw.strip():
                log.write("  Connected USB Devices:")
                for line in raw.strip().splitlines():
                    if line.strip():
                        log.write(f"    {line.strip()}")

        elif os_name == "Darwin":
            raw = run_system_command(["system_profiler", "SPUSBDataType"], timeout=15)
            if raw.strip():
                log.write("  Connected USB Devices:")
                for line in raw.strip().splitlines():
                    if line.strip():
                        log.write(f"    {line.strip()}")

        else:
            log.write(f"  [!] Unsupported platform: {os_name}")

    except Exception as e:
        log.write(f"  [!] USB scan error: {e}")
        log.add_troubleshooting_note(f"USB scan failed: {e}")


def test_usb_connections():
    """
    Test USB device connections using platform-specific techniques.
    On Windows, uses PowerShell to get USB device status.
    """
    log.section("USB CONNECTION TEST")

    os_name = platform.system()
    log.write(f"  Platform: {os_name}\n")
    batch = 0
    errors = 0

    try:
        if os_name == "Windows":
            raw = scan_usb_devices_windows_powershell()
            if not raw.strip():
                raw = scan_usb_devices_windows_wmic()

            if not raw.strip():
                log.write("  [!] Could not retrieve USB device info")
                return

            devices = []
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    devices = parsed
                elif isinstance(parsed, dict):
                    devices = [parsed]
            except json.JSONDecodeError:
                log.write("  Could not parse device list (raw output below):")
                for line in raw.strip().splitlines():
                    if line.strip():
                        log.write(f"    {line.strip()}")
                return

            for dev in devices:
                batch += 1
                fn = dev.get("FriendlyName", "") or ""
                status = dev.get("Status", "") or ""
                dev_id = dev.get("DeviceID", "") or ""

                is_ok = status.lower() == "ok"
                if is_ok:
                    log.result(fn or f"Device #{batch}", "OK")
                else:
                    errors += 1
                    log.result(fn or f"Device #{batch}", status.upper() or "UNKNOWN", dev_id)

            total = len(devices)
            log.write(f"\n  Summary: {total - errors}/{total} devices OK")
            if errors:
                log.add_troubleshooting_note(f"{errors} USB device(s) with non-OK status")

        elif os_name == "Linux":
            raw = run_system_command(["lsusb", "-v"], timeout=10)
            if raw.strip():
                for line in raw.strip().splitlines():
                    if "Bus" in line and "Device" in line:
                        batch += 1
                        log.write(f"  • {line.strip()}")
            log.write(f"\n  Summary: {batch} USB device(s) detected")

        elif os_name == "Darwin":
            raw = run_system_command(["system_profiler", "SPUSBDataType"], timeout=15)
            if raw.strip():
                for line in raw.strip().splitlines():
                    st = line.strip()
                    if st and not st.startswith(" ") and ":" in st:
                        batch += 1
                        log.write(f"  • {st}")
            log.write(f"\n  Summary: {batch} USB device(s) detected")

        else:
            log.write(f"  [!] Unsupported platform: {os_name}")

    except Exception as e:
        log.write(f"  [!] USB connection test error: {e}")
        log.add_troubleshooting_note(f"USB connection test error: {e}")


# ─────────────────────────────────────────────
# POS UTILITY DETECTION (123Scan, OPOS Tools, SMS)
# ─────────────────────────────────────────────

def find_pos_utilities() -> dict:
    """Scan standard install paths for known POS utilities."""
    found = {}
    if platform.system() != "Windows":
        for name in POS_UTILITY_PATHS:
            found[name] = None
        return found

    for name, paths in POS_UTILITY_PATHS.items():
        for path in paths:
            if os.path.isfile(path):
                found[name] = path
                break
        else:
            found[name] = None
    return found


def check_pos_utilities():
    """Check for and report installed POS utilities."""
    log.section("POS UTILITY CHECK (123Scan, OPOS Tools, SMS)")
    found = find_pos_utilities()
    any_found = False
    for name, path in found.items():
        if path:
            any_found = True
            log.result(name, "INSTALLED", path)
        else:
            log.write(f"  - {name}: Not found")

    if not any_found and platform.system() == "Windows":
        log.add_troubleshooting_note(
            "No POS utilities (123Scan, OPOS tools) detected on this machine. "
            "These are essential for device configuration."
        )
        log.write("")
        log.write("  123Scan: https://www.zebra.com/us/en/support-downloads/software/123scan.html")
        log.write("  OPOS: Installed from manufacturer driver package or Zebra website")

    return found


def launch_123scan():
    """Launch 123Scan if installed."""
    log.section("LAUNCH 123SCAN")
    found = find_pos_utilities()
    path = found.get("123Scan")
    if path:
        log.write(f"  Starting 123Scan from: {path}")
        try:
            subprocess.Popen([path], shell=True)
            log.write("  123Scan launched in a separate window.")
        except Exception as e:
            log.write(f"  [!] Failed to launch: {e}")
    else:
        log.write("  123Scan is not installed on this machine.")
        log.write("  You can download it from: https://www.zebra.com/us/en/support-downloads/software/123scan.html")
        log.add_troubleshooting_note("123Scan not installed - needed for scanner/scale configuration.")


# ─────────────────────────────────────────────
# NETWORK TESTING
# ─────────────────────────────────────────────

def _test_tcp_endpoint(ip: str, port: int, label: str, results: dict, lock: threading.Lock):
    """Test a single TCP endpoint and store the result."""
    try:
        start = time.time()
        sock = socket.create_connection((ip, port), timeout=3)
        elapsed = int((time.time() - start) * 1000)
        sock.close()
        status = f"OPEN ({elapsed}ms)"
    except Exception:
        status = "CLOSED"

    with lock:
        results[(ip, port)] = (label, status)


def test_network_parallel(endpoints: list = None):
    """
    Test all network endpoints in parallel.
    Accepts optional store-specific endpoints from config.
    Defaults to DNS + gateway if no config provided.
    """
    if endpoints is None:
        endpoints = DEFAULT_NETWORK_ENDPOINTS

    log.section(f"NETWORK TEST (Parallel — {len(endpoints)} endpoints)")

    results = {}
    lock = threading.Lock()

    threads = []
    for ip, port, label in endpoints:
        t = threading.Thread(target=_test_tcp_endpoint, args=(ip, port, label, results, lock))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=5)

    open_count = 0
    for (ip, port), (label, status) in sorted(results.items()):
        is_open = status.startswith("OPEN")
        if is_open:
            open_count += 1
        log.result(label, status, f"{ip}:{port}")

    log.write(f"\n  Summary: {open_count}/{len(endpoints)} endpoints reachable")
    if open_count < len(endpoints):
        log.add_troubleshooting_note(f"{len(endpoints) - open_count} endpoint(s) unreachable — check network connectivity")


def ping_host(host: str, count: int = 2) -> str:
    """Ping a host and return result string."""
    system = platform.system().lower()
    flag = "-n" if system == "windows" else "-c"
    try:
        result = subprocess.run(
            ["ping", flag, str(count), host],
            capture_output=True, text=True,
            timeout=10
        )
        if "ttl=" in result.stdout.lower():
            return "Reachable"
        else:
            return f"FAIL — no response"
    except subprocess.TimeoutExpired:
        return "FAIL — timeout"
    except Exception as e:
        return f"FAIL — {e}"


# ─────────────────────────────────────────────
# OPOS / JavaPOS CHECKS (Windows-only)
# ─────────────────────────────────────────────

OPOS_REGISTRY_PATHS = [
    r"HKLM\SOFTWARE\WOW6432Node\OLEforRetail\OPOS",
    r"HKLM\SOFTWARE\OLEforRetail\OPOS",
]

OPOS_DEVICE_CATEGORIES = [
    "CashDrawer",
    "CheckScanner",
    "CoinDispenser",
    "FiscalPrinter",
    "Keylock",
    "LineDisplay",
    "MICR",
    "MSR",
    "PINPad",
    "POSKeyboard",
    "POSPrinter",
    "RemoteOrderDisplay",
    "Scanner",
    "SignatureCapture",
    "SmartCardRW",
    "ToneIndicator",
]

JAVAPOS_REGISTRY_PATHS = [
    r"HKLM\SOFTWARE\WOW6432Node\JavaPOS",
    r"HKLM\SOFTWARE\JavaPOS",
]


def check_opos_registry():
    """
    Check OPOS service object registrations via Windows registry.
    Essential for diagnosing OPOS error 107 (service not registered).
    """
    log.section("OPOS/JavaPOS SERVICE OBJECT CHECK (Windows)")

    if platform.system() != "Windows":
        log.write("  [!] OPOS is Windows-only — skipping")
        return

    found_any = False

    for reg_base in OPOS_REGISTRY_PATHS:
        for category in OPOS_DEVICE_CATEGORIES:
            key_path = f'{reg_base}\\{category}'
            cmd = ["reg", "query", key_path, "/s"]
            out = run_system_command(cmd, timeout=5)
            if out.strip():
                found_any = True
                log.write(f"  [OK] {category}:")
                for line in out.strip().splitlines():
                    stripped = line.strip()
                    if stripped and "SOFTWARE" in stripped and stripped.endswith(category):
                        # Header line — skip
                        continue
                    if stripped:
                        log.write(f"      {stripped}")

    if not found_any:
        log.write("  [!] No OPOS service objects found in Windows registry")
        log.add_troubleshooting_note(
            "No OPOS service objects registered. If SMS shows OPOS error 107, "
            "the service objects need to be installed/re-registered via OPOS config utility."
        )
        log.add_troubleshooting_note(
            "Try: re-run OPOS configuration, or install from manufacturer's OPOS driver package."
        )
    else:
        log.write("\n  [OK] OPOS service objects detected — service layer appears configured")

    # Also check JavaPOS
    for reg_base in JAVAPOS_REGISTRY_PATHS:
        cmd = ["reg", "query", reg_base, "/s"]
        out = run_system_command(cmd, timeout=5)
        if out.strip():
            log.write(f"\n  [OK] JavaPOS registry keys found at {reg_base}")
            log.write("  (JavaPOS control objects detected)")
            return

    log.write("\n  [!] No JavaPOS registry keys found")
    log.add_troubleshooting_note(
        "JavaPOS not detected in registry. If the store uses JavaPOS drivers, "
        "they may need reinstallation."
    )


def check_opos_specific_device(device_category: str, device_name: str = ""):
    """
    Check a specific OPOS device category and optionally a specific device name.
    Call from menu for targeted OPOS troubleshooting.
    """
    log.section(f"OPOS CHECK: {device_category}")

    if platform.system() != "Windows":
        log.write("  [!] OPOS is Windows-only")
        return

    found = False
    for reg_base in OPOS_REGISTRY_PATHS:
        key_path = f'{reg_base}\\{device_category}'
        cmd = ["reg", "query", key_path, "/s"]
        out = run_system_command(cmd, timeout=5)
        if out.strip():
            found = True
            log.write(f"  Found entries in {key_path}:")
            for line in out.strip().splitlines():
                stripped = line.strip()
                if stripped:
                    log.write(f"    {stripped}")

    if not found:
        log.write(f"  [!] No OPOS entries found for {device_category}")
        log.add_troubleshooting_note(
            f"OPOS category '{device_category}' has no registered service objects. "
            f"This will cause OPOS error 107."
        )


# ─────────────────────────────────────────────
# CONFIGURATION MANAGEMENT
# ─────────────────────────────────────────────

def validate_store_config(config: dict) -> list:
    """Validate a store config and return list of errors."""
    errors = []
    for field, expected_type in STORE_CONFIG_REQUIRED_FIELDS.items():
        if field not in config:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(config[field], expected_type):
            errors.append(f"Field '{field}' should be {expected_type.__name__}, got {type(config[field]).__name__}")
    if "endpoints" in config and isinstance(config["endpoints"], list):
        for i, ep in enumerate(config["endpoints"]):
            if not isinstance(ep, (list, tuple)) or len(ep) < 3:
                errors.append(f"endpoints[{i}] should be [ip, port, label]")
    return errors


def save_config():
    """Interactive: save current store configuration."""
    log.section("SAVE STORE CONFIGURATION")

    name = input("  Store name: ").strip()
    if not name:
        log.write("  [!] Cancelled — store name required")
        return

    address = input("  Store address: ").strip()

    print("  Enter custom network endpoints (IP, Port, Label)")
    print("  One per line. Empty line to finish.")
    print("  Example: 10.0.0.5 443 VHQ Server")
    endpoints = []
    while True:
        ep_raw = input("  Endpoint: ").strip()
        if not ep_raw:
            break
        parts = ep_raw.split()
        if len(parts) >= 3:
            try:
                ip, port_str, label = parts[0], parts[1], " ".join(parts[2:])
                endpoints.append((ip, int(port_str), label))
            except ValueError:
                log.write("  [!] Invalid port number, skipping")
        else:
            log.write("  [!] Expected: IP PORT LABEL, skipping")

    notes = input("  Notes (optional): ").strip()

    config = {
        "store_name": name,
        "store_address": address,
        "endpoints": endpoints,
        "notes": notes,
        "saved_at": datetime.datetime.now().isoformat(),
    }

    errors = validate_store_config(config)
    if errors:
        log.write("  Validation errors:")
        for err in errors:
            log.write(f"    [FAIL] {err}")
        return

    filepath = CONFIG_DIR / f"{name.replace(' ', '_').lower()}.json"
    with open(filepath, "w") as f:
        json.dump(config, f, indent=2)

    log.write(f"  [OK] Configuration saved to {filepath}")
    log.set_store(name)


def load_config_and_quick_test():
    """Load a store config and run targeted tests based on its endpoints."""
    log.section("QUICK TEST FROM CONFIG")

    configs = list(CONFIG_DIR.glob("*.json"))
    if not configs:
        log.write("  No saved configurations found.")
        log.write("  Use option 9 to save a config first.")
        return

    log.write("  Available store configs:")
    for i, c in enumerate(configs, 1):
        try:
            with open(c) as f:
                data = json.load(f)
            store_name = data.get("store_name", c.stem)
            log.write(f"  [{i}] {store_name}")
        except (json.JSONDecodeError, OSError):
            log.write(f"  [{i}] {c.stem} (broken file)")

    try:
        choice = int(input("\n  Select config: ").strip())
        if choice < 1 or choice > len(configs):
            log.write("  [!] Invalid selection")
            return
    except (ValueError, IndexError):
        log.write("  [!] Invalid selection")
        return

    try:
        with open(configs[choice - 1]) as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.write(f"  [!] Could not load config: {e}")
        return

    log.set_store(config.get("store_name", "Unknown"))
    log.section(f"QUICK TEST — {config.get('store_name', 'Unknown')}")

    # Run targeted tests
    endpoints = config.get("endpoints", [])
    if endpoints:
        test_network_parallel(endpoints)
    else:
        log.write("  No custom endpoints in config — skipping network test")

    # Always do serial + USB scan
    test_all_ports_simultaneous()
    scan_usb_devices()

    # Check OPOS if on Windows
    check_opos_registry()


def list_configs():
    """List saved store configurations with metadata."""
    log.section("SAVED CONFIGURATIONS")
    configs = list(CONFIG_DIR.glob("*.json"))
    if not configs:
        log.write("  No saved configurations found.")
        return
    log.write(f"  Saved configs ({len(configs)}):")
    for c in configs:
        try:
            with open(c) as f:
                data = json.load(f)
            name = data.get("store_name", c.stem)
            address = data.get("store_address", "No address")
            ep_count = len(data.get("endpoints", []))
            saved = data.get("saved_at", "")[:10]
            log.write(f"    • {name}")
            log.write(f"      Location: {address} | Endpoints: {ep_count} | Saved: {saved}")
        except (json.JSONDecodeError, OSError):
            log.write(f"    • {c.stem} (broken — delete and recreate)")


# ─────────────────────────────────────────────
# FULL SYSTEM DIAGNOSTICS
# ─────────────────────────────────────────────

def full_diagnostics():
    """
    Run ALL diagnostic checks in one go.
    Uses simultaneous serial scan (fastest), no redundant double-scanning.
    """
    log.section(f"{APP_NAME} v{VERSION} \u2014 FULL SYSTEM DIAGNOSTICS")
    log.write(f"  Date/Time : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.write(f"  Hostname  : {socket.gethostname()}")
    log.write(f"  OS        : {platform.system()} {platform.release()}")
    log.write(f"  Log file  : {log.log_file}")
    admin_status = 'Yes' if is_admin() else 'No - limited functionality'
    log.write(f"  Admin     : {admin_status}")

    # 1. Serial ports \u2014 simultaneous scan only (fast, no redundant testing)
    test_all_ports_simultaneous()

    # 2. USB devices
    scan_usb_devices()
    test_usb_connections()

    # 3. Network (default endpoints)
    test_network_parallel()

    # 4. Ping key hosts
    log.section("PING TEST")
    for host in ["8.8.8.8", "192.168.1.1"]:
        result = ping_host(host)
        is_ok = "FAIL" not in result
        log.result(host, "OK" if is_ok else "FAIL", result)

    # 5. OPOS check (Windows only)
    check_opos_registry()

    # 6. POS utility check (123Scan, OPOS Tools, SMS)
    check_pos_utilities()

    log.section(f"DIAGNOSTICS COMPLETE")
    log.write(f"  Full log saved to: {log.log_file}")
    log.write("")
    log.print_ticket_block()


# \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
# INTERACTIVE MENU
# \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def print_menu():
    print()
    print("=" * 60)
    print(f"  {APP_NAME} v{VERSION}")
    print(f"  Author: Christian J. Sanchez Avila \u2014 AM PM Services")
    print("=" * 60)
    print("  [1]  Full System Diagnostics (recommended)")
    print("  [2]  Test Serial Ports (Simultaneous)")
    print("  [3]  Scan USB Devices")
    print("  [4]  Test USB Connections")
    print("  [5]  Network Tests (Parallel)")
    print("  [6]  Ping Test")
    print("  [7]  OPOS/JavaPOS Check (Windows)")
    print("  [8]  Quick Test from Config")
    print("  [9]  Save Store Config")
    print("  [10] List Saved Configs")
    print("  [11] Check POS Utilities (123Scan, OPOS Tools, SMS)")
    print("  [12] Launch 123Scan")
    print("  [0]  Exit")
    print("-" * 60)


def main():
    """
    Main entry point.
    Double-click the .exe to start \u2014 no arguments needed.
    """
    LOG_DIR.mkdir(exist_ok=True)
    CONFIG_DIR.mkdir(exist_ok=True)

    print()
    print(f"  {APP_NAME} v{VERSION}")
    print(f"  Starting up...")
    check_elevation()

    while True:
        print_menu()
        try:
            choice = input("  Enter choice: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Exiting...")
            break

        if choice == "1":
            full_diagnostics()
        elif choice == "2":
            test_all_ports_simultaneous()
        elif choice == "3":
            scan_usb_devices()
        elif choice == "4":
            test_usb_connections()
        elif choice == "5":
            test_network_parallel()
        elif choice == "6":
            log.section("PING TEST")
            host = input("  Enter host to ping [default: 8.8.8.8]: ").strip() or "8.8.8.8"
            result = ping_host(host)
            is_ok = "FAIL" not in result
            log.result(host, "OK" if is_ok else "FAIL", result)
        elif choice == "7":
            check_opos_registry()
        elif choice == "8":
            load_config_and_quick_test()
        elif choice == "9":
            save_config()
        elif choice == "10":
            list_configs()
        elif choice == "11":
            check_pos_utilities()
        elif choice == "12":
            launch_123scan()
        elif choice == "0":
            print()
            log.write("  Goodbye!")
            print()
            log.print_ticket_block()
            break
        else:
            print("  [!] Invalid choice. Please try again.")

        input("\n  Press Enter to continue...")


if __name__ == "__main__":
    main()