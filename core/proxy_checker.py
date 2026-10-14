"""
OFFICIALUM1 — Proxy Health & Exit IP Checker
Validates upstream SOCKS5 and HTTP proxies, measures latency, and resolves public exit IP & location.
"""

import time
import requests
from typing import Dict, Any, Optional

def test_proxy_connection(protocol: str, host: str, port: int, username: str = "", password: str = "", timeout: float = 6.0) -> Dict[str, Any]:
    """
    Tests upstream proxy, measures round-trip latency, and discovers the public Exit IP and country.
    """
    protocol = protocol.lower().strip()
    if protocol not in ("socks5", "http", "socks5h"):
        protocol = "socks5"

    # Construct proxy URL
    if username and password:
        proxy_url = f"{protocol}://{username}:{password}@{host}:{port}"
    else:
        proxy_url = f"{protocol}://{host}:{port}"

    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }

    t0 = time.perf_counter()
    try:
        # Use ip-api.com for IP + Country + ISP details
        resp = requests.get(
            "http://ip-api.com/json/?fields=status,message,country,city,query,org,hosting",
            proxies=proxies,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 OFFICIALUM1-HealthCheck"}
        )
        latency = (time.perf_counter() - t0) * 1000

        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "success": True,
                    "exit_ip": data.get("query", "Unknown"),
                    "country": data.get("country", "Unknown"),
                    "city": data.get("city", ""),
                    "isp": data.get("org", ""),
                    "is_hosting": data.get("hosting", False),
                    "latency_ms": round(latency, 1),
                    "status": "ONLINE"
                }

        # Fallback to ipify if ip-api rate-limited
        resp2 = requests.get(
            "https://api.ipify.org?format=json",
            proxies=proxies,
            timeout=timeout
        )
        latency = (time.perf_counter() - t0) * 1000
        if resp2.status_code == 200:
            ip = resp2.json().get("ip", "Unknown")
            return {
                "success": True,
                "exit_ip": ip,
                "country": "Online",
                "city": "",
                "isp": "",
                "is_hosting": False,
                "latency_ms": round(latency, 1),
                "status": "ONLINE"
            }

    except Exception as e:
        return {
            "success": False,
            "exit_ip": "Failed",
            "country": "Offline",
            "city": "",
            "isp": "",
            "latency_ms": 0,
            "status": "OFFLINE",
            "error": str(e)
        }

    return {
        "success": False,
        "exit_ip": "Failed",
        "country": "Offline",
        "city": "",
        "isp": "",
        "latency_ms": 0,
        "status": "OFFLINE",
        "error": "No response from proxy"
    }

def start_proxy_watchdog(store, interval_sec: int = 180):
    """Background watchdog periodically validates assigned proxies and updates status."""
    import threading
    def _watchdog_loop():
        time.sleep(15)  # Initial boot grace period
        while True:
            try:
                proxies = store.get_proxies()
                for pr in proxies:
                    res = test_proxy_connection(
                        pr.get("protocol", "socks5"),
                        pr.get("host", ""),
                        int(pr.get("port", 1080)),
                        pr.get("username", ""),
                        pr.get("password", ""),
                        timeout=5.0
                    )
                    store.update_proxy_result(
                        proxy_id=pr["id"],
                        exit_ip=res.get("exit_ip", pr.get("exit_ip", "Unknown")),
                        country=res.get("country", pr.get("country", "Unknown")),
                        latency_ms=res.get("latency_ms", 0.0),
                        status=res.get("status", "OFFLINE")
                    )
            except Exception:
                pass
            time.sleep(interval_sec)

    t = threading.Thread(target=_watchdog_loop, daemon=True)
    t.start()
    return t
