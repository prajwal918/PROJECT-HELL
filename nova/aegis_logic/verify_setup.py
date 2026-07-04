import os
import sys
import socket
from pathlib import Path

def check_python_version():
    print("Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 9:
        print(f"[PASS] Python {version.major}.{version.minor}.{version.micro}")
        return True
    print(f"[FAIL] Python {version.major}.{version.minor}.{version.micro} (requires 3.9+)")
    return False

def check_dependencies():
    print("\nChecking Python dependencies...")
    required = ['asyncio', 'websockets', 'requests', 'python-dotenv', 'numpy']
    missing = []

    for module in required:
        try:
            __import__(module.replace('-', '_'))
            print(f"[PASS] {module}")
        except ImportError:
            print(f"[FAIL] {module}")
            missing.append(module)

    return len(missing) == 0

def check_aegis_files():
    print("\nChecking AEGIS files...")
    aegis_dir = Path(__file__).parent
    required = [
        'main.py',
        'config.py',
        'core/absorption_detector.py',
        'core/deriv_execution.py',
        'core/nexus_bridge.py',
    ]

    all_exist = True
    for file in required:
        path = aegis_dir / file
        if path.exists():
            print(f"[PASS] {file}")
        else:
            print(f"[FAIL] {file} (missing)")
            all_exist = False

    return all_exist

def check_env_file():
    print("\nChecking .env file...")
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        print(f"[PASS] .env exists")
        with open(env_file) as f:
            content = f.read()
            if 'DERIV_API_TOKEN' in content:
                print(f"[PASS] DERIV_API_TOKEN configured")
            else:
                print(f"[FAIL] DERIV_API_TOKEN not configured")
            return True
    else:
        print(f"[FAIL] .env not found (copy .env.example to .env)")
        return False

def check_nexus_backend():
    print("\nChecking NEXUS Rust backend...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 9001))
        sock.close()

        if result == 0:
            print(f"[PASS] NEXUS backend running on ws://localhost:9001")
            return True
        else:
            print(f"[FAIL] NEXUS backend not running (ws://localhost:9001)")
            return False
    except Exception as e:
        print(f"[FAIL] NEXUS backend check failed: {e}")
        return False

def check_overseer():
    print("\nChecking OVERSEER data feed...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        sock.bind(('127.0.0.1', 0))
        result = sock.connect_ex(('127.0.0.1', 12347))
        sock.close()

        if result == 0:
            print(f"[PASS] OVERSEER UDP feed available (127.0.0.1:12347)")
            return True
        else:
            print(f"[FAIL] OVERSEER UDP feed not available (127.0.0.1:12347)")
            return False
    except Exception as e:
        print(f"[FAIL] OVERSEER check failed: {e}")
        return False

def main():
    print("=" * 60)
    print("  AEGIS SETUP VERIFICATION")
    print("=" * 60)

    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("AEGIS Files", check_aegis_files),
        ("Environment Config", check_env_file),
        ("NEXUS Backend", check_nexus_backend),
        ("OVERSEER Data Feed", check_overseer),
    ]

    results = []
    for name, check_func in checks:
        result = check_func()
        results.append((name, result))

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status:8} {name}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        print("\n[PASS] All checks passed! AEGIS is ready to start.")
        print("\nTo start AEGIS:")
        print("  python main.py")
    else:
        print("\n[FAIL] Some checks failed. Please fix issues before starting.")
        print("\nQuick fixes:")
        if not results[3][1]:
            print("  - Copy .env.example to .env and add DERIV_API_TOKEN")
        if not results[4][1]:
            print("  - Start NEXUS Rust backend")
            print("    cd C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\nexus\\rust-backend")
            print("    cargo run --release")
        if not results[5][1]:
            print("  - Start OVERSEER to feed data to NEXUS")

if __name__ == "__main__":
    main()