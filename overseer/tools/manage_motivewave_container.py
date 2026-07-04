#!/usr/bin/env python3
import sys
import os
import json
import argparse
import subprocess
import time
from pathlib import Path

# Caesar Cipher Key for MotiveWave workspace encryption
K = [255, 1, 1, 254, 254, 2, 0, 254]

def decrypt_mw_string(ciphertext):
    """Decrypt MotiveWave's Caesar-cipher-like encrypted string."""
    try:
        return "".join(chr((ord(char) - K[i % 8]) % 256) for i, char in enumerate(ciphertext))
    except Exception as e:
        print(f"Error decrypting: {e}")
        return None

def encrypt_mw_string(plaintext):
    """Encrypt plain string into MotiveWave's Caesar-cipher-like format."""
    try:
        return "".join(chr((ord(char) + K[i % 8]) % 256) for i, char in enumerate(plaintext))
    except Exception as e:
        print(f"Error encrypting: {e}")
        return None

def update_workspace_credentials(workspace_name, username, password, system_name, gateway_location):
    """Update username and password settings in a MotiveWave workspace."""
    workspace_path = Path(f"/home/jogi999/.motivewave/workspaces/{workspace_name}/config/workspace.json")
    if not workspace_path.exists():
        print(f"Error: Workspace path '{workspace_path}' does not exist.")
        return False
    
    # Read and decrypt
    encrypted_content = workspace_path.read_text().strip()
    decrypted_content = decrypt_mw_string(encrypted_content)
    if not decrypted_content:
        print("Error: Failed to decrypt workspace.json")
        return False
    
    try:
        data = json.loads(decrypted_content)
    except Exception as e:
        print(f"Error parsing decrypted JSON: {e}")
        return False
        
    # Update connection credentials
    updated = False
    if "instances" in data:
        for instance in data["instances"]:
            if "connections" in instance:
                for conn in instance["connections"]:
                    if username:
                        conn["username"] = username
                    if password:
                        conn["password"] = password
                    if system_name:
                        conn["system"] = system_name
                    if gateway_location:
                        conn["location"] = gateway_location
                    updated = True
                    
    if not updated:
        print("Warning: Connection settings not found in workspace.json. Attempting to inject them.")
        # Inject standard Rithmic structure if empty
        data["instances"] = [{
            "name": "RN",
            "id": "1jr8fjer5",
            "connections": [{
                "type": "RITHMIC_GATEWAY",
                "username": username or "desabot106@herojp.com",
                "password": password or "Nt+ELonuI4OGPRJioGWtPw==",
                "connectionType": "NON_AGG",
                "system": system_name or "Rithmic Paper Trading",
                "location": gateway_location or "Chicago",
                "services": "BROKER|REALTIME|HISTORICAL"
            }]
        }]
    
    # Re-encrypt and write back
    new_decrypted = json.dumps(data, separators=(',', ':'))
    new_encrypted = encrypt_mw_string(new_decrypted)
    
    # Backup first
    backup_path = workspace_path.with_suffix(".json.bak")
    if workspace_path.exists():
        workspace_path.rename(backup_path)
    
    workspace_path.write_text(new_encrypted)
    print(f"Successfully updated credentials for workspace '{workspace_name}'!")
    print(f"Backup saved to '{backup_path}'")
    return True

def generate_windows_json(pairs):
    """Generate a clean windows.json layout with the selected pairs and attached Java bridge study."""
    tabs = []
    for i, pair in enumerate(pairs):
        clean_symbol = pair.split(".")[0]
        # Generate a clean ID matching symbols
        tab_content = {
            "factory": "chartFactory",
            "selected": i == 0,
            "content": {
                "settings": [{"showAlertHistory": True, "showOrders": True, "showAlerts": True}],
                "accountId": "simulated",
                "graphs": [{"active": True, "analysis": ":1"}],
                "untitled": {
                    f"{pair}:1": {
                        "graphs": [
                            {
                                "figures": [
                                    {
                                        "settings": {
                                            "UdpHost": "127.0.0.1",
                                            "UdpPort": 65000,
                                            "DomDepth": 50,
                                            "MboFilter": 5,
                                            "SendTicks": True,
                                            "SendDom": True,
                                            "SendMbo": True,
                                            "DomInterval": 100,
                                            "HeartbeatMs": 2000
                                        },
                                        "id": f"overseer_bridge_{clean_symbol.lower()}",
                                        "type": "study",
                                        "ns": "com.overseer",
                                        "overlayPosition": "FULL",
                                        "sid": "OverseerMotiveWaveBridge"
                                    }
                                ]
                            }
                        ],
                        "instr": pair
                    }
                },
                "chartSettings": {"showDOM": True},
                "cfg": {
                    f"{pair}:1": {
                        "graphs": [{"top": 0, "bottom": 0}],
                        "v": 7
                    }
                },
                "v": "7",
                "instr": pair,
                "domSettings": {"width": 478, "version": "2"}
            }
        }
        tabs.append(tab_content)
        
    layout = [
        {
            "type": "console",
            "maximized": True,
            "bounds": {"x": 0, "y": 28, "width": 1366, "height": 740},
            "restoreBounds": "0,28,1366,740",
            "layout": {
                "tabLocation": "TOP",
                "showTabIcons": False,
                "pages": [
                    {
                        "pageId": "overseer_main_page",
                        "title": "OVERSEER Live Data",
                        "active": True,
                        "type": "CHART",
                        "content": {
                            "type": "station",
                            "active": True,
                            "content": {
                                "stationId": "overseer_main_station",
                                "tabs": tabs,
                                "title": "OVERSEER Live Data"
                            }
                        }
                    }
                ]
            }
        }
    ]
    return layout

def update_pairs(pairs):
    """Update config.json and windows.json in the 'hi' workspace to subscribe to the selected pairs."""
    config_path = Path("/home/jogi999/.motivewave/workspaces/hi/config/config.json")
    windows_path = Path("/home/jogi999/.motivewave/workspaces/hi/config/windows.json")
    
    if not config_path.exists() or not windows_path.exists():
        print("Error: Config or windows layout file not found in 'hi' workspace.")
        return False
        
    print(f"Configuring workspace to subscribe to: {pairs}")
    
    # 1. Update config.json
    try:
        config_data = json.loads(config_path.read_text())
        # Replace favInstrKeys and recentInstrKeys
        config_data["favInstrKeys"] = pairs
        config_data["recentInstrKeys"] = [pairs[0]] if pairs else []
        config_path.write_text(json.dumps(config_data, indent=2))
        print("Updated config.json favorite instruments.")
    except Exception as e:
        print(f"Failed to update config.json: {e}")
        return False
        
    # 2. Update windows.json
    try:
        windows_layout = generate_windows_json(pairs)
        windows_path.write_text(json.dumps(windows_layout, indent=2))
        print("Generated and updated windows.json with attached Overseer Java Bridge.")
    except Exception as e:
        print(f"Failed to update windows.json: {e}")
        return False
        
    print("Pairs configured successfully!")
    return True

def start_headless_motivewave():
    """Start MotiveWave headlessly inside the mw-box container with Openbox managing window focus."""
    print("Stopping any existing instances to avoid conflicts...")
    stop_motivewave()
    
    print("Starting Xvfb display :99...")
    log_file = "/home/jogi999/PROJECT HELL/overseer/logs/motivewave_headless.log"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # We start Xvfb ourselves in the background with access control disabled (-ac)
    xvfb_cmd = [
        "distrobox-enter", "-n", "mw-box", "--",
        "Xvfb", ":99", "-screen", "0", "1024x768x24", "-ac", "-nolisten", "tcp"
    ]
    with open(log_file, "a") as f:
        f.write(f"\n--- Headless MotiveWave started at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        subprocess.Popen(xvfb_cmd, stdout=f, stderr=f, start_new_session=True)
    
    time.sleep(2)
    
    print("Starting Openbox window manager on display :99...")
    ob_cmd = [
        "distrobox-enter", "-n", "mw-box", "--",
        "bash", "-c", "DISPLAY=:99 openbox"
    ]
    with open(log_file, "a") as f:
        subprocess.Popen(ob_cmd, stdout=f, stderr=f, start_new_session=True)
    time.sleep(2)
    
    print("Starting MotiveWave on display :99...")
    mw_cmd = [
        "distrobox-enter", "-n", "mw-box", "--",
        "bash", "-c", "DISPLAY=:99 /usr/bin/motivewave"
    ]
    with open(log_file, "a") as f:
        subprocess.Popen(mw_cmd, stdout=f, stderr=f, start_new_session=True)
        
    print("Waiting 15 seconds for MotiveWave to load the splash screen...")
    time.sleep(15)
    
    print("Locating MotiveWave window...")
    # Find window ID
    try:
        w_id_out = subprocess.check_output([
            "distrobox-enter", "-n", "mw-box", "--",
            "bash", "-c", "DISPLAY=:99 xdotool search --onlyvisible --name MotiveWave"
        ]).decode().strip()
        
        if w_id_out:
            w_id = w_id_out.split('\n')[0]
            print(f"MotiveWave window ID: {w_id}")
            
            # Fetch window geometry to calculate absolute coordinates
            geom_out = subprocess.check_output([
                "distrobox-enter", "-n", "mw-box", "--",
                "bash", "-c", f"DISPLAY=:99 xdotool getwindowgeometry {w_id}"
            ]).decode()
            
            # Parse position
            pos_line = [line for line in geom_out.split('\n') if "Position" in line][0]
            pos_str = pos_line.split("Position:")[1].split("(")[0].strip()
            wx, wy = map(int, pos_str.split(","))
            print(f"Window Position: {wx}, {wy}")
            
            # Calculate absolute button coordinates
            checkbox_x = wx + 748
            checkbox_y = wy + 297
            continue_x = wx + 808
            continue_y = wy + 221
            
            # Focus window
            subprocess.run([
                "distrobox-enter", "-n", "mw-box", "--",
                "bash", "-c", f"DISPLAY=:99 xdotool windowfocus --sync {w_id}"
            ])
            time.sleep(1)
            
            # Click Auto Connect checkbox
            print("Clicking Auto Connect checkbox...")
            subprocess.run([
                "distrobox-enter", "-n", "mw-box", "--",
                "bash", "-c", f"DISPLAY=:99 xdotool mousemove {checkbox_x} {checkbox_y} mousedown 1 sleep 0.1 mouseup 1"
            ])
            time.sleep(1)
            
            # Click Continue button
            print("Clicking Continue button...")
            subprocess.run([
                "distrobox-enter", "-n", "mw-box", "--",
                "bash", "-c", f"DISPLAY=:99 xdotool mousemove {continue_x} {continue_y} mousedown 1 sleep 0.2 mouseup 1"
            ])
            print("Clicks sent successfully!")
        else:
            print("Warning: MotiveWave window not found.")
    except Exception as e:
        print(f"Warning: Could not auto-click: {e}")
        
    print("MotiveWave start process complete. Check status to verify it connected.")
    return True

def stop_motivewave():
    """Terminate any running MotiveWave, Xvfb, and Openbox instances."""
    print("Stopping MotiveWave and virtual framebuffers...")
    
    # Terminate motivewave processes using exact command name matching to avoid self-killing
    subprocess.run(["pkill", "-x", "MotiveWave"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-x", "motivewave"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Terminate Xvfb
    subprocess.run(["pkill", "-x", "Xvfb"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Terminate openbox
    subprocess.run(["pkill", "-x", "openbox"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Clean up lock file
    subprocess.run(["distrobox-enter", "-n", "mw-box", "--", "rm", "-f", "/tmp/.X99-lock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print("Stopped.")
    return True

def show_status():
    """Print status of MotiveWave process, Xvfb, UDP port, and latest bridge logs."""
    print("--- OVERSEER Headless MotiveWave Status ---")
    
    # MotiveWave PID
    try:
        pid = subprocess.check_output(["pgrep", "-f", "MotiveWave"]).decode().strip()
        print(f"MotiveWave process: RUNNING (PID {pid})")
    except subprocess.CalledProcessError:
        print("MotiveWave process: STOPPED")
        
    # Xvfb
    try:
        xvfb_pid = subprocess.check_output(["pgrep", "-f", "Xvfb"]).decode().strip()
        print(f"Xvfb Virtual Framebuffer: RUNNING (PID {xvfb_pid})")
    except subprocess.CalledProcessError:
        print("Xvfb Virtual Framebuffer: STOPPED")
        
    # UDP Port 65000
    try:
        netstat = subprocess.check_output(["ss", "-u", "-a", "-p"]).decode()
        if "65000" in netstat:
            print("UDP Port 65000: ACTIVE")
        else:
            print("UDP Port 65000: INACTIVE")
    except Exception as e:
        print(f"Could not check UDP port status: {e}")
        
    # Bridge logs
    log_path = Path("/home/jogi999/PROJECT HELL/overseer/logs/motivewave_bridge.log")
    if log_path.exists():
        print("\n--- Latest Bridge Logs ---")
        lines = log_path.read_text().splitlines()[-15:]
        print("\n".join(lines))
    else:
        print("\nBridge log file not found at logs/motivewave_bridge.log")

def main():
    parser = argparse.ArgumentParser(description="OVERSEER Headless MotiveWave Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Credentials Command
    cred_parser = subparsers.add_parser("set-credentials", help="Update Rithmic credentials in workspace")
    cred_parser.add_argument("--username", type=str, help="Rithmic Username")
    cred_parser.add_argument("--password", type=str, help="Rithmic Encrypted Password")
    cred_parser.add_argument("--system", type=str, default="Rithmic Paper Trading", help="Rithmic System Name")
    cred_parser.add_argument("--gateway", type=str, default="Chicago", help="Gateway Location")
    
    # Pairs Command
    pairs_parser = subparsers.add_parser("set-pairs", help="Configure active pairs in workspace")
    pairs_parser.add_argument("--pairs", nargs="+", required=True, help="Space-separated list of symbols (e.g., 6EU6.CME.RITHMIC 6BU6.CME.RITHMIC)")
    
    # Control Commands
    subparsers.add_parser("start", help="Start headless MotiveWave")
    subparsers.add_parser("stop", help="Stop headless MotiveWave")
    subparsers.add_parser("status", help="Show current status")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
        
    if args.command == "set-credentials":
        # Update both default and hi workspaces
        update_workspace_credentials("hi", args.username, args.password, args.system, args.gateway)
        update_workspace_credentials("default", args.username, args.password, args.system, args.gateway)
        
    elif args.command == "set-pairs":
        update_pairs(args.pairs)
        
    elif args.command == "start":
        start_headless_motivewave()
        
    elif args.command == "stop":
        stop_motivewave()
        
    elif args.command == "status":
        show_status()

if __name__ == "__main__":
    main()
