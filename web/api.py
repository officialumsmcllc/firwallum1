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
        config_id = request.args.get("config") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        settings = store.get_settings()
        ports = store.get_ports()
        cfg = store.get_or_create_config(config_id)
        is_active = store.is_config_active(config_id)

        # Scoped strictly to this customer tenant's devices
        tenant_devices = store.get_wifi_devices(config_id=config_id)
        active_devices_count = len(tenant_devices)

        # Real tenant DNS metrics from dns_logs
        dns_summary = store.get_tenant_dns_summary(config_id=config_id)
        total_queries = dns_summary.get("total_queries", 0)
        blocked_threats = dns_summary.get("blocked_threats", 0)

        return jsonify({
            "status": "ONLINE" if is_active else "SUSPENDED",
            "hub_ip": settings.get("hub_ip", "127.0.0.1"),
            "config_id": config_id,
            "config_name": cfg.get("name", "OfficialUM1 Network Shield"),
            "tenant_name": cfg.get("name", "OfficialUM1 Network Shield"),
            "is_active": is_active,
            "plan_tier": cfg.get("plan_tier", "home_pro"),
            "expires_at": cfg.get("expires_at", 0),
            "total_ports": len(ports),
            "active_devices": active_devices_count,
            "total_queries": total_queries,
            "blocked_threats": blocked_threats,
            "proxy_active_count": sum(1 for p in ports if p.get("status") == "ACTIVE"),
            "dns_clients": [d["ip"] for d in tenant_devices],
            "dns_clients_count": active_devices_count,
            "dns_adblock": cfg.get("adblock_enabled", 1) == 1,
            "proxy_gateway_enabled": settings.get("proxy_gateway_enabled", "1") == "1",
            "adult_block_enabled": cfg.get("adult_block_enabled", 1) == 1,
            "smart_tv_shield": cfg.get("smart_tv_shield", 1) == 1,
            "safesearch_enabled": cfg.get("safesearch_enabled", 1) == 1,
            "block_tiktok": cfg.get("block_tiktok", 0) == 1,
            "block_gaming": cfg.get("block_gaming", 0) == 1,
            "block_youtube": cfg.get("block_youtube", 0) == 1,
            "block_roblox": cfg.get("block_roblox", 0) == 1,
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
        config_id = request.args.get("config") or request.args.get("id") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        hub_ip = store.get_settings().get("hub_ip", "192.168.100.158")

        # 1. Fetch persistent devices scoped strictly to this customer tenant config
        stored_devs = store.get_wifi_devices(config_id=config_id)
        device_metrics = store.get_device_dns_metrics(config_id=config_id)

        from core.store import traffic_tracker
        devices = []
        for d in stored_devs:
            dev = dict(d)
            raw_ip = dev["ip"]
            # Clean display identifier (strip internal tag hash if any)
            dev["display_ip"] = raw_ip.split("#")[0] if "#" in raw_ip else raw_ip

            is_blk = store.is_client_blocked(raw_ip) or store.is_client_blocked(dev["display_ip"])
            is_psd = store.is_client_paused(raw_ip) or store.is_client_paused(dev["display_ip"])
            db_b = int(dev.get("bytes_used") or 0)
            st = traffic_tracker.get_stats(raw_ip, db_bytes=db_b)
            dev["is_blocked"] = is_blk
            dev["is_paused"] = is_psd
            dev["status"] = "BLOCKED" if is_blk else ("PAUSED" if is_psd else (dev.get("status") or "SHIELDED"))
            dev["speed_kbps"] = st["speed_kbps"]
            dev["speed_mbps"] = st["speed_mbps"]
            dev["total_mb"] = st["total_mb"]
            dev["total_gb"] = st["total_gb"]
            dev["is_active"] = st["is_active"]
            dev["assigned_port"] = dev.get("assigned_port") or store.get_port_for_client_ip(dev["display_ip"])

            # Real NextDNS-style DNS query telemetry
            tag = raw_ip.split("#", 1)[1] if "#" in raw_ip else ""
            m = device_metrics.get(raw_ip) or device_metrics.get(dev["display_ip"]) or (device_metrics.get(tag) if tag else None) or device_metrics.get(dev.get("name", "")) or {}
            dev["total_queries"] = m.get("total_queries", 0)
            dev["blocked_queries"] = m.get("blocked_queries", 0)

            devices.append(dev)

        # Sort: unblocked first, then by query activity
        devices.sort(key=lambda d: (1 if d["is_blocked"] else 0, -d["total_queries"]))

        return jsonify({
            "devices": devices,
            "total_count": len(devices),
            "hub_ip": hub_ip,
            "config_id": config_id
        })

    @api.route("/wifi-devices/force-kill", methods=["POST"])
    def force_kill_device():
        data = request.json or {}
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "Missing IP"}), 400
        stored_devs = store.get_wifi_devices()
        dev_name = ""
        dev_mac = ""
        for d in stored_devs:
            if d.get("ip") == ip or d.get("display_ip") == ip:
                dev_name = d.get("name", "")
                dev_mac = d.get("mac", "")
                break
        store.block_client(ip, mac=dev_mac, reason="Force Killed by User")
        if dev_name:
            store.block_client(dev_name, mac=dev_mac, reason="Force Killed by User")
        return jsonify({"status": "killed", "ip": ip, "name": dev_name, "message": f"Device {dev_name or ip} hard cut-off. Internet completely blocked."})

    @api.route("/wifi-devices/sync", methods=["POST"])
    def sync_wifi_devices():
        """
        Receives real-time live device lists from Huawei Router or local probe
        and dynamically registers new devices in the Cloud database.
        Also automatically detects public WAN IP changes (e.g. after light outage)
        and auto-syncs Cloudflare Zero Trust without user intervention.
        """
        data = request.json or {}
        incoming_devices = data.get("devices", [])
        config_id = data.get("config_id") or "cfg_officialum1"

        # Auto-detect WAN IP change on every probe pulse
        raw_wan_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        if raw_wan_ip and not raw_wan_ip.startswith("127.") and raw_wan_ip != "::1":
            linked_ips = store.get_linked_ips(config_id)
            if raw_wan_ip not in linked_ips:
                store.link_ip(raw_wan_ip, config_id)
                try:
                    from core.cloudflare_bridge import sync_cloudflare_location
                    sync_cloudflare_location(store, raw_wan_ip, config_id)
                except Exception:
                    pass

        for dev in incoming_devices:
            ip = dev.get("ip")
            name = dev.get("name") or f"Wi-Fi Client ({ip})"
            mac = dev.get("mac", "")
            dev_type = dev.get("type", "Connected Device")
            if ip:
                store.upsert_wifi_device(ip=ip, name=name, mac=mac, dev_type=dev_type, config_id=config_id)
        return jsonify({"status": "synced", "count": len(incoming_devices), "wan_ip": raw_wan_ip})

    @api.route("/wifi-devices/delete", methods=["POST", "DELETE"])
    def delete_wifi_device():
        data = request.json or {}
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "Missing IP"}), 400
        store.delete_wifi_device(ip)
        return jsonify({"status": "deleted", "ip": ip})

    @api.route("/wifi-devices/block", methods=["POST"])
    def block_wifi_device():
        data = request.json or {}
        ip = data.get("ip")
        mac = data.get("mac", "")
        if not ip:
            return jsonify({"error": "Missing IP"}), 400
        stored_devs = store.get_wifi_devices()
        dev_name = ""
        for d in stored_devs:
            if d.get("ip") == ip or d.get("display_ip") == ip:
                dev_name = d.get("name", "")
                if not mac:
                    mac = d.get("mac", "")
                break
        store.block_client(ip, mac)
        if dev_name:
            store.block_client(dev_name, mac)
        return jsonify({"status": "blocked", "ip": ip, "name": dev_name})

    @api.route("/wifi-devices/unblock", methods=["POST"])
    def unblock_wifi_device():
        data = request.json or {}
        ip = data.get("ip")
        if not ip:
            return jsonify({"error": "Missing IP"}), 400
        stored_devs = store.get_wifi_devices()
        dev_name = ""
        for d in stored_devs:
            if d.get("ip") == ip or d.get("display_ip") == ip:
                dev_name = d.get("name", "")
                break
        store.unblock_client(ip)
        if dev_name:
            store.unblock_client(dev_name)
        return jsonify({"status": "unblocked", "ip": ip, "name": dev_name})

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
        config_id = request.args.get("config") or store.get_config_for_ip(client_ip) or "default"
        is_current_ip_linked = store.is_ip_linked(client_ip, config_id)
        linked_ips = store.get_linked_ips(config_id)
        has_any_linked = len(linked_ips) > 0

        # Check recent queries
        recent_logs = store.get_dns_logs(config_id=config_id, limit=10)
        has_recent = any(log["client_ip"] in linked_ips or log["client_ip"] == client_ip for log in recent_logs)

        # Remote access detection (e.g. user opening from 4G mobile data while home router IP is linked)
        is_remote_view = has_any_linked and not is_current_ip_linked
        is_active = is_current_ip_linked or has_any_linked

        return jsonify({
            "is_using_officialum1": is_active,
            "client_ip": client_ip,
            "config_id": config_id,
            "is_linked": is_current_ip_linked,
            "has_any_linked": has_any_linked,
            "linked_ips": linked_ips,
            "is_remote_view": is_remote_view,
            "has_recent_queries": has_recent
        })

    @api.route("/config/info", methods=["GET"])
    def get_config_info():
        """Returns SaaS configuration details and linked public IPs."""
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        config_id = request.args.get("id") or request.args.get("config") or store.get_config_for_ip(client_ip)
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
        config_id = data.get("config_id") or request.args.get("config") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        action = data.get("action", "link")

        if action == "unlink":
            store.unlink_ip(client_ip)
            return jsonify({"status": "unlinked", "ip": client_ip, "config_id": config_id})
        else:
            store.link_ip(client_ip, config_id)
            # Auto-register Home Router Gateway device
            store.upsert_wifi_device(
                ip=client_ip,
                name=f"Home Wi-Fi Router ({client_ip})",
                dev_type="Router Gateway (DHCP DNS)",
                config_id=config_id
            )
            # Auto-provision Cloudflare Zero Trust Gateway Location in background
            try:
                from core.cloudflare_bridge import sync_cloudflare_location
                cf_info = sync_cloudflare_location(store, client_ip, config_id)
            except Exception as e:
                cf_info = {"success": False, "message": str(e)}

            return jsonify({
                "status": "linked",
                "ip": client_ip,
                "config_id": config_id,
                "cloudflare": cf_info
            })

    @api.route("/config/ddns", methods=["GET", "POST"])
    def ddns_auto_update():
        """
        Universal Dynamic DNS (DDNS) Webhook for Routers & Cron.
        When router restarts or power returns, router automatically hits this URL.
        Grabs new WAN IP, links to config, and updates Cloudflare Zero Trust instantly.
        """
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        config_id = request.args.get("config") or request.args.get("id") or "cfg_officialum1"
        store.link_ip(client_ip, config_id)
        try:
            from core.cloudflare_bridge import sync_cloudflare_location
            cf_info = sync_cloudflare_location(store, client_ip, config_id)
        except Exception as e:
            cf_info = {"success": False, "message": str(e)}
        return jsonify({
            "status": "updated",
            "wan_ip": client_ip,
            "config_id": config_id,
            "cloudflare": cf_info
        })

    @api.route("/config/update-shields", methods=["POST"])
    def update_customer_shields():
        """Allows customer to toggle personal shields on their dashboard."""
        data = request.json or {}
        config_id = data.get("config_id") or request.args.get("config") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        toggles = {}
        for k in ("adblock_enabled", "adult_block_enabled", "safesearch_enabled", "smart_tv_shield", "block_tiktok", "block_gaming", "block_youtube", "block_roblox"):
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
        stored_devs = store.get_wifi_devices()
        dev_name = ""
        for d in stored_devs:
            if d.get("ip") == ip or d.get("display_ip") == ip:
                dev_name = d.get("name", "")
                break
        store.pause_device(ip, is_paused)
        if dev_name:
            store.pause_device(dev_name, is_paused)
        return jsonify({"status": "updated", "ip": ip, "name": dev_name, "paused": is_paused})

    @api.route("/dns-logs", methods=["GET"])
    def get_dns_logs():
        """Real-time DNS query telemetry stream for active configuration."""
        config_id = request.args.get("config") or request.args.get("id") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        limit = int(request.args.get("limit", 100))
        logs = store.get_dns_logs(config_id=config_id, limit=limit)
        return jsonify({"logs": logs, "count": len(logs)})

    @api.route("/dns-logs/clear", methods=["POST", "DELETE"])
    def clear_dns_logs():
        """Clears query telemetry logs."""
        config_id = request.args.get("config") or request.args.get("id") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
    # ========== ZERO-INSTALL NATIVE DEVICE PROFILES API ==========
    @api.route("/devices/apple-profile", methods=["GET"])
    def get_apple_profile():
        config_id = request.args.get("config") or "cfg_officialum1"
        dev_name = request.args.get("name") or request.args.get("device") or "Child Device"
        from web.mobile_profiles import generate_apple_mobileconfig
        from flask import Response
        xml = generate_apple_mobileconfig(config_id=config_id, device_name=dev_name, host=request.host)
        safe_filename = f"OfficialUM1-{dev_name.replace(' ', '-')}.mobileconfig"
        return Response(
            xml,
            mimetype="application/x-apple-aspen-config",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'}
        )

    @api.route("/devices/pairing-info", methods=["GET"])
    def get_pairing_info():
        config_id = request.args.get("config") or "cfg_officialum1"
        dev_name = request.args.get("name") or "My Mobile"
        from web.mobile_profiles import get_device_pairing_info
        info = get_device_pairing_info(config_id=config_id, device_name=dev_name, host=request.host)
        return jsonify(info)

    # ========== CUSTOM RULES (WHITELIST / BLACKLIST) API ==========
    @api.route("/custom-rules", methods=["GET"])
    def get_custom_rules_api():
        config_id = request.args.get("config") or request.args.get("config_id") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        rules = store.get_custom_rules(config_id=config_id)
        return jsonify({"rules": rules, "count": len(rules)})

    @api.route("/custom-rules/add", methods=["POST"])
    def add_custom_rule_api():
        data = request.json or {}
        config_id = data.get("config_id") or data.get("config") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        domain = data.get("domain", "").strip()
        action = data.get("action", "BLOCK").upper()
        if not domain:
            return jsonify({"error": "Missing domain"}), 400
        rule = store.add_custom_rule(config_id=config_id, domain=domain, action=action)
        return jsonify({"status": "added", "rule": rule})

    @api.route("/custom-rules/delete", methods=["POST", "DELETE"])
    @api.route("/custom-rules/remove", methods=["POST", "DELETE"])
    def delete_custom_rule_api():
        data = request.json or {}
        config_id = data.get("config_id") or data.get("config") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        rule_id = data.get("id") or data.get("rule_id")
        if not rule_id:
            return jsonify({"error": "Missing rule id"}), 400
        store.remove_custom_rule(rule_id=int(rule_id), config_id=config_id)
        return jsonify({"status": "deleted", "id": rule_id})

    # ========== BEDTIME & CURFEW SCHEDULER API ==========
    @api.route("/bedtime/schedules", methods=["GET"])
    def get_bedtime_schedules_api():
        config_id = request.args.get("config") or request.args.get("config_id") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        dev = request.args.get("device")
        schedules = store.get_bedtime_schedules(config_id=config_id, device_identifier=dev)
        return jsonify({"schedules": schedules, "count": len(schedules)})

    @api.route("/bedtime/add", methods=["POST"])
    def add_bedtime_schedule_api():
        data = request.json or {}
        config_id = data.get("config_id") or data.get("config") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        dev = (data.get("device_identifier") or data.get("device") or data.get("client") or "all").strip()
        start = (data.get("start_time") or "22:00").strip()
        end = (data.get("end_time") or "06:00").strip()
        days = (data.get("days") or "0,1,2,3,4,5,6").strip()
        sch = store.add_bedtime_schedule(config_id=config_id, device_identifier=dev, start_time=start, end_time=end, days=days)
        return jsonify({"status": "added", "schedule": sch})

    @api.route("/bedtime/delete", methods=["POST", "DELETE"])
    @api.route("/bedtime/remove", methods=["POST", "DELETE"])
    def delete_bedtime_schedule_api():
        data = request.json or {}
        config_id = data.get("config_id") or data.get("config") or "cfg_officialum1"
        if config_id == "default":
            config_id = "cfg_officialum1"
        sch_id = data.get("id") or data.get("schedule_id")
        if not sch_id:
            return jsonify({"error": "Missing schedule id"}), 400
        store.remove_bedtime_schedule(schedule_id=int(sch_id), config_id=config_id)
        return jsonify({"status": "deleted", "id": sch_id})

    # ========== ADMIN COMMAND CENTER API SUITE (/api/admin/*) ==========

    @api.route("/admin/auth", methods=["POST"])
    def admin_auth():
        """Verifies master admin secret and issues authenticated session."""
        data = request.json or {}
        secret = (data.get("password") or data.get("secret") or "").strip()
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
        if not tid or tid == "cfg_officialum1":
            return jsonify({"error": "Cannot delete master tenant"}), 400
        store.delete_tenant(tid)
        return jsonify({"status": "deleted", "id": tid})

    @api.route("/admin/tenants/merge-default", methods=["POST"])
    def admin_merge_default():
        """Merges all devices, logs, and linked IPs from 'default' into 'cfg_officialum1' and deletes 'default'."""
        target = "cfg_officialum1"
        store.get_or_create_config(target, "OfficialUM1 Enterprise Shield")
        with store._get_conn() as conn:
            conn.execute("UPDATE OR IGNORE wifi_devices SET config_id = ? WHERE config_id = 'default';", (target,))
            conn.execute("UPDATE OR IGNORE linked_ips SET config_id = ? WHERE config_id = 'default';", (target,))
            conn.execute("UPDATE dns_logs SET config_id = ? WHERE config_id = 'default';", (target,))
            conn.execute("UPDATE users SET config_id = ? WHERE config_id = 'default';", (target,))
            conn.execute("DELETE FROM users WHERE username = 'demo';")
            conn.execute("DELETE FROM configurations WHERE id = 'default';")
            conn.commit()
        return jsonify({"status": "success", "message": f"Successfully merged 'default' into '{target}' and removed 'default'!"})

    # =========================================================================
    # SAAS CUSTOMER AUTHENTICATION & ADMIN USER CONTROLS
    # =========================================================================

    @api.route("/auth/register", methods=["POST"])
    def auth_register():
        """Customer Self-Registration & Dedicated Config Provisioning."""
        data = request.json or {}
        username = data.get("username", "").strip()
        email = data.get("email", "").strip()
        password = data.get("password", "")
        full_name = data.get("full_name", "").strip()
        plan_tier = data.get("plan_tier", "home_pro")

        if not username or not email or not password:
            return jsonify({"error": "Username, email, and password are required"}), 400
        if len(password) < 4:
            return jsonify({"error": "Password must be at least 4 characters long"}), 400

        try:
            user = store.create_user(
                username=username,
                email=email,
                password=password,
                full_name=full_name,
                plan_tier=plan_tier
            )
            return jsonify({"status": "registered", "user": user}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Registration failed: {str(e)}"}), 500

    @api.route("/auth/login", methods=["POST"])
    def auth_login():
        """Customer Login & Session Issuance."""
        data = request.json or {}
        identifier = data.get("username") or data.get("email") or ""
        password = data.get("password", "")

        if not identifier or not password:
            return jsonify({"error": "Please provide username/email and password"}), 400

        user = store.authenticate_user(identifier, password)
        if not user:
            return jsonify({"error": "Invalid credentials. Please verify your details."}), 401

        return jsonify({
            "status": "authenticated",
            "user": user
        })

    @api.route("/auth/me", methods=["GET"])
    def auth_me():
        """Returns active user profile."""
        uid = request.headers.get("X-User-Id") or request.args.get("user_id")
        if not uid:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            user = store.get_user_by_id(int(uid))
            if not user:
                return jsonify({"error": "User not found"}), 404
            return jsonify({"user": user})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @api.route("/admin/users", methods=["GET"])
    def admin_get_users():
        """Admin fleet view: List all registered customers and subscribers."""
        users = store.get_all_users()
        return jsonify({
            "status": "success",
            "total_users": len(users),
            "users": users
        })

    @api.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
    def admin_reset_password(user_id: int):
        """Admin manual password reset for any customer."""
        data = request.json or {}
        new_password = data.get("new_password", "")
        if not new_password or len(new_password) < 4:
            return jsonify({"error": "New password must be at least 4 characters long"}), 400

        try:
            ok = store.admin_reset_user_password(user_id, new_password)
            if not ok:
                return jsonify({"error": "User not found"}), 404
            return jsonify({"status": "success", "message": "User password reset successfully"})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @api.route("/admin/users/<int:user_id>/upgrade", methods=["POST"])
    def admin_upgrade_user_plan(user_id: int):
        """Admin manual plan tier promotion and subscription extension."""
        data = request.json or {}
        plan_tier = data.get("plan_tier", "home_pro")
        extend_days = int(data.get("extend_days", 30))

        try:
            ok = store.admin_upgrade_user(user_id, new_plan_tier=plan_tier, extend_days=extend_days)
            if not ok:
                return jsonify({"error": "User not found"}), 404
            return jsonify({
                "status": "success",
                "message": f"Account upgraded to {plan_tier} with +{extend_days} days extension"
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @api.route("/admin/settings/cloudflare", methods=["GET", "POST"])
    def admin_cloudflare_settings():
        """Get or save Cloudflare Zero Trust Gateway credentials for SaaS DNS Anycast bridge."""
        if request.method == "POST":
            data = request.json or {}
            token = data.get("api_token", "").strip()
            account_id = data.get("account_id", "").strip()
            if token:
                store.set_setting("cloudflare_api_token", token)
            if account_id:
                store.set_setting("cloudflare_account_id", account_id)
            return jsonify({"status": "saved", "message": "Cloudflare Zero Trust credentials saved successfully!"})

        settings = store.get_settings()
        token = settings.get("cloudflare_api_token", "")
        account_id = settings.get("cloudflare_account_id", "")
        token_masked = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else ("Configured" if token else "Not Configured")
        return jsonify({
            "configured": bool(token),
            "account_id": account_id,
            "token_masked": token_masked
        })

    @api.route("/admin/tenants/force-renew", methods=["POST"])
    def admin_force_renew_tenant():
        """Instantly cuts off internet for a customer until they renew subscription."""
        data = request.json or {}
        config_id = data.get("config_id") or data.get("id") or "cfg_officialum1"
        store.suspend_tenant(config_id)
        from core.cloudflare_bridge import toggle_kill_switch
        cf_res = toggle_kill_switch(store, enabled=True)
        return jsonify({
            "status": "success",
            "config_id": config_id,
            "internet_state": "SEVERED",
            "message": f"Network severed for {config_id}. Internet resolution is hard blocked until subscription renewal.",
            "cloudflare": cf_res
        })

    @api.route("/admin/tenants/restore", methods=["POST"])
    def admin_restore_tenant():
        """Restores internet access and extends subscription for customer."""
        data = request.json or {}
        config_id = data.get("config_id") or data.get("id") or "cfg_officialum1"
        days = int(data.get("days", 30))
        store.renew_tenant(config_id, days=days)
        from core.cloudflare_bridge import toggle_kill_switch
        cf_res = toggle_kill_switch(store, enabled=False)
        return jsonify({
            "status": "success",
            "config_id": config_id,
            "internet_state": "ACTIVE",
            "message": f"Internet access restored for {config_id} (+{days} days extension)!",
            "cloudflare": cf_res
        })

    @api.route("/admin/kill-switch", methods=["POST"])
    def admin_toggle_kill_switch():
        """Global or per-network instant kill switch toggle."""
        data = request.json or {}
        enabled = bool(data.get("enabled", True))
        from core.cloudflare_bridge import toggle_kill_switch
        res = toggle_kill_switch(store, enabled=enabled)
        return jsonify({
            "status": "success",
            "kill_switch_active": enabled,
            "result": res
        })

    return api
