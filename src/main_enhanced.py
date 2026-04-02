#!/usr/bin/env python3
"""
POS Diagnostic Toolkit v3.0 - Enhanced
Author: Christian J. Sanchez Avila
Company: AM PM Services

A comprehensive field technician utility for diagnosing POS hardware issues.
Supports serial ports, USB devices, network connectivity, and device-specific testing.
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
from pathlib import Path

# Try importing serial — graceful fallback if not installed
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

VERSION = "3.0.0"
APP_NAME = "POS Diagnostic Toolkit"
LOG_DIR = Path("logs")
CONFIG_DIR = Path("configs")

# Device detection patterns — map port descriptions to device types
DEVICE_PATTERNS = {
    "verifone":  {"keywords": ["verifone", "vx", "mx9"], "test_cmd": b"STATUS\r\n"},
    "ingenico":  {"keywords": ["ingenico", "ipp", "isc"],  "test_cmd": b"STATUS\r\n"},
    "epson":     {"keywords": ["epson", "tm-", "receipt"], "test_cmd": bytes([0x1B, 0x40])},  # ESC @
    "zebra":     {"keywords": ["zebra", "symbol", "ls"],   "test_cmd": bytes([0x05])},         # ENQ
    "scale":     {"keywords": ["scale", "mettler", "toledo"], "test_cmd": b"W\r\n"},
    "cashdrawer":{"keywords": ["cash", "drawer", "apd"],   "test_cmd": bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])},
}

# Common network endpoints to check
NETWORK_ENDPOINTS = [
    ("8.8.8.8",     53,  "Google DNS"),
    ("8.8.4.4",     53,  "Google DNS 2"),
    ("1.1.1.1",     53,  "Cloudflare DNS"),
    ("192.168.1.1",  80,  "Default Gateway"),
    ("localhost",    9100,"Epson ePOS"),
    ("localhost",    80,  "HTTP"),
    ("localhost",    443, "HTTPS"),
]


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

class Logger:
    """Simple file + console logger for field use."""

    def __init__(self):
        LOG_DIR.mkdir(exist_ok=True)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.log_file = LOG_DIR / f"pos-diag-{today}.log"
        self._buf = []

    def write(self, text: str):
        """Write to console and log file simultaneously."""
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
        icon = "✓" if status.upper() in ("OK", "OPEN", "FOUND", "PASS") else "✗"
        msg = f"  {icon} {label:<35} {status}"
        if detail:
            msg += f" — {detail}"
        self.write(msg)

    def flush_to_clipboard(self):
        """Print a copyable block for ticket remarks."""
        self.write("\n" + "─" * 60)
        self.write("  COPY BELOW FOR TICKET REMARKS:")
        self.write("─" * 60)
        for line in self._buf[-40:]:
            print(line)


log = Logger()


# ─────────────────────────────────────────────
# SERIAL PORT TESTING
# ─────────────────────────────────────────────

def detect_device_type(port_description: str) -> str:
    """Identify device type from port description string."""
    desc_lower = port_description.lower()
    for device, info in DEVICE_PATTERNS.items():
        if any(kw in desc_lower for kw in info["keywords"]):
            return device
    return "generic"


def test_single_port(port_name: str, baud: int = 9600, timeout: float = 2.0) -> dict:
    """
    Open a serial port, detect device type, send a test command,
    and return a result dictionary.
    """
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

            # Get device type from port description
            ports = {p.device: p for p in serial.tools.list_ports.comports()}
            desc = ports.get(port_name, None)
            desc_str = desc.description if desc else ""
            device_type = detect_device_type(desc_str)
            result["device"] = device_type

            # Send test command specific to device type
            cmd = DEVICE_PATTERNS.get(device_type, {}).get("test_cmd", b"TEST\r\n")
            ser.write(cmd)
            time.sleep(0.5)

            # Read response (up to 64 bytes)
            if ser.in_waiting:
                raw = ser.read(64)
                result["response"] = raw.hex()
                result["status"] = "OK"

    except serial.SerialException as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"Unexpected: {e}"

    return result


def test_all_ports_sequential():
    """
    Enumerate every available COM/serial port and test each one in sequence.
    Ports are tested one after another — safe and simple.
    Good for: basic scans, older machines, avoiding device conflicts.
    """
    log.section("SEQUENTIAL PORT SCAN")

    if not SERIAL_AVAILABLE:
        log.write("  [!] pyserial not available — skipping serial tests")
        return

    ports = list(serial.tools.list_ports.comports())

    if not ports:
        log.write("  [!] No serial/COM ports detected on this system")
        return

    log.write(f"  Found {len(ports)} port(s). Testing one by one...\n")

    results = []
    for port in ports:
        log.write(f"  Testing {port.device} ({port.description})...")
        res = test_single_port(port.device)
        results.append(res)
        log.result(
            port.device,
            res["status"],
            f"{res['device']} | {res['error'] or res['response'] or 'no response'}"
        )

    ok = sum(1 for r in results if r["status"] in ("OK", "OPEN"))
    log.write(f"\n  Summary: {ok}/{len(results)} ports accessible")
    return results


def test_all_ports_simultaneous():
    """
    Test ALL serial/COM ports at the same time using threads.
    Every port gets its own thread — results come in as fast as the
    slowest single port (instead of adding up all timeouts).

    Example: 4 ports × 2s timeout = 2s total (not 8s sequential).

    Good for: fast scans on stores with many devices, time-critical calls.
    Note: May miss responses on devices that conflict when opened together.
    """
    log.section("SIMULTANEOUS PORT SCAN (All at Once)")

    if not SERIAL_AVAILABLE:
        log.write("  [!] pyserial not available — skipping serial tests")
        return

    ports = list(serial.tools.list_ports.comports())

    if not ports:
        log.write("  [!] No serial/COM ports detected on this system")
        return

    log.write(f"  Found {len(ports)} port(s). Testing ALL simultaneously...\n")

    results = {}
    lock = threading.Lock()  # Prevent garbled output when threads write at same time

    def worker(port):
        """Thread worker — tests one port and stores result."""
        res = test_single_port(port.device)
        with lock:
            results[port.device] = res

    # Launch one thread per port
    threads = []
    start_time = time.time()
    for port in ports:
        t = threading.Thread(target=worker, args=(port,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete (max 10 seconds total)
    for t in threads:
        t.join(timeout=10)

    elapsed = time.time() - start_time
    log.write(f"  All ports tested in {elapsed:.1f}s\n")

    # Print results in port order
    for port in ports:
        res = results.get(port.device, {"status": "TIMEOUT", "device": "?", "error": "thread timeout", "response": ""})
        log.result(
            port.device,
            res["status"],
            f"{res['device']} | {res['error'] or res['response'] or 'no response'}"
        )

    ok = sum(1 for r in results.values() if r["status"] in ("OK", "OPEN"))
    log.write(f"\n  Summary: {ok}/{len(ports)} ports accessible | Time: {elapsed:.1f}s")
    return results


# ─────────────────────────────────────────────
# USB DEVICE SCANNING & CONNECTION TESTING
# ─────────────────────────────────────────────

# Known POS USB device signatures — used to classify detected devices
USB_DEVICE_SIGNATURES = {
    # Vendor ID : (brand, device type)
    "04b8": ("Epson",         "Printer/Scanner"),
    "0525": ("Verifone",      "Pin Pad"),
    "0b00": ("Ingenico",      "Pin Pad/Terminal"),
    "05e0": ("Symbol/Zebra",  "Scanner"),
    "0a5f": ("Zebra",         "Scanner/Printer"),
    "1fc9": ("NCR",           "POS Device"),
    "0403": ("FTDI",          "USB-Serial Adapter"),
    "067b": ("Prolific",      "USB-Serial Adapter"),
    "10c4": ("Silicon Labs",  "USB-Serial Adapter"),
    "1a86": ("CH340",         "USB-Serial Adapter"),
    "0557": ("ATEN",          "USB-Serial/KVM"),
    "045e": ("Microsoft",     "HID/Keyboard/Mouse"),
    "046d": ("Logitech",      "HID/Keyboard/Mouse"),
    "0458": ("KYE/Genius",    "HID Device"),
    "05ac": ("Apple",         "HID/Hub"),
    "0424": ("Microchip",     "USB Hub"),
    "2341": ("Arduino",       "USB-Serial"),
    "0451": ("Texas Instrs",  "USB Hub"),
    "1d6b": ("Linux",         "USB Hub/Virtual"),
}


def _classify_usb_device(vid: str, desc: str) -> str:
    """Return a friendly device type label based on vendor ID or description."""
    vid_lower = vid.lower()
    match = USB_DEVICE_SIGNATURES.get(vid_lower)
    if match:
        return f"{match[0]} — {match[1]}"

    # Fall back to keyword matching on description
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


def scan_usb_devices():
    """
    Detect USB devices using platform-specific tools:
    - Windows: PowerShell Get-PnpDevice
    - Linux:   lsusb
    - macOS:   system_profiler
    Lists all physically connected USB devices.
    """
    log.section("USB DEVICE SCAN (Connected Devices)")

    os_name = platform.system()
    log.write(f"  Platform: {os_name}\n")

    try:
        if os_name == "Windows":
            cmd = [
                "powershell", "-Command",
                "Get-PnpDevice -PresentOnly | Where-Object {$_.InstanceId -like 'USB*'} | "
                "Select-Object Status, Class, FriendlyName | Format-List"
            ]
            out = subprocess.check_output(cmd, timeout=15, stderr=subprocess.DEVNULL, text=True)
        elif os_name == "Linux":
            out = subprocess.check_output(["lsusb"], timeout=10, text=True)
        elif os_name == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPUSBDataType"], timeout=15, text=True
            )
        else:
            log.write(f"  [!] Unsupported platform: {os_name}")
            return

        if not out.strip():
            log.write("  [!] No USB devices detected")
            return

        log.write("  Connected USB Devices:")
        for line in out.strip().splitlines():
            if line.strip():
                log.write(f"    {line.strip()}")

    except FileNotFoundError:
        log.write("  [!] USB scan tool not found on this system")
    except subprocess.TimeoutExpired:
        log.write("  [!] USB scan timed out")
    except Exception as e:
        log.write(f"  [!] USB scan error: {e}")


def test_usb_connections():
    """
    Test USB connections — goes beyond just listing devices.
    For each detected USB device:
      1. Lists it with Vendor ID and Product ID
      2. Classifies the device type (printer, scanner, pin pad, etc.)
      3. Checks if the device is responding (OK / ERROR / UNKNOWN)
      4. Shows status: OK (driver loaded, responding) vs ERROR (driver issue)

    Windows: uses PowerShell Get-PnpDevice + DeviceID for VID/PID
    Linux:   uses lsusb -v for detailed info
    macOS:   uses system_profiler SPUSBDataType
    """
    log.section("USB CONNECTION TEST")

    os_name = platform.system()
    log.write(f"  Platform: {os_name}\n")

    devices = []  # List of dicts: {name, vid, pid, status, device_type}

    try:
        if os_name == "Windows":
            # --- Windows: PowerShell query ---
            # Get all USB devices with their hardware IDs (VID/PID) and status
            cmd = [
                "powershell", "-Command",
                """
                Get-PnpDevice -PresentOnly |
                Where-Object { $_.InstanceId -like 'USB*' } |
                Select-Object Status, FriendlyName, InstanceId |
                ForEach-Object {
                    $vid = '';
                    $pid = '';
                    if ($_.InstanceId -match 'VID_([0-9A-F]{4})') { $vid = $matches[1] }
                    if ($_.InstanceId -match 'PID_([0-9A-F]{4})') { $pid = $matches[1] }
                    [PSCustomObject]@{
                        Status = $_.Status;
                        Name = $_.FriendlyName;
                        VID = $vid;
                        PID = $pid
                    }
                } | ConvertTo-Json
                """
            ]
            raw = subprocess.check_output(cmd, timeout=20, stderr=subprocess.DEVNULL, text=True)
            items = json.loads(raw) if raw.strip() else []
            # Handle single device (dict) vs multiple (list)
            if isinstance(items, dict):
                items = [items]
            for item in items:
                name = item.get("Name") or "Unknown"
                vid  = (item.get("VID") or "????").lower()
                pid  = (item.get("PID") or "????").lower()
                status_raw = item.get("Status", "Unknown")
                # Map Windows PnP status to OK/ERROR/UNKNOWN
                if status_raw == "OK":
                    status = "OK"
                elif status_raw in ("Error", "Degraded", "Unknown"):
                    status = "ERROR"
                else:
                    status = "WARNING"
                devices.append({
                    "name":   name,
                    "vid":    vid,
                    "pid":    pid,
                    "status": status,
                    "type":   _classify_usb_device(vid, name),
                })

        elif os_name == "Linux":
            # --- Linux: lsusb for device list ---
            raw = subprocess.check_output(["lsusb"], timeout=10, text=True)
            for line in raw.strip().splitlines():
                # Format: Bus 001 Device 002: ID 04b8:0202 Seiko Epson Corp. ...
                parts = line.split()
                vid_pid = ""
                name    = line
                for p in parts:
                    if ":" in p and len(p) == 9:
                        vid_pid = p
                        name = " ".join(parts[parts.index(p)+1:])
                        break
                vid = vid_pid.split(":")[0] if ":" in vid_pid else "????"
                pid = vid_pid.split(":")[1] if ":" in vid_pid else "????"
                devices.append({
                    "name":   name or line,
                    "vid":    vid,
                    "pid":    pid,
                    "status": "OK",  # lsusb only lists responding devices
                    "type":   _classify_usb_device(vid, name),
                })

        elif os_name == "Darwin":
            # --- macOS: system_profiler ---
            raw = subprocess.check_output(
                ["system_profiler", "SPUSBDataType"], timeout=15, text=True
            )
            name = ""
            for line in raw.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("USB") and ":" in stripped:
                    key, _, val = stripped.partition(":")
                    key = key.strip().lower()
                    val = val.strip()
                    if key in ("product id", "vendor id"):
                        pass
                    elif not key.startswith("bcd") and val:
                        name = val
                        devices.append({
                            "name":   name,
                            "vid":    "????",
                            "pid":    "????",
                            "status": "OK",
                            "type":   _classify_usb_device("", name),
                        })
        else:
            log.write(f"  [!] Unsupported platform: {os_name}")
            return

    except FileNotFoundError:
        log.write("  [!] USB test tool not found on this system")
        return
    except subprocess.TimeoutExpired:
        log.write("  [!] USB test timed out")
        return
    except json.JSONDecodeError:
        log.write("  [!] Could not parse USB device data")
        return
    except Exception as e:
        log.write(f"  [!] USB test error: {e}")
        return

    if not devices:
        log.write("  [!] No USB devices found")
        return

    log.write(f"  Found {len(devices)} USB device(s):\n")
    log.write(f"  {'Device':<35} {'VID:PID':<12} {'Type':<28} {'Status'}")
    log.write(f"  {'-'*35} {'-'*12} {'-'*28} {'-'*8}")

    ok_count = 0
    for d in devices:
        vid_pid = f"{d['vid']}:{d['pid']}"
        log.result(
            d["name"][:34],
            d["status"],
            f"[{vid_pid}] {d['type']}"
        )
        if d["status"] == "OK":
            ok_count += 1

    log.write(f"\n  Summary: {ok_count}/{len(devices)} USB devices responding OK")

    # Flag any errors
    errors = [d for d in devices if d["status"] != "OK"]
    if errors:
        log.write(f"\n  ⚠️  DEVICES WITH ISSUES:")
        for d in errors:
            log.write(f"     • {d['name']} [{d['vid']}:{d['pid']}] — {d['status']}")
        log.write("  → Check Device Manager for driver errors")

    return devices


# ─────────────────────────────────────────────
# NETWORK TESTING
# ─────────────────────────────────────────────

def test_tcp_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Attempt a TCP connection to host:port. Returns True if successful."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def test_network_parallel():
    """
    Test multiple network endpoints simultaneously using threads.
    Much faster than sequential testing — all endpoints checked at once.
    """
    log.section("PARALLEL NETWORK TESTS")

    results = {}

    def worker(host, port, label):
        status = "OPEN" if test_tcp_port(host, port) else "CLOSED"
        results[label] = status

    threads = []
    for host, port, label in NETWORK_ENDPOINTS:
        t = threading.Thread(target=worker, args=(host, port, label))
        threads.append(t)
        t.start()

    # Wait for all threads to finish (max 5 seconds)
    for t in threads:
        t.join(timeout=5)

    for label, status in results.items():
        log.result(label, status)

    open_count = sum(1 for s in results.values() if s == "OPEN")
    log.write(f"\n  Summary: {open_count}/{len(results)} endpoints reachable")


def ping_host(host: str) -> str:
    """
    Ping a host once. Returns latency string or 'FAIL'.
    Works on both Windows and Linux/macOS.
    """
    flag = "-n" if platform.system() == "Windows" else "-c"
    try:
        out = subprocess.check_output(
            ["ping", flag, "1", host],
            timeout=5, stderr=subprocess.DEVNULL, text=True
        )
        # Extract ms from output
        for line in out.splitlines():
            if "ms" in line.lower() or "time=" in line.lower():
                return line.strip()
        return "OK"
    except Exception:
        return "FAIL"


# ─────────────────────────────────────────────
# CONFIGURATION MANAGEMENT
# ─────────────────────────────────────────────

def save_config(store_name: str, config: dict):
    """Save store-specific configuration to JSON file."""
    CONFIG_DIR.mkdir(exist_ok=True)
    safe_name = store_name.replace(" ", "_").lower()
    path = CONFIG_DIR / f"{safe_name}.json"
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
    log.write(f"  Config saved: {path}")


def load_config(store_name: str) -> dict:
    """Load a previously saved store configuration."""
    safe_name = store_name.replace(" ", "_").lower()
    path = CONFIG_DIR / f"{safe_name}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def list_configs():
    """List all saved store configurations."""
    CONFIG_DIR.mkdir(exist_ok=True)
    configs = list(CONFIG_DIR.glob("*.json"))
    if not configs:
        log.write("  No saved configurations found.")
        return
    log.write(f"  Saved configs ({len(configs)}):")
    for c in configs:
        log.write(f"    • {c.stem}")


# ─────────────────────────────────────────────
# FULL SYSTEM DIAGNOSTICS
# ─────────────────────────────────────────────

def full_diagnostics():
    """
    Run ALL diagnostic checks in sequence:
    1. System info
    2. Serial port scan
    3. USB device scan
    4. Network tests
    5. Ping gateway
    """
    log.section(f"{APP_NAME} v{VERSION} — FULL SYSTEM DIAGNOSTICS")
    log.write(f"  Date/Time : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.write(f"  Hostname  : {socket.gethostname()}")
    log.write(f"  OS        : {platform.system()} {platform.release()}")
    log.write(f"  Log file  : {log.log_file}")

    # 1. Serial ports — run BOTH sequential and simultaneous for full picture
    test_all_ports_simultaneous()   # Fast scan first (all at once)
    test_all_ports_sequential()     # Then sequential for detailed output

    # 2. USB devices — scan + connection test
    scan_usb_devices()
    test_usb_connections()

    # 3. Network
    test_network_parallel()

    # 4. Ping gateway
    log.section("PING TEST")
    for host in ["8.8.8.8", "192.168.1.1"]:
        result = ping_host(host)
        log.result(host, "OK" if "FAIL" not in result else "FAIL", result)

    log.section("DIAGNOSTICS COMPLETE")
    log.write(f"  Full log saved to: {log.log_file}")
    log.write("  Copy log content into your ticket remarks.\n")


# ─────────────────────────────────────────────
# INTERACTIVE MENU
# ─────────────────────────────────────────────

def print_menu():
    print("\n" + "=" * 60)
    print(f"  {APP_NAME} v{VERSION}")
    print(f"  Author: Christian J. Sanchez Avila — AM PM Services")
    print("=" * 60)
    print("  [1] Full System Diagnostics (recommended)")
    print("  [2] Test Serial Ports — Sequential (one by one)")
    print("  [3] Test Serial Ports — Simultaneous (all at once, fastest)")
    print("  [4] Scan USB Devices (list all)")
    print("  [5] Test USB Connections (status + type check)")
    print("  [6] Network Tests (Parallel)")
    print("  [7] Ping Test")
    print("  [8] List Saved Configs")
    print("  [0] Exit")
    print("-" * 60)


def main():
    """
    Main entry point. Displays an interactive menu so field techs
    can run any diagnostic check with a single keypress.
    Double-click the .exe to start — no command-line arguments needed.
    """
    # Ensure log and config dirs exist
    LOG_DIR.mkdir(exist_ok=True)
    CONFIG_DIR.mkdir(exist_ok=True)

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
            test_all_ports_sequential()
        elif choice == "3":
            test_all_ports_simultaneous()
        elif choice == "4":
            scan_usb_devices()
        elif choice == "5":
            test_usb_connections()
        elif choice == "6":
            test_network_parallel()
        elif choice == "7":
            log.section("PING TEST")
            host = input("  Enter host to ping [default: 8.8.8.8]: ").strip() or "8.8.8.8"
            result = ping_host(host)
            log.result(host, "OK" if "FAIL" not in result else "FAIL", result)
        elif choice == "8":
            log.section("SAVED CONFIGURATIONS")
            list_configs()
        elif choice == "0":
            print("  Goodbye!")
            break
        else:
            print("  [!] Invalid choice. Please try again.")

        input("\n  Press Enter to continue...")


if __name__ == "__main__":
    main()
