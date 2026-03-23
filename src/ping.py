import subprocess
import platform


def ping(ip, count: str = "4"):
    system = platform.system().lower()
    flag = "-n" if system == "windows" else "-c"
    result = subprocess.run(
        ["ping", flag, count, ip],
        capture_output=True,
        text=True
    )
    print(result.stdout)
    return "ttl=" in result.stdout.lower()
