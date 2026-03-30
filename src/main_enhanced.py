        self.scan_usb_devices()
        
        # 5. Common POS Services
        print("\n[5] COMMON POS SERVICE PORTS:")
        print("-" * 40)
        common_ports = [
            ("localhost", 9100, "Epson ePOS"),
            ("localhost", 443, "HTTPS"),
            ("localhost", 80, "HTTP"),
            ("127.0.0.1", 3306, "MySQL"),
            ("127.0.0.1", 1433, "MSSQL"),
        ]
        
        for ip, port, service in common_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((ip, port))
                sock.close()
                status = "OPEN" if result == 0 else "CLOSED"
                print(f"{service:<15} {ip}:{port:<10} {status}")
            except:
                print(f"{service:<15} {ip}:{port:<10} ERROR")
        
        print("\n[*] Diagnostics complete. Check log file for details.")
        self.log("FULL_DIAGNOSTICS", "Completed comprehensive system check")
    
    def save_configuration(self):
        """Save current test configuration"""
        config = {
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "common_ips": [],
            "common_ports": [
                {"name": "Epson Printer", "port": 9100},
                {"name": "Verifone VHQ", "port": 443},
                {"name": "Payment Host", "port": 8443},
            ],
            "serial_baud": 9600,
            "ping_count": 4,
            "timeout": 3
        }
        
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")
        os.makedirs(config_dir, exist_ok=True)
        
        store_name = input("\nEnter store name for config: ").strip()
        if not store_name:
            store_name = "default"
        
        filename = os.path.join(config_dir, f"{store_name.replace(' ', '_')}.json")
        
        with open(filename, "w") as f:
            json.dump(config, f, indent=2)
        
        print(f"[+] Configuration saved to {filename}")
        self.log("SAVE_CONFIG", f"Saved config: {filename}")
    
    def load_configuration(self):
        """Load saved configuration"""
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")
        
        if not os.path.exists(config_dir):
            print("[!] No configurations saved yet")
            return
        
        configs = [f for f in os.listdir(config_dir) if f.endswith('.json')]
        
        if not configs:
            print("[!] No configurations found")
            return
        
        print("\n[*] Available configurations:")
        for idx, config_file in enumerate(configs, 1):
            print(f"  {idx}. {config_file[:-5].replace('_', ' ')}")
        
        try:
            choice = int(input("\nSelect config to load: ").strip())
            if 1 <= choice <= len(configs):
                filename = os.path.join(config_dir, configs[choice-1])
                with open(filename, "r") as f:
                    config = json.load(f)
                
                print(f"[+] Loaded configuration: {configs[choice-1]}")
                print(f"    Saved: {config.get('timestamp', 'Unknown')}")
                self.log("LOAD_CONFIG", f"Loaded: {filename}")
            else:
                print("[!] Invalid selection")
        except (ValueError, IndexError):
            print("[!] Invalid input")
    
    def run(self):
        """Main application loop"""
        self.clear_screen()
        
        while True:
            self.show_menu()
            choice = input("\nSelect option: ").strip()
            
            if choice == "1":
                self.list_all_ports()
            elif choice == "2":
                self.test_all_ports_sequential()
            elif choice == "3":
                ports = self.list_all_ports()
                if ports:
                    try:
                        port_num = int(input("\nEnter port number to test: ").strip())
                        if 1 <= port_num <= len(ports):
                            port_info = ports[port_num-1]
                            self.test_single_port(port_info['device'], port_info['description'])
                        else:
                            print("[!] Invalid port number")
                    except ValueError:
                        print("[!] Please enter a number")
            elif choice == "4":
                self.scan_usb_devices()
            elif choice == "5":
                self.parallel_network_tests()
            elif choice == "6":
                self.ping_device()
            elif choice == "7":
                self.test_tcp_port()
            elif choice == "8":
                self.full_system_diagnostics()
            elif choice == "9":
                self.save_configuration()
            elif choice == "10":
                self.load_configuration()
            elif choice == "0":
                print(f"\n[*] Session log saved to: {self.log_file}")
                print("[*] Goodbye.")
                break
            else:
                print("[!] Invalid option")
            
            input("\nPress Enter to continue...")
            self.clear_screen()


def main():
    """Entry point"""
    try:
        tool = POSDiagnosticToolkit()
        tool.run()
    except KeyboardInterrupt:
        print("\n\n[*] Tool interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
