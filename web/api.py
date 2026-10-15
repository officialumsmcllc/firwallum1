"""
OFFICIALUM1 — Clean REST API for Management Dashboard
"""

import socket
import time
import threading
import subprocess
from flask import Blueprint, jsonify, request
from core.store import HubStore
from core.proxy_checker import test_proxy_connection

# Friendly names mapped to MAC addresses from router & network discovery
KNOWN_DEVICE_MAP = {
    "E2:06:16:AA:1E:5F": {"name": "Infinix HOT 11 Play", "type": "Android Smartphone (Wi-Fi)"},
    "9A:23:8C:65:4D:D5": {"name": "Vivo V2109", "type": "Android Smartphone (Wi-Fi)"},
    "38:BA:F8:84:F3:05": {"name": "Client PC Laptop (PC 02)", "type": "Windows Laptop (Wi-Fi)"},
    "D8:FC:92:58:8B:12": {"name": "Wireless Device (lwp0)", "type": "Wi-Fi Client"},
    "08:CC:81:18:C9:98": {"name": "Ethernet Device (Port 1)", "type": "LAN Client"},
    "1E:91:0C:0E:DB:42": {"name": "Mobile Device", "type": "Smartphone (Wi-Fi)"},
    "5E:E4:9F:53:4E:49": {"name": "Mobile Device", "type": "Smartphone (Wi-Fi)"},
}

_last_sweep_time = 0
_sweep_lock = threading.Lock()

def _trigger_subnet_sweep(subnet="192.168.100."):
    """Fast non-blocking UDP sweep to keep Windows ARP cache freshly populated."""
    global _last_sweep_time
    now = time.time()
    with _sweep_lock:
        if now - _last_sweep_time < 8:
            return
        _last_sweep_time = now

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i in range(2, 255):
            try:
                s.sendto(b'', (f"{subnet}{i}", 53))
            except Exception:
                pass
        s.close()
    except Exception:
        pass

def _background_arp_scanner():
    while True:
        try:
            _trigger_subnet_sweep()
        except Exception:
            pass
        time.sleep(20)

threading.Thread(target=_background_arp_scanner, daemon=True).start()

def create_api_blueprint(store: HubStore, dns_firewall) -> Blueprint:
    api = Blueprint("api", __name__, url_prefix="/api")

    @api.route("/status", methods=["GET"])
    def get_status():
        config_id = request.args.get("config", "default")
        settings = store.get_settings()
        ports = store.get_ports()
        cfg = store.get_or_create_config(config_id)
        is_active = store.is_config_active(config_id)
        active_count = sum(1 for p in ports if p.get("status") == "ACTIVE")
        dns_clients = dns_firewall.get_active_clients() if dns_firewall else []
        total_active = max(active_count, len(dns_clients))
        return jsonify({
            "status": "ONLINE" if is_active else "SUSPENDED",
            "hub_ip": settings.get("hub_ip", "127.0.0.1"),
            "config_id": config_id,
            "config_name": cfg.get("name", "OfficialUM1 Network Shield"),
            "is_active": is_active,
            "plan_tier": cfg.get("plan_tier", "home_pro"),
            "expires_at": cfg.get("expires_at", 0),
            "total_ports": len(ports),
            "active_devices": total_active,
            "proxy_active_count": active_count,
            "dns_clients": dns_clients,
            "dns_clients_count": len(dns_clients),
            "dns_adblock": cfg.get("adblock_enabled", 1) == 1 and settings.get("dns_adblock_enabled") == "1",
            "proxy_gateway_enabled": settings.get("proxy_gateway_enabled", "1") == "1",
            "adult_block_enabled": cfg.get("adult_block_enabled", 1) == 1 and settings.get("adult_block_enabled", "1") == "1",
            "smart_tv_shield": cfg.get("smart_tv_shield", 1) == 1,
            "blocked_domains_count": len(dns_firewall.blocked_domains) if dns_firewall else 0,
            "adult_domains_count": len(dns_firewall.adult_blocked_domains) if dns_firewall else 0
        })

    @api.route("/ports", methods=["GET"])
    def get_ports():
        ports = store.get_ports()
        from core.store import traffic_tracker
        for p in ports:
            st = traffic_tracker.get_stats(str(p["port"]))
            p["speed_kbps"] = st["speed_kbps"]
            p["total_mb"] = st["total_mb"]
        return jsonify({"ports": ports})

    @api.route("/ports/update", methods=["POST"])
    def update_port():
        data = request.json or {}
        port = data.get("port")
        if not port:
            return jsonify({"error": "Missing port"}), 400

        rate_limit = data.get("rate_limit_mbps")
        store.update_port(
            port=int(port),
            device_name=data.get("device_name"),
            proxy_id=data.get("proxy_id"),
            rate_limit_mbps=float(rate_limit) if rate_limit is not None else None
        )
        return jsonify({"status": "success", "port": port})

    @api.route("/proxies", methods=["GET"])
    def get_proxies():
        return jsonify({"proxies": store.get_proxies()})

    @api.route("/proxies/add", methods=["POST"])
    def add_proxy():
        data = request.json or {}
        name = data.get("name", "Residential Proxy")
        protocol = data.get("protocol", "socks5")
        host = data.get("host", "").strip()
        port = data.get("port")
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        if not host or not port:
            return jsonify({"error": "Host and Port are required"}), 400

        pid = store.add_proxy(name, protocol, host, int(port), username, password)

        # Immediate background test
        result = test_proxy_connection(protocol, host, int(port), username, password)
        store.update_proxy_result(
            proxy_id=pid,
            exit_ip=result.get("exit_ip", "Unknown"),
            country=result.get("country", "Unknown"),
            latency_ms=result.get("latency_ms", 0),
            status=result.get("status", "UNTESTED")
        )

        return jsonify({"status": "added", "id": pid, "test": result})

    @api.route("/proxies/test", methods=["POST"])
    def test_proxy():
        data = request.json or {}
        pid = data.get("id")
        if not pid:
            return jsonify({"error": "Missing proxy id"}), 400

        proxies = store.get_proxies()
        target = next((p for p in proxies if p["id"] == int(pid)), None)
        if not target:
            return jsonify({"error": "Proxy not found"}), 404

        result = test_proxy_connection(
            target["protocol"],
            target["host"],
            target["port"],
            target.get("username", ""),
            target.get("password", "")
        )

        store.update_proxy_result(
            proxy_id=target["id"],
            exit_ip=result.get("exit_ip", "Unknown"),
            country=result.get("country", "Unknown"),
            latency_ms=result.get("latency_ms", 0),
            status=result.get("status", "UNTESTED")
        )

        return jsonify({"status": "tested", "result": result})

    @api.route("/proxies/delete", methods=["DELETE"])
    def delete_proxy():
        pid = request.args.get("id")
        if not pid:
            return jsonify({"error": "Missing proxy id"}), 400
        store.delete_proxy(int(pid))
        return jsonify({"status": "deleted"})

    @api.route("/settings/toggle-adblock", methods=["POST"])
    def toggle_adblock():
        curr = store.get_settings().get("dns_adblock_enabled") == "1"
        new_val = "0" if curr else "1"
        store.set_setting("dns_adblock_enabled", new_val)
        return jsonify({"status": "updated", "dns_adblock": new_val == "1"})

    @api.route("/settings/toggle-proxy-gateway", methods=["POST"])
    def toggle_proxy_gateway():
        curr = store.get_settings().get("proxy_gateway_enabled", "1") == "1"
        new_val = "0" if curr else "1"
        store.set_setting("proxy_gateway_enabled", new_val)
        return jsonify({"status": "updated", "proxy_gateway_enabled": new_val == "1"})

    @api.route("/settings/toggle-adult-block", methods=["POST"])
    def toggle_adult_block():
        curr = store.get_settings().get("adult_block_enabled", "1") == "1"
        new_val = "0" if curr else "1"
        store.set_setting("adult_block_enabled", new_val)
        return jsonify({"status": "updated", "adult_block_enabled": new_val == "1"})

    @api.route("/wifi-devices", methods=["GET"])
    def get_wifi_devices():
        config_id = request.args.get("config", "default")
        dns_clients = dns_firewall.get_active_clients(timeout_sec=600) if dns_firewall else []
        hub_ip = store.get_settings().get("hub_ip", "192.168.100.158")

        # 1. Start with persistent Router & Wi-Fi inventory from store for this config
        stored_devs = store.get_wifi_devices(config_id=config_id)
        dev_map = {d["ip"]: dict(d) for d in stored_devs}

        # 2. Add/update dynamic ARP clients if on local Windows
        import platform
        if platform.system() == "Windows" and config_id in ("default", "all"):
            try:
                out = subprocess.check_output("arp -a", shell=True, text=True, errors="ignore", timeout=0.8)
                for line in out.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[0].startswith("192.168.100."):
                        ip = parts[0]
                        mac = parts[1].replace("-", ":").upper()
                        ip_type = parts[2]
                        if ip_type.lower() == "dynamic" and ip not in ("192.168.100.1", hub_ip):
                            info = KNOWN_DEVICE_MAP.get(mac, {})
                            dev_name = info.get("name", f"Wi-Fi Client ({ip})")
                            dev_type = info.get("type", "Wireless Mobile / PC")
                            store.upsert_wifi_device(ip=ip, name=dev_name, mac=mac, dev_type=dev_type, config_id="default")
                            if ip not in dev_map:
                                dev_map[ip] = {
                                    "ip": ip, "mac": mac, "name": dev_name, "type": dev_type,
                                    "status": "SHIELDED", "assigned_port": store.get_port_for_client_ip(ip),
                                    "bytes_used": 150000000, "config_id": "default"
                                }
            except Exception:
                pass

        # 3. Add live cloud DNS clients
        for raw_entry in dns_clients:
            if raw_entry not in ("192.168.100.1", hub_ip, "127.0.0.1", "::1"):
                parts = raw_entry.split(" - ")
                dev_ip = parts[0]
                dev_name = parts[1] if len(parts) > 1 else f"Wi-Fi Client ({dev_ip})"
                dev_type = "Smart TV (Wi-Fi Streaming)" if any(t in dev_name.lower() for t in ("tv", "samsung", "lg", "bravia")) else ("Gaming Console (Wi-Fi)" if any(c in dev_name.lower() for c in ("ps5", "xbox", "switch")) else "Active Wi-Fi Device")
                if dev_ip not in dev_map:
                    store.upsert_wifi_device(ip=raw_entry, name=dev_name, mac="--", dev_type=dev_type, config_id=config_id, initial_bytes=180000000)
                    dev_map[raw_entry] = {
                        "ip": raw_entry, "mac": "--", "name": dev_name, "type": dev_type,
                        "status": "SHIELDED", "assigned_port": store.get_port_for_client_ip(raw_entry),
                        "bytes_used": 180000000, "config_id": config_id
                    }

        from core.store import traffic_tracker
        devices = []
        for ip, d in dev_map.items():
            is_blk = store.is_client_blocked(d["ip"])
            db_b = int(d.get("bytes_used") or 0)
            st = traffic_tracker.get_stats(d["ip"], db_bytes=db_b)
            d["is_blocked"] = is_blk
            d["status"] = "BLOCKED" if is_blk else (d.get("status") or "SHIELDED")
            d["speed_kbps"] = st["speed_kbps"]
            d["total_mb"] = st["total_mb"]
            d["total_gb"] = st["total_gb"]
            d["assigned_port"] = d.get("assigned_port") or store.get_port_for_client_ip(d["ip"])
            devices.append(d)

        # Sort nicely: first unblocked, then by data used
        devices.sort(key=lambda d: (1 if d["is_blocked"] else 0, -d["total_mb"]))

        return jsonify({
            "devices": devices,
            "total_count": len(devices),
            "hub_ip": hub_ip,
            "config_id": config_id
        })

    @api.route("/wifi-devices/sync", methods=["POST"])
    def sync_wifi_devices():
        """
        Receives real-time live device lists from Huawei Router or local probe
        and dynamically registers new devices in the Cloud database.
        """
        data = request.json or {}
        incoming_devices = data.get("devices", [])
        for dev in incoming_devices:
            ip = dev.get("ip")
            name = dev.get("name") or f"Wi-Fi Client ({ip})"
            mac = dev.get("mac", "")
            dev_type = dev.get("type", "Connected Device")
            if ip:
                store.upsert_wifi_device(ip=ip, name=name, mac=mac, dev_type=dev_type)
        return jsonify({"status": "synced", "count": len(incoming_devices)})

    @api.route("/wifi-devices/block", methods=["POST"])
    def block_wifi_device():
        data = request.json or {}
        ip = data.get("ip")
        mac = data.get("mac", "")
        if not ip:
            return jsonify({"error": "Missing IP"}), 400
        store.block_client(ip, mac)
        return jsonify({"status": "blocked", "ip": ip})

    @api.route("/wifi-devices/unblock", methods=["POST"])
    def unblock_wifi_device():
        data = request.json or {}
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "Missing IP"}), 400
        store.unblock_client(ip)
        return jsonify({"status": "unblocked", "ip": ip})

    @api.route("/ports/limit", methods=["POST"])
    def set_port_limit():
        data = request.json or {}
        port = data.get("port")
        rate = data.get("rate_limit_mbps", 0.0)
        if not port:
            return jsonify({"error": "Missing port"}), 400
        store.update_port(port=int(port), rate_limit_mbps=float(rate))
        return jsonify({"status": "updated", "port": port, "rate_limit_mbps": float(rate)})

    @api.route("/ports/bind", methods=["POST"])
    def bind_device_port():
        data = request.json or {}
        ip = data.get("ip")
        mac = data.get("mac", "")
        port = data.get("port")
        if not ip or port is None:
            return jsonify({"error": "Missing ip or port"}), 400
        store.bind_client_to_port(int(port), ip, mac)
        return jsonify({"status": "updated", "ip": ip, "mac": mac, "port": int(port)})

    # ========== NEXTDNS-STYLE SAAS & LINKED IP APIS ==========
    @api.route("/dns-detect", methods=["GET"])
    def detect_dns_usage():
        """NextDNS-style real-time verification: checks if current browser/network is using the firewall."""
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        config_id = store.get_config_for_ip(client_ip)
        is_linked = store.is_ip_linked(client_ip, config_id)
        
        # Check recent queries
        recent_logs = store.get_dns_logs(config_id=config_id, limit=5)
        has_recent = any(log["client_ip"] == client_ip for log in recent_logs)
        
        return jsonify({
            "is_using_officialum1": is_linked or has_recent,
            "client_ip": client_ip,
            "config_id": config_id,
            "is_linked": is_linked,
            "has_recent_queries": has_recent
        })

    @api.route("/config/info", methods=["GET"])
    def get_config_info():
        """Returns SaaS configuration details and linked public IPs."""
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        config_id = request.args.get("id") or store.get_config_for_ip(client_ip)
        config = store.get_or_create_config(config_id)
        linked_ips = store.get_linked_ips(config_id)
        return jsonify({
            "config": config,
            "client_ip": client_ip,
            "linked_ips": linked_ips,
            "is_current_ip_linked": client_ip in linked_ips
        })

    @api.route("/config/link-ip", methods=["POST"])
    def handle_link_ip():
        """1-Click Link or Unlink of Public Router WAN IP to Configuration."""
        data = request.json or {}
        client_ip = data.get("ip") or request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        config_id = data.get("config_id", "default")
        action = data.get("action", "link")
        
        if action == "unlink":
            store.unlink_ip(client_ip)
            return jsonify({"status": "unlinked", "ip": client_ip, "config_id": config_id})
        else:
            store.link_ip(client_ip, config_id)
            return jsonify({"status": "linked", "ip": client_ip, "config_id": config_id})

    @api.route("/config/update-shields", methods=["POST"])
    def update_customer_shields():
        """Allows customer to toggle personal shields on their dashboard."""
        data = request.json or {}
        config_id = data.get("config_id", "default")
        toggles = {}
        for k in ("adblock_enabled", "adult_block_enabled", "safesearch_enabled", "smart_tv_shield", "block_tiktok", "block_gaming"):
            if k in data:
                toggles[k] = int(data[k])
        store.update_tenant_features(config_id, toggles)
        return jsonify({"status": "updated", "config_id": config_id, "toggles": toggles})

    @api.route("/wifi-devices/pause", methods=["POST"])
    def pause_wifi_device():
        """1-Click Bedtime / Internet Pause for specific device."""
        data = request.json or {}
        ip = data.get("ip")
        is_paused = bool(data.get("paused", True))
        if not ip:
            return jsonify({"error": "Missing IP"}), 400
        store.pause_device(ip, is_paused)
        return jsonify({"status": "updated", "ip": ip, "paused": is_paused})

    @api.route("/dns-logs", methods=["GET"])
    def get_dns_logs():
        """Real-time DNS query telemetry stream for active configuration."""
        config_id = request.args.get("id", "default")
        limit = int(request.args.get("limit", 100))
        logs = store.get_dns_logs(config_id=config_id, limit=limit)
        return jsonify({"logs": logs, "count": len(logs)})

    @api.route("/dns-logs/clear", methods=["POST", "DELETE"])
    def clear_dns_logs():
        """Clears query telemetry logs."""
        config_id = request.args.get("id", "default")
        store.clear_dns_logs(config_id=config_id)
        return jsonify({"status": "cleared"})

    # ========== ADMIN COMMAND CENTER API SUITE (/api/admin/*) ==========

    @api.route("/admin/auth", methods=["POST"])
    def admin_auth():
        """Verifies master admin secret and issues authenticated session."""
        data = request.json or {}
        secret = data.get("password", "").strip()
        master_secret = store.get_settings().get("admin_secret", "admintelecom")
        if secret == master_secret:
            return jsonify({"authenticated": True, "token": "admin-session-active"})
        return jsonify({"authenticated": False, "error": "Invalid Admin Password"}), 401

    @api.route("/admin/overview", methods=["GET"])
    def admin_overview():
        """Global fleet analytics for Admin dashboard."""
        analytics = store.get_global_analytics()
        proxies = store.get_proxies()
        analytics["active_proxies"] = sum(1 for p in proxies if p.get("status") == "ACTIVE")
        analytics["total_proxies"] = len(proxies)
        return jsonify(analytics)

    @api.route("/admin/tenants", methods=["GET"])
    def admin_get_tenants():
        """Lists all customer accounts with status, expiry, and device counts."""
        tenants = store.get_all_tenants()
        return jsonify({"tenants": tenants, "total": len(tenants)})

    @api.route("/admin/tenants/create", methods=["POST"])
    def admin_create_tenant():
        """Creates a new customer tenant profile."""
        data = request.json or {}
        tid = data.get("id", "").strip()
        name = data.get("name", "Customer Profile").strip()
        owner = data.get("owner_name", "").strip()
        email = data.get("owner_email", "").strip()
        tier = data.get("plan_tier", "home_pro")
        days = int(data.get("days_valid", 30))

        if not tid or not name:
            return jsonify({"error": "Config ID and Name are required"}), 400

        tenant = store.create_tenant(id=tid, name=name, owner_name=owner, owner_email=email, plan_tier=tier, days_valid=days)
        return jsonify({"status": "created", "tenant": tenant})

    @api.route("/admin/tenants/update", methods=["POST"])
    def admin_update_tenant():
        """Updates feature entitlements and settings for a tenant."""
        data = request.json or {}
        tid = data.get("id")
        updates = data.get("updates", {})
        if not tid:
            return jsonify({"error": "Missing tenant ID"}), 400
        store.update_tenant_features(tid, updates)
        return jsonify({"status": "updated", "id": tid})

    @api.route("/admin/tenants/renew", methods=["POST"])
    def admin_renew_tenant():
        """1-Click 30-Day Subscription Renewal."""
        data = request.json or {}
        tid = data.get("id")
        days = int(data.get("days", 30))
        if not tid:
            return jsonify({"error": "Missing tenant ID"}), 400
        result = store.renew_tenant(tid, days=days)
        return jsonify({"status": "renewed", "tenant": result})

    @api.route("/admin/tenants/suspend", methods=["POST"])
    def admin_suspend_tenant():
        """Suspends a customer tenant (triggers paywall)."""
        data = request.json or {}
        tid = data.get("id")
        if not tid:
            return jsonify({"error": "Missing tenant ID"}), 400
        store.suspend_tenant(tid)
        return jsonify({"status": "suspended", "id": tid})

    @api.route("/admin/tenants/delete", methods=["POST", "DELETE"])
    def admin_delete_tenant():
        """Deletes customer tenant."""
        data = request.json or {}
        tid = data.get("id")
        if not tid or tid == "default":
            return jsonify({"error": "Cannot delete master tenant"}), 400
        store.delete_tenant(tid)
        return jsonify({"status": "deleted", "id": tid})

    return api
