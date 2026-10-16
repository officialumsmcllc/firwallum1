import os
import sys
import requests
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.store import HubStore
from core.cloudflare_bridge import get_cf_credentials

store = HubStore()
TOKEN, ACCOUNT_ID = get_cf_credentials(store)
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def setup_kill_switch_rule():
    if not TOKEN or not ACCOUNT_ID:
        print("[ERROR] Cloudflare credentials not found in settings or environment.")
        return None

    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/gateway/rules"
    rules = requests.get(url, headers=HEADERS).json().get("result", [])
    
    kill_rule = None
    for r in rules:
        if "Kill Switch" in r.get("name", ""):
            kill_rule = r
            break
            
    if kill_rule:
        print(f"Kill switch rule already exists: {kill_rule['id']}, Enabled={kill_rule['enabled']}")
        return kill_rule["id"]

    traffic_expr = 'not(any(dns.domains[*] in {"officialum1.com"}))'
    
    payload = {
        "name": "OFFICIALUM1 - Instant Internet Kill Switch",
        "description": "Completely cuts off all internet DNS resolution when account is suspended or forced renew",
        "enabled": False,
        "action": "block",
        "traffic": traffic_expr,
        "precedence": 500
    }
    
    res = requests.post(url, headers=HEADERS, json=payload).json()
    print("Create Rule Result:", res)
    if res.get("success"):
        return res["result"]["id"]
    return None

if __name__ == "__main__":
    setup_kill_switch_rule()
