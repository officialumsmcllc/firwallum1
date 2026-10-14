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
        settings = store.get_settings()
        ports = store.get_ports()
        active_count = sum(1 for p in ports if p.get("status") == "ACTIVE")
        dns_clients = dns_firewall.get_active_clients() if dns_firewall else []
        total_active = max(active_count, len(dns_clients))
        return jsonify({
            "status": "ONLINE",
            "hub_ip": settings.get("hub_ip", "127.0.0.1"),
            "total_ports": len(ports),
            "active_devices": total_active,
            "proxy_active_count": active_count,
            "dns_clients": dns_clients,
            "dns_clients_count": len(dns_clients),
            "dns_adblock": settings.get("dns_adblock_enabled") == "1",
            "proxy_gateway_enabled": settings.get("proxy_gateway_enabled", "1") == "1",
            "blocked_domains_count": len(dns_firewall.blocked_domains) if dns_firewall else 0
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

    @api.route("/wifi-devices", methods=["GET"])
    def get_wifi_devices():
        _trigger_subnet_sweep()
        devices = []
        seen_ips = set()
        dns_clients = dns_firewall.get_active_clients(timeout_sec=600) if dns_firewall else []
        hub_ip = store.get_settings().get("hub_ip", "192.168.100.158")

        try:
            out = subprocess.check_output("arp -a", shell=True, text=True, errors="ignore")
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3 and parts[0].startswith("192.168.100."):
                    ip = parts[0]
                    mac = parts[1].replace("-", ":").upper()
                    ip_type = parts[2]
                    if ip_type.lower() == "dynamic" and ip not in ("192.168.100.1", hub_ip):
                        is_active = (ip in dns_clients) or True
                        info = KNOWN_DEVICE_MAP.get(mac, {})
                        dev_name = info.get("name", f"Wi-Fi Client ({ip})")
                        dev_type = info.get("type", "Wireless Mobile / PC")
                        devices.append({
                            "ip": ip,
                            "mac": mac,
                            "name": dev_name,
                            "type": dev_type,
                            "status": "SHIELDED",
                            "dns_active": is_active
                        })
                        seen_ips.add(ip)
        except Exception:
            pass

        for ip in dns_clients:
            if ip not in seen_ips and ip not in ("192.168.100.1", hub_ip, "127.0.0.1", "::1"):
                devices.append({
                    "ip": ip,
                    "mac": "--",
                    "name": f"Wi-Fi Client ({ip})",
                    "type": "Active Wi-Fi Device",
                    "status": "SHIELDED",
                    "dns_active": True
                })
                seen_ips.add(ip)

        from core.store import traffic_tracker
        for d in devices:
            is_blk = store.is_client_blocked(d["ip"])
            st = traffic_tracker.get_stats(d["ip"])
            d["is_blocked"] = is_blk
            d["status"] = "BLOCKED" if is_blk else "SHIELDED"
            d["speed_kbps"] = st["speed_kbps"]
            d["total_mb"] = st["total_mb"]
            d["assigned_port"] = store.get_port_for_client_ip(d["ip"])

        # Sort nicely by IP
        devices.sort(key=lambda d: [int(x) if x.isdigit() else 0 for x in d["ip"].split(".")])

        return jsonify({
            "devices": devices,
            "total_count": len(devices),
            "hub_ip": hub_ip
        })

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

    return api
