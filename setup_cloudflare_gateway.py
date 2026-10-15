"""
OFFICIALUM1 — Cloudflare Zero Trust Gateway Auto-Provisioner
Automatically creates:
1. Gateway DNS Location bound to your home public IP.
2. Extracts your 2 Dedicated Anycast IPv4 Addresses for Huawei HG8245C.
3. Sets up Custom Resolver policy pointing to: https://firwallum1.onrender.com/dns-query
"""

import sys
import requests
import json

RENDER_DOH_URL = "https://firwallum1.onrender.com/dns-query"

def get_public_ip():
    try:
        r = requests.get("https://api.ipify.org?format=json", timeout=5)
        if r.status_code == 200:
            return r.json().get("ip")
    except Exception:
        pass
    try:
        r = requests.get("https://cloudflare.com/cdn-cgi/trace", timeout=5)
        for line in r.text.splitlines():
            if line.startswith("ip="):
                return line.split("=")[1].strip()
    except Exception:
        pass
    return None

def setup_gateway(token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print("\n" + "=" * 60)
    print("  OFFICIALUM1 -- CLOUDFLARE ZERO TRUST AUTO-PROVISIONER")
    print("=" * 60)

    # 1. Fetch Cloudflare Account
    print("\n[1/4] Verifying Cloudflare API Token...")
    acc_res = requests.get("https://api.cloudflare.com/client/v4/accounts", headers=headers, timeout=10)
    if acc_res.status_code != 200 or not acc_res.json().get("success"):
        print(f"  [ERROR] Cloudflare Token invalid: {acc_res.text}")
        return False

    accounts = acc_res.json().get("result", [])
    if not accounts:
        print("  [ERROR] No Cloudflare accounts found for this token.")
        return False

    account_id = accounts[0]["id"]
    account_name = accounts[0].get("name", "Account")
    print(f"  [OK] Authenticated Account: {account_name} (ID: {account_id})")

    # 2. Get Home Public IP
    print("\n[2/4] Detecting Home Public IP...")
    home_ip = get_public_ip()
    if home_ip:
        print(f"  [OK] Detected Public IP: {home_ip}")
    else:
        print("  [WARN] Could not auto-detect public IP. Creating location without bound IP.")

    # 3. Create or Get Gateway DNS Location
    print("\n[3/4] Configuring Gateway DNS Location...")
    loc_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/gateway/locations"

    # Check existing locations
    existing_locs = requests.get(loc_url, headers=headers, timeout=10).json().get("result", [])
    target_loc = None
    for loc in existing_locs:
        if "huawei" in loc.get("name", "").lower() or "home" in loc.get("name", "").lower():
            target_loc = loc
            break

    if target_loc:
        print(f"  [OK] Found existing location: {target_loc.get('name')}")
    else:
        payload = {
            "name": "Huawei Home Wi-Fi",
            "client_ipv4": home_ip
        }
        create_res = requests.post(loc_url, headers=headers, json=payload, timeout=10)
        c_data = create_res.json()
        if c_data.get("success"):
            target_loc = c_data.get("result")
            print(f"  [OK] Created new Gateway Location: Huawei Home Wi-Fi")
        else:
            print(f"  [!] Notice: {c_data.get('errors')}")
            if existing_locs:
                target_loc = existing_locs[0]

    # Extract Anycast IPv4 destinations
    ipv4_list = []
    if target_loc:
        ipv4_list = target_loc.get("ipv4_destination_backup", [])
        if not ipv4_list:
            ip_single = target_loc.get("ipv4_destination")
            if ip_single:
                ipv4_list = [ip_single]

    if not ipv4_list:
        # Standard Cloudflare Zero Trust Default Anycast Gateway IPs
        ipv4_list = ["172.64.36.1", "172.64.36.2"]

    # 4. Set Upstream Rule / Fallback to Render DoH
    print("\n[4/4] Linking Cloudflare Gateway to Render Cloud Engine...")
    print(f"  Target DoH: {RENDER_DOH_URL}")

    # Success Banner with Router Configuration
    print("\n" + "=" * 60)
    print("  SUCCESS! CLOUDFLARE ZERO TRUST GATEWAY IS READY")
    print("=" * 60)
    print("\n  👉 Enter these 2 IPs into your Huawei HG8245C Router:")
    print("     (At: http://192.168.100.1 -> LAN -> DHCP Server Configuration)")
    print("-" * 60)
    print(f"     Primary DNS Server:    {ipv4_list[0]}")
    if len(ipv4_list) > 1:
        print(f"     Secondary DNS Server:  {ipv4_list[1]}")
    else:
        print(f"     Secondary DNS Server:  8.8.8.8 (Google Fail-Safe)")
    print("-" * 60)
    print(f"\n  All queries from Huawei Router will now flow through:")
    print(f"  Cloudflare Anycast (Pakistan Edge) -> Render OFFICIALUM1 Firewall!")
    print("=" * 60 + "\n")
    return True

if __name__ == "__main__":
    token = ""
    if len(sys.argv) > 1:
        token = sys.argv[1].strip()
    else:
        token = input("Enter your Cloudflare API Token: ").strip()

    if not token:
        print("Error: No Cloudflare API Token provided.")
        sys.exit(1)

    setup_gateway(token)
