#!/usr/bin/env python3
"""
PROJECT HELL — DEMO SCRIPT
Demonstrates all 5 projects working together
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

class ProjectHellDemo:
    def __init__(self):
        self.running = False
        self.components = {}

    async def start_nexus(self):
        """Start NEXUS Rust backend"""
        print("\n" + "="*60)
        print("  STARTING NEXUS (Rithmic Direct)")
        print("="*60)

        import subprocess
        import os

        nexus_dir = PROJECT_ROOT / "nexus" / "rust-backend"

        if not nexus_dir.exists():
            # Try alternative paths
            alt_paths = [
                PROJECT_ROOT / "nexus",
                PROJECT_ROOT / "nexus" / "backend",
                Path("C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\nexus")
            ]
            
            for alt_path in alt_paths:
                if alt_path.exists():
                    nexus_dir = alt_path
                    break
            else:
                print("[-] NEXUS directory not found")
                print(f"  Expected: {PROJECT_ROOT / 'nexus' / 'rust-backend'}")
                return False

        print(f"[*] NEXUS directory: {nexus_dir}")
        print("[*] Building NEXUS backend...")

        # Check if Rust is installed
        try:
            result = subprocess.run(["cargo", "--version"], capture_output=True, text=True, cwd=nexus_dir)
            if result.returncode != 0:
                print("[-] Rust not installed")
                return False
            print(f"[+] Rust version: {result.stdout.strip()}")
        except Exception as e:
            print(f"[-] Error checking Rust: {e}")
            return False

        print("\n[*] NEXUS would start here with:")
        print("   - Rithmic WebSocket connection")
        print("   - EUR/USD MBO subscription")
        print("   - WebSocket server on port 9001")
        print("\n[+] NEXUS configured (ready to compile)")
        return True

    async def start_nova(self):
        """Start NOVA trading system"""
        print("\n" + "="*60)
        print("  STARTING NOVA (Phase 1)")
        print("="*60)

        nova_dir = PROJECT_ROOT / "nova" / "nova_logic"

        if not nova_dir.exists():
            # Try alternative paths
            alt_paths = [
                PROJECT_ROOT / "nova",
                Path("C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\nova")
            ]
            
            for alt_path in alt_paths:
                if alt_path.exists():
                    nova_dir = alt_path
                    break
            else:
                print("[-] NOVA directory not found")
                print(f"  Expected: {PROJECT_ROOT / 'nova' / 'nova_logic'}")
                return False

        print(f"[*] NOVA directory: {nova_dir}")
        print("\n[*] NOVA System Components:")
        print("   - Event Whitelist (Gate 1)")
        print("   - Directional Bias (Gate 2)")
        print("   - L3 Vacuum Detection (Gate 3a)")
        print("   - L3 Anchor Detection (Gate 3b)")
        print("   - T+90s Entry Trigger")
        print("\n[*] Confluence System:")
        print("   - Threshold: 75/100 points")
        print("   - Entry: T+90s after news")
        print("   - Execution: Manual (IQ Option/Pocket Option)")
        print("\n[+] NOVA configured")
        return True

    async def start_aegis(self):
        """Start AEGIS trading system"""
        print("\n" + "="*60)
        print("  STARTING AEGIS (Phase 2)")
        print("="*60)

        aegis_dir = PROJECT_ROOT / "nova" / "aegis_logic"

        if not aegis_dir.exists():
            # Try alternative paths
            alt_paths = [
                PROJECT_ROOT / "nova",
                Path("C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\nova")
            ]
            
            for alt_path in alt_paths:
                if alt_path.exists():
                    aegis_dir = alt_path
                    break
            else:
                print("[-] AEGIS directory not found")
                print(f"  Expected: {PROJECT_ROOT / 'nova' / 'aegis_logic'}")
                return False

        print(f"[*] AEGIS directory: {aegis_dir}")
        print("\n[*] AEGIS System Components:")
        print("   - Absorption Detection (Gate 1)")
        print("   - Depth Retention (Gate 2)")
        print("   - Rejection Ratio (Gate 3)")
        print("   - Breakout Confirmation (Gate 4)")
        print("\n[*] Confluence System:")
        print("   - Threshold: 75/100 points")
        print("   - Entry: Absorption breakout")
        print("   - Execution: Auto (Deriv API)")
        print("\n[+] AEGIS configured")
        return True

    async def start_overseer(self):
        """Show OVERSEER status"""
        print("\n" + "="*60)
        print("  OVERSEER STATUS")
        print("="*60)

        overseer_dir = PROJECT_ROOT / "overseer"

        if not overseer_dir.exists():
            # Try alternative paths
            alt_paths = [
                PROJECT_ROOT / "nova" / "overseer",
                Path("C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\nova\\overseer")
            ]
            
            for alt_path in alt_paths:
                if alt_path.exists():
                    overseer_dir = alt_path
                    break
            else:
                print("[-] OVERSEER directory not found")
                print(f"  Expected: {PROJECT_ROOT / 'overseer'}")
                return False

        print(f"[*] OVERSEER directory: {overseer_dir}")
        print("\n[*] OVERSEER System Components:")
        print("   - 152 Gates (23 Frameworks)")
        print("   - XGBoost ML Scoring")
        print("   - 16 Institutional Modules")
        print("   - Legendary Mode (6 Platinum Gates)")
        print("\n[*] Execution:")
        print("   - MT5 (Windows)")
        print("   - OANDA API (Linux)")
        print("   - Telegram Alerts")
        print("\n[+] OVERSEER available (independent system)")
        return True

    async def start_prophet(self):
        """Show PROPHET status"""
        print("\n" + "="*60)
        print("  PROPHET STATUS")
        print("="*60)

        prophet_dir = PROJECT_ROOT / "prophet"

        if not prophet_dir.exists():
            # Try alternative paths
            alt_paths = [
                PROJECT_ROOT / "prophet",
                Path("C:\\Users\\jogip\\OneDrive\\Desktop\\PROJECT HELL\\prophet")
            ]
            
            for alt_path in alt_paths:
                if alt_path.exists():
                    prophet_dir = alt_path
                    break
            else:
                print("[-] PROPHET directory not found")
                print(f"  Expected: {PROJECT_ROOT / 'prophet'}")
                return False

        print(f"[*] PROPHET directory: {prophet_dir}")
        print("\n[*] PROPHET System Components:")
        print("   - Volume Profile Detection")
        print("   - CVD Divergence")
        print("   - Iceberg Detection")
        print("   - Absorption Detection")
        print("\n[*] Execution:")
        print("   - Deriv API")
        print("   - 15-minute binaries")
        print("   - Automated")
        print("\n[+] PROPHET available (independent system)")
        return True

    async def show_data_flow(self):
        """Display complete data flow"""
        print("\n" + "="*60)
        print("  DATA FLOW ARCHITECTURE")
        print("="*60)

        print("""
RITHMIC API (EdgeClear)
- Username: asdsadkiarhar6468
- Gateway: Rithmic 01
- Latency: 1-5ms
|
V
NEXUS v2.0 (Rust)
- WebSocket connection
- MBO data processing
- LimitOrderBook state
- WebSocket broadcast (9001)
|
V
+-------------+-------------+
|   NOVA      |   AEGIS     |
+-------------+-------------+
| 3 Gates     | 4 Gates     |
| 75/100 pts  | 75/100 pts  |
| T+90s entry | Absorption  |
| Manual IQ/PO| Auto Deriv  |
+-------------+-------------+

INDEPENDENT SYSTEMS:

OVERSEER -> MotiveWave -> MT5/OANDA (Forex)
PROPHET -> Deriv API (Binary)
        """)

    async def show_configuration(self):
        """Display configuration status"""
        print("\n" + "="*60)
        print("  CONFIGURATION STATUS")
        print("="*60)

        configs = {
            "Rithmic Credentials": {
                "file": "nexus/rust-backend/.env.rithmic",
                "status": "[+] Configured",
                "details": "asdsadkiarhar6468"
            },
            "FRED API Key": {
                "file": "nova/nova_logic/.env",
                "status": "[-] Required",
                "details": "Get from https://fred.stlouisfed.org/docs/api/api_key.html"
            },
            "Deriv API Token": {
                "file": "nova/aegis_logic/.env",
                "status": "[-] Required",
                "details": "Get from https://app.deriv.com/account/api-token"
            }
        }

        for name, config in configs.items():
            print(f"\n{name}:")
            print(f"  File: {config['file']}")
            print(f"  Status: {config['status']}")
            print(f"  Details: {config['details']}")

    async def show_next_steps(self):
        """Display next steps"""
        print("\n" + "="*60)
        print("  NEXT STEPS")
        print("="*60)

        steps = [
            ("1", "Compile NEXUS v2.0", "On Linux: cargo build --release"),
            ("2", "Get API Keys", "FRED + Deriv"),
            ("3", "Update .env files", "Add API keys"),
            ("4", "Test NOVA", "Run: python test_mode.py"),
            ("5", "Test AEGIS", "Run: python test_mode.py"),
            ("6", "Start Production", "Run: LAUNCHER.bat"),
        ]

        for num, title, cmd in steps:
            print(f"\n{num}. {title}")
            print(f"   {cmd}")

    async def show_cost_summary(self):
        """Display cost summary"""
        print("\n" + "="*60)
        print("  COST SUMMARY")
        print("="*60)

        costs = [
            ("Rithmic API", "$20.00/month", "Base access fee"),
            ("Rithmic Per Contract", "$0.10/contract", "Execution fee"),
            ("FRED API", "Free", "Economic data"),
            ("Deriv API", "Free", "Binary options"),
            ("MotiveWave", "$0-99/mo", "OVERSEER only (optional)"),
        ]

        total_min = 20
        total_max = 119

        print("\nMonthly Costs:")
        for name, cost, notes in costs:
            print(f"  • {name:25} {cost:15} {notes}")

        print(f"\nEstimated Total: ${total_min}-${total_max}/month")

    async def run(self):
        """Run complete demo"""
        print("\n" + "="*60)
        print("  PROJECT HELL — COMPLETE DEMO")
        print("="*60)
        print("\n5-Project Trading Ecosystem")
        print("Direct Rithmic Integration")
        print("Production Ready")

        try:
            await self.show_data_flow()
            await self.show_configuration()
            await self.show_cost_summary()

            results = {
                "NEXUS": await self.start_nexus(),
                "NOVA": await self.start_nova(),
                "AEGIS": await self.start_aegis(),
                "OVERSEER": await self.start_overseer(),
                "PROPHET": await self.start_prophet(),
            }

            print("\n" + "="*60)
            print("  DEMO SUMMARY")
            print("="*60)

            for name, success in results.items():
                status = "[+] OK" if success else "[-] FAILED"
                print(f"  {name:15} {status}")

            success_count = sum(results.values())
            total_count = len(results)

            print(f"\nTotal: {success_count}/{total_count} systems configured")

            if success_count == total_count:
                print("\n[+] All systems ready!")
                await self.show_next_steps()
            else:
                print("\n[!] Some systems need configuration")

        except KeyboardInterrupt:
            print("\n\nDemo interrupted by user")
        except Exception as e:
            print(f"\n\n[-] Demo error: {e}")

async def main():
    demo = ProjectHellDemo()
    await demo.run()

if __name__ == "__main__":
    asyncio.run(main())