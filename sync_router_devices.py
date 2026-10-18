"""
OFFICIALUM1 — Continuous Local Router & Wi-Fi Auto-Discovery Sync
Periodically sweeps the local 192.168.100.x subnet and pushes all active router
devices to the live Cloud Hub without requiring any user intervention or links.
"""
import subprocess
import time
import socket
import requests

import os

CLOUD_SYNC_URL = os.environ.get("CLOUD_SYNC_URL", "http://142.93.19.40:8088/api/wifi-devices/sync")

KNOWN_MAP = {
    "48:4D:7E:E9:25:DD": {"name": "Host PC (Firewall Admin)", "type": "Core Server Laptop (LAN)"},
    "E2:06:16:AA:1E:5F": {"name": "Infinix HOT 11 Play", "type": "Android Smartphone (Wi-Fi)"},
    "1E:91:0C:0E:DB:42": {"name": "Infinix HOT 11 Play", "type": "Android Smartphone (Wi-Fi)"},
    "9A:23:8C:65:4D:D5": {"name": "Vivo V2109", "type": "Android Smartphone (Wi-Fi)"},
    "38:BA:F8:84:F3:05": {"name": "Client PC Laptop (PC 02)", "type": "Windows Laptop (Wi-Fi)"},
    "D8:FC:92:58:8B:12": {"name": "Wireless Device (lwp0)", "type": "Wi-Fi Client"},
    "08:CC:81:18:C9:98": {"name": "Ethernet Device (Port 1)", "type": "LAN Client"},
    "5E:E4:9F:53:4E:49": {"name": "Mobile Device", "type": "Smartphone (Wi-Fi)"},
}

def trigger_arp_sweep(subnet="192.168.100."):
    """Sends ultra-light UDP pulses to refresh the Windows ARP cache for all 254 IPs."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.01)
        for i in range(2, 255):
            try:
                s.sendto(b'', (f"{subnet}{i}", 53))
            except Exception:
                pass
        s.close()
    except Exception:
        pass

def scan_and_sync():
    trigger_arp_sweep()
    time.sleep(0.5)

    try:
        out = subprocess.check_output("arp -a", shell=True, text=True, errors="ignore")
        devices = []
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0].startswith("192.168.100."):
                ip = parts[0]
                mac = parts[1].replace("-", ":").upper()
                ip_type = parts[2]
                if ip_type.lower() == "dynamic" and ip != "192.168.100.1":
                    info = KNOWN_MAP.get(mac, {})
                    name = info.get("name", f"Wi-Fi Client ({ip})")
                    dev_type = info.get("type", "Wireless Mobile / PC")
                    devices.append({
                        "ip": ip,
                        "mac": mac,
                        "name": name,
                        "type": dev_type
                    })

        # Windows 'arp -a' does not list the local host machine itself.
        # Explicitly add Host PC (192.168.100.158) so all 7 router devices are accounted for.
        host_ip = "192.168.100.158"
        host_mac = "48:4D:7E:E9:25:DD"
        if not any(d["ip"] == host_ip for d in devices):
            devices.insert(0, {
                "ip": host_ip,
                "mac": host_mac,
                "name": "Host PC (Firewall Admin)",
                "type": "Core Server Laptop (LAN)"
            })

        if devices:
            resp = requests.post(CLOUD_SYNC_URL, json={"devices": devices}, timeout=6)
            if resp.status_code == 200:
                print(f"[{time.strftime('%H:%M:%S')}] Auto-Synced {len(devices)} router devices to Cloud Hub!")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Sync error: {e}")

def run_continuous():
    print("[OFFICIALUM1] Zero-Touch Router Auto-Sync Daemon Started...")
    print("[OFFICIALUM1] Monitoring Huawei HG8245C router for newly connected devices...")
    while True:
        scan_and_sync()
        time.sleep(8)

if __name__ == "__main__":
    run_continuous()
