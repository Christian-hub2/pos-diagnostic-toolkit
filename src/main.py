import os
import socket
import serial.tools.list_ports
from ping import ping


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def show_menu():
    #clear()
    print("=" * 40)
    print("      POS DIAGNOSTIC TOOLKIT")
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
        return print("[*] No serial ports")
    for p in ports:
        print(p.device, "-", p.description)


def test_serial():
    import serial
    port = input("Enter COM port: ")

    try:
        ser = serial.Serial(port, 9600, timeout=2)
        print("[*] Connection opened")
        ser.write(b'TEST\n')
        data = ser.readline()
        print("Response:", data)
        ser.close()
    except Exception as e:
        print("Error:", e)


def ping_device():
    ip = input("Enter IP: ")
    if ping(ip):
        print("[*] Ping successful")


def test_connection(ip, port):
    try:
        socket.create_connection((ip, port), timeout=3)
        return "[*] OPEN"
    except:
        return "[*] CLOSED"


def tcp_test():
    ip = input("IP: ")
    port = int(input("Port: "))
    print(test_connection(ip, port))


def system_info():
    os.system("ipconfig")


while True:
    show_menu()
    choice = input("Select option: ")

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
        break
