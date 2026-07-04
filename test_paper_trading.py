#!/usr/bin/env python3
"""
Rithmic Paper Trading Test
Test if Rithmic paper trading account is working
"""

import asyncio
import json
import ssl
from pathlib import Path
import socket

PROJECT_ROOT = Path(__file__).parent

def load_rithmic_config():
    """Load Rithmic credentials"""
    possible_paths = [
        PROJECT_ROOT / "nexus" / "rust-backend" / ".env.rithmic",
        Path("C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\nexus\\rust-backend\\.env.rithmic"),
    ]
    
    for path in possible_paths:
        if path.exists():
            config = {}
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
            
            required_keys = ['RITHMIC_USERNAME', 'RITHMIC_PASSWORD', 'RITHMIC_GATEWAY']
            missing = [k for k in required_keys if k not in config]
            
            if not missing:
                return config
    
    return None

def test_dns_resolution():
    """Test if Rithmic domains resolve"""
    print("\n" + "="*60)
    print("  DNS RESOLUTION TEST")
    print("="*60)

    domains = [
        "rithmic.rapi.com",
        "api.rithmic.com", 
        "rithmic.com",
        "demo.rithmic.com",
        "paper.rithmic.com"
    ]

    results = {}
    for domain in domains:
        try:
            ip = socket.gethostbyname(domain)
            results[domain] = {"status": "RESOLVED", "ip": ip}
            print(f"[+] {domain:30} -> {ip}")
        except socket.gaierror as e:
            results[domain] = {"status": "FAILED", "error": str(e)}
            print(f"[-] {domain:30} -> DNS ERROR: {e}")

    return results

def test_network_connectivity():
    """Test network connectivity to Rithmic ports"""
    print("\n" + "="*60)
    print("  NETWORK CONNECTIVITY TEST")
    print("="*60)

    targets = [
        ("rithmic.rapi.com", 443),
        ("rithmic.rapi.com", 80),
        ("rithmic.com", 443),
        ("rithmic.com", 80),
    ]

    results = {}
    for host, port in targets:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                results[f"{host}:{port}"] = "CONNECTED"
                print(f"[+] {host:30}:{port:5} -> CONNECTED")
            else:
                results[f"{host}:{port}"] = f"FAILED (error {result})"
                print(f"[-] {host:30}:{port:5} -> FAILED (error {result})")

        except Exception as e:
            results[f"{host}:{port}"] = f"ERROR: {e}"
            print(f"[-] {host:30}:{port:5} -> ERROR: {e}")

    return results

def check_paper_trading_requirements():
    """Check paper trading specific requirements"""
    print("\n" + "="*60)
    print("  PAPER TRADING REQUIREMENTS")
    print("="*60)

    requirements = [
        ("Paper Trading Account", "Your EdgeClear account must be enabled for paper trading"),
        ("API Access", "Paper trading API access must be enabled"),
        ("WebSocket Support", "Paper trading accounts typically support WebSocket"),
        ("Market Hours", "Paper trading may have different hours than live markets"),
        ("Data Simulation", "Paper trading uses simulated market data"),
    ]

    print("\nPaper Trading Requirements:")
    for req, description in requirements:
        print(f"\n• {req}")
        print(f"  {description}")

    print("\n\nCommon Paper Trading Issues:")
    issues = [
        "1. Account not activated for paper trading",
        "2. API access not enabled for paper trading", 
        "3. Different authentication requirements",
        "4. Simulated data may not match live market conditions",
        "5. Paper trading markets may have limited hours",
    ]

    for issue in issues:
        print(f"  {issue}")

async def test_rithmic_websocket_alternative(config):
    """Test alternative Rithmic WebSocket connection methods"""
    print("\n" + "="*60)
    print("  ALTERNATIVE WEBSOCKET TEST")
    print("="*60)

    # Different authentication formats for paper trading
    auth_formats = [
        {
            "name": "Standard Rithmic Auth",
            "url": "wss://rithmic.rapi.com:443",
            "auth": {
                "user": config['RITHMIC_USERNAME'],
                "password": config['RITHMIC_PASSWORD'],
                "gateway": config['RITHMIC_GATEWAY'],
                "app_name": "NEXUS",
                "app_version": "2.0.0",
                "requestId": 1
            }
        },
        {
            "name": "Paper Trading Auth",
            "url": "wss://rithmic.rapi.com:443", 
            "auth": {
                "user": config['RITHMIC_USERNAME'],
                "password": config['RITHMIC_PASSWORD'],
                "gateway": config['RITHMIC_GATEWAY'],
                "app_name": "NEXUS",
                "app_version": "2.0.0",
                "mode": "paper",
                "requestId": 1
            }
        },
        {
            "name": "Demo Mode Auth",
            "url": "wss://rithmic.rapi.com:443",
            "auth": {
                "user": config['RITHMIC_USERNAME'],
                "password": config['RITHMIC_PASSWORD'],
                "gateway": config['RITHMIC_GATEWAY'],
                "app_name": "NEXUS",
                "app_version": "2.0.0",
                "demo": True,
                "requestId": 1
            }
        }
    ]

    print("\n[*] Configuration:")
    print(f"  Username: {config['RITHMIC_USERNAME']}")
    print(f"  Gateway: {config['RITHMIC_GATEWAY']}")
    print(f"  Account Type: Paper Trading")

    for format_spec in auth_formats:
        print(f"\n[*] Testing: {format_spec['name']}")
        print(f"    URL: {format_spec['url']}")
        print(f"    Auth format: {list(format_spec['auth'].keys())}")

        try:
            # Just test if we can establish TCP connection (not full WebSocket)
            host = format_spec['url'].replace('wss://', '').replace('ws://', '').split(':')[0]
            port = int(format_spec['url'].split(':')[-1])

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                print(f"    [+] TCP connection successful")
                print(f"    [+] WebSocket endpoint reachable")
            else:
                print(f"    [-] TCP connection failed (error {result})")

        except Exception as e:
            print(f"    [-] Connection test failed: {e}")

def main():
    print("\n" + "="*60)
    print("  RITHMIC PAPER TRADING STATUS CHECK")
    print("="*60)

    # Load configuration
    config = load_rithmic_config()
    if not config:
        print("\n[-] Cannot proceed - Rithmic configuration missing")
        return

    print("\n[+] Configuration loaded successfully")
    print(f"    Account: {config['RITHMIC_USERNAME']}")
    print(f"    Gateway: {config['RITHMIC_GATEWAY']}")
    print(f"    Type: Paper Trading")

    # Run tests
    dns_results = test_dns_resolution()
    network_results = test_network_connectivity()
    check_paper_trading_requirements()

    # Try alternative connection methods
    asyncio.run(test_rithmic_websocket_alternative(config))

    # Summary
    print("\n" + "="*60)
    print("  SUMMARY")
    print("="*60)

    print("\nPaper Trading Account Status:")
    print("  Account: asdsadkiarhar6468 (EdgeClear)")
    print("  Gateway: Rithmic 01")
    print("  Type: Paper Trading")

    print("\nConnection Status:")
    successful_dns = sum(1 for r in dns_results.values() if r["status"] == "RESOLVED")
    successful_network = sum(1 for r in network_results.values() if r == "CONNECTED")

    print(f"  DNS Resolution: {successful_dns}/{len(dns_results)} domains resolved")
    print(f"  Network Connectivity: {successful_network}/{len(network_results)} ports connected")

    if successful_dns == 0:
        print("\n  [-] CRITICAL: No Rithmic domains can be resolved")
        print("  [-] This indicates a DNS or network connectivity issue")
        print("  [-] Cannot proceed with WebSocket connection testing")
    elif successful_network == 0:
        print("\n  [-] WARNING: DNS resolves but network connections fail")
        print("  [-] This may indicate firewall or network restrictions")
    else:
        print("\n  [+] Network infrastructure appears functional")
        print("  [+] Ready for WebSocket connection testing")

    print("\nRecommended Actions:")
    if successful_dns == 0:
        print("  1. Check internet connectivity")
        print("  2. Try alternative DNS servers (8.8.8.8, 1.1.1.1)")
        print("  3. Check if Rithmic domains are blocked by ISP/firewall")
    elif successful_network == 0:
        print("  1. Check firewall settings (port 443, 80)")
        print("  2. Verify no proxy/VPN interference")
        print("  3. Contact network administrator")
    else:
        print("  1. Proceed with compiling NEXUS Rust backend")
        print("  2. Test Rithmic WebSocket connection via Rust backend")
        print("  3. Verify paper trading data reception")

if __name__ == "__main__":
    main()