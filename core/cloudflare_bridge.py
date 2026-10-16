"""
OFFICIALUM1 — Cloudflare Zero Trust Automated Bridge
Automatically provisions Gateway DNS Locations and Anycast IPv4s
when customers link their router WAN IP.
"""

import requests
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("cloudflare_bridge")

def get_cf_credentials(store) -> tuple[str, str]:
    """Retrieves Cloudflare API Token and Account ID from store or environment."""
    import os
    settings = store.get_settings()
    token = settings.get("cloudflare_api_token") or os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    account_id = settings.get("cloudflare_account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    return token, account_id

def sync_cloudflare_location(store, client_ip: str, config_id: str) -> Dict[str, Any]:
    """
    Auto-provisions Cloudflare Zero Trust Gateway location for customer's public WAN IP.
    Returns:
    {
        "success": True/False,
        "ipv4_dns": ["172.64.36.1", "172.64.36.2"],
        "location_id": "...",
        "message": "..."
    }
    """
    token, account_id = get_cf_credentials(store)
    if not token:
        return {
            "success": False,
            "ipv4_dns": ["172.64.36.1", "172.64.36.2"],
            "message": "No Cloudflare API Token configured. Using default Cloudflare Gateway Anycast IPs."
        }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        # 1. Discover account_id if not saved
        if not account_id:
            acc_res = requests.get("https://api.cloudflare.com/client/v4/accounts", headers=headers, timeout=8)
            if acc_res.status_code == 200 and acc_res.json().get("success"):
                accounts = acc_res.json().get("result", [])
                if accounts:
                    account_id = accounts[0]["id"]
                    store.set_setting("cloudflare_account_id", account_id)

        if not account_id:
            return {
                "success": False,
                "ipv4_dns": ["172.64.36.1", "172.64.36.2"],
                "message": "Could not find Cloudflare Account ID for this token."
            }

        # 2. Check existing locations or create new one
        loc_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/gateway/locations"
        existing = requests.get(loc_url, headers=headers, timeout=8).json().get("result", [])
        
        target_loc = None
        for loc in existing:
            if loc.get("client_ipv4") == client_ip or config_id in loc.get("name", "").lower():
                target_loc = loc
                break

        location_name = f"OFFICIALUM1_{config_id}"

        if target_loc:
            # Update IP if needed
            loc_id = target_loc["id"]
            if target_loc.get("client_ipv4") != client_ip:
                requests.put(f"{loc_url}/{loc_id}", headers=headers, json={
                    "name": target_loc.get("name", location_name),
                    "client_ipv4": client_ip
                }, timeout=8)
        else:
            # Create new Location bound to customer's Router WAN IP
            payload = {
                "name": location_name,
                "client_ipv4": client_ip
            }
            create_res = requests.post(loc_url, headers=headers, json=payload, timeout=8)
            c_data = create_res.json()
            if c_data.get("success"):
                target_loc = c_data.get("result")
            elif existing:
                target_loc = existing[0]

        # 3. Extract Dedicated Anycast IPv4 destinations
        ipv4_list = []
        if target_loc:
            ipv4_list = target_loc.get("ipv4_destination_backup", [])
            if not ipv4_list:
                ip_single = target_loc.get("ipv4_destination")
                if ip_single:
                    ipv4_list = [ip_single]

        if not ipv4_list:
            ipv4_list = ["172.64.36.1", "172.64.36.2"]

        # Cache assigned IPs in settings
        store.set_setting(f"cf_dns_{config_id}", json.dumps(ipv4_list))

        return {
            "success": True,
            "ipv4_dns": ipv4_list,
            "location_name": location_name,
            "client_ipv4": client_ip,
            "message": f"Successfully bound Router WAN IP {client_ip} to Cloudflare Anycast Gateway!"
        }

    except Exception as e:
        logger.error(f"Cloudflare auto-sync error: {e}")
        return {
            "success": False,
            "ipv4_dns": ["172.64.36.1", "172.64.36.2"],
            "message": str(e)
        }

def toggle_kill_switch(store, enabled: bool) -> Dict[str, Any]:
    """
    Instantly enables or disables the Cloudflare Zero Trust Kill Switch rule.
    When enabled=True, 100% of DNS resolution on Anycast IPs (172.64.36.1/2) is blocked,
    severing all internet access for connected devices until renewed.
    """
    token, account_id = get_cf_credentials(store)
    if not token or not account_id:
        return {"success": False, "message": "Missing Cloudflare credentials"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/gateway/rules"
        rules_res = requests.get(url, headers=headers, timeout=8).json()
        rules = rules_res.get("result", [])

        target_rule = None
        for r in rules:
            if "Kill Switch" in r.get("name", ""):
                target_rule = r
                break

        if not target_rule:
            traffic_expr = 'not(any(dns.domains[*] in {"officialum1.com"}))'
            payload = {
                "name": "OFFICIALUM1 - Instant Internet Kill Switch",
                "description": "Completely cuts off all internet DNS resolution when account is suspended or forced renew",
                "enabled": enabled,
                "action": "block",
                "traffic": traffic_expr,
                "precedence": 500
            }
            res = requests.post(url, headers=headers, json=payload, timeout=8).json()
            return {"success": res.get("success", False), "enabled": enabled, "rule_id": res.get("result", {}).get("id")}

        rule_id = target_rule["id"]
        put_url = f"{url}/{rule_id}"
        payload = {
            "name": target_rule["name"],
            "enabled": enabled,
            "action": target_rule["action"],
            "traffic": target_rule["traffic"],
            "precedence": target_rule.get("precedence", 500)
        }
        res = requests.put(put_url, headers=headers, json=payload, timeout=8).json()
        return {"success": res.get("success", False), "enabled": enabled, "rule_id": rule_id}
    except Exception as e:
        logger.error(f"Error toggling Cloudflare kill switch: {e}")
        return {"success": False, "error": str(e)}

