import os
import platform
import socket
import serial.tools.list_ports
from ping import ping
from logger import log, get_log_path

VERSION = "2.0"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def show_menu():
    print("=" * 40)
    print(f"    POS DIAGNOSTIC TOOLKIT v{VERSION}")
    print("      Field Tech Edition")
    print("=" * 40)
    print("1. List Serial Ports")
    print("2. Test Serial Connection")
    print("3. Ping Device")
    print("4. Test TCP Port")
    print("5. System Info")
    print("0. Exit")
    print("=" * 40)


def list_serial():
    ports = serial.tools.list_ports.comports()
    if not ports:
        result = "No serial ports found"
        print(f"[*] {result}")
        log("LIST_SERIAL", result)
        return
    for p in ports:
        line = f"{p.device} - {p.description}"
        print(f"  {line}")
        log("LIST_SERIAL", line)


def test_serial():
    import serial
    print("\nDevice type:")
    print("  1. Verifone")
    print("  2. Ingenico")
    print("  3. Epson Printer")
    print("  4. Generic")
    dtype = input("Select device type: ").strip()

    commands = {
        "1": (b"STATUS\r\n", "Verifone"),
        "2": (b"STATUS\r\n", "Ingenico"),
        "3": (b"\x1b\x40",   "Epson"),
        "4": (b"TEST\n",     "Generic"),
    }
    cmd, label = commands.get(dtype, (b"TEST\n", "Generic"))

    port = input("Enter COM port (e.g. COM3): ").strip()
    try:
        ser = serial.Serial(port, 9600, timeout=2)
        print(f"[*] Connected to {port} ({label})")
        ser.write(cmd)
        data = ser.readline()
        result = f"Port={port} Device={label} Response={data}"
        print(f"[*] Response: {data}")
        ser.close()
        log("SERIAL_TEST", result)
    except Exception as e:
        print(f"[!] Error: {e}")
        log("SERIAL_TEST", f"Port={port} Error={e}")


def ping_device():
    ip = input("Enter IP: ").strip()
    success = ping(ip)
    result = f"IP={ip} Status={'REACHABLE' if success else 'UNREACHABLE'}"
    print(f"[*] {'Ping successful' if success else 'Ping failed'}")
    log("PING", result)


def test_connection(ip, port):
    try:
        socket.create_connection((ip, port), timeout=3)
        return "OPEN"
    except:
        return "CLOSED"


def tcp_test():
    print("\nQuick presets:")
    print("  1. Verifone VHQ   (443)")
    print("  2. Epson Printer  (9100)")
    print("  3. Payment Host   (8443)")
    print("  4. Manual entry")
    choice = input("Select: ").strip()

    presets = {
        "1": ("", 443,  "Verifone VHQ"),
        "2": ("", 9100, "Epson Printer"),
        "3": ("", 8443, "Payment Host"),
    }

    if choice in presets:
        _, default_port, label = presets[choice]
        ip = input(f"IP for {label}: ").strip()
        port = default_port
    else:
        ip = input("IP: ").strip()
        port = int(input("Port: ").strip())
        label = "Manual"

    status = test_connection(ip, port)
    result = f"IP={ip} Port={port} Label={label} Status={status}"
    print(f"[*] Port {port} is {status}")
    log("TCP_TEST", result)


def system_info():
    system = platform.system().lower()
    print("\n[*] Network Information:")
    if system == "windows":
        os.system("ipconfig /all")
    else:
        os.system("ip addr && echo '---' && ip route")
    log("SYSTEM_INFO", f"OS={platform.system()} Version={platform.version()}")


while True:
    show_menu()
    choice = input("Select option: ").strip()

    if choice == "1":
        list_serial()
    elif choice == "2":
        test_serial()
    elif choice == "3":
        ping_device()
    elif choice == "4":
        tcp_test()
    elif choice == "5":
        system_info()
    elif choice == "0":
        print(f"\n[*] Session log saved to: {get_log_path()}")
        print("[*] Goodbye.")
        break
    else:
        print("[!] Invalid option.")

    input("\nPress Enter to continue...")
    clear()
