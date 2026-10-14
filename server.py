"""
OFFICIALUM1 — Main Server Orchestrator
Binds:
1. Multi-Port Proxy Gateway (Ports 8101 - 8110)
2. DNS Firewall & Speed Shield (Port 53)
3. Clean Web Management Dashboard (Port 8088)
"""

import os
import sys
import logging
import threading
import time
from flask import Flask, send_from_directory, Response, request, jsonify
import base64
from flask_cors import CORS

from core.store import HubStore, get_local_ip
from core.proxy_engine import MultiPortManager
from core.dns_server import DnsFirewall
from web.api import create_api_blueprint

# Suppress noisy Flask/Werkzeug request logs in production
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "web", "static")

def create_app(store: HubStore, dns_firewall: DnsFirewall) -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
    CORS(app)

    # Register Clean API Blueprint
    app.register_blueprint(create_api_blueprint(store, dns_firewall))

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/proxy.pac")
    def default_pac():
        hub_ip = store.get_settings().get("hub_ip", get_local_ip())
        client_ip = request.remote_addr or "127.0.0.1"
        proxy_on = store.get_settings().get("proxy_gateway_enabled", "1") == "1"
        if not proxy_on:
            pac_code = "function FindProxyForURL(url, host) { return 'DIRECT'; }\n"
            return Response(pac_code, mimetype="application/x-ns-proxy-autoconfig")

        port = request.args.get("port")
        if not port:
            port = store.get_port_for_client_ip(client_ip)

        pac_code = (
            "function FindProxyForURL(url, host) {\n"
            "    if (isPlainHostName(host) || shExpMatch(host, '*.local') || "
            "shExpMatch(host, '192.168.*') || shExpMatch(host, '127.*') || shExpMatch(host, '10.*')) {\n"
            "        return 'DIRECT';\n"
            "    }\n"
            f"    return 'PROXY {hub_ip}:{port}; DIRECT';\n"
            "}\n"
        )
        return Response(pac_code, mimetype="application/x-ns-proxy-autoconfig")

    @app.route("/pac/<int:port>")
    def dedicated_port_pac(port):
        hub_ip = store.get_settings().get("hub_ip", get_local_ip())
        proxy_on = store.get_settings().get("proxy_gateway_enabled", "1") == "1"
        if not proxy_on:
            pac_code = "function FindProxyForURL(url, host) { return 'DIRECT'; }\n"
            return Response(pac_code, mimetype="application/x-ns-proxy-autoconfig")

        pac_code = (
            "function FindProxyForURL(url, host) {\n"
            "    if (isPlainHostName(host) || shExpMatch(host, '*.local') || "
            "shExpMatch(host, '192.168.*') || shExpMatch(host, '127.*') || shExpMatch(host, '10.*')) {\n"
            "        return 'DIRECT';\n"
            "    }\n"
            f"    return 'PROXY {hub_ip}:{port}; DIRECT';\n"
            "}\n"
        )
        return Response(pac_code, mimetype="application/x-ns-proxy-autoconfig")

    @app.route("/dns-query", methods=["GET", "POST"])
    def doh_query():
        """
        RFC 8484 DNS-over-HTTPS (DoH) Endpoint.
        Enables 100% active cloud firewall on Render without needing Port 53 UDP.
        Android 'Private DNS', iOS DNS profiles, and Windows 11 DoH connect directly here.
        """
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()

        # Track client in firewall
        if client_ip and hasattr(dns_firewall, "live_clients"):
            with dns_firewall._client_lock:
                dns_firewall.live_clients[client_ip] = time.time()

        if store.is_client_blocked(client_ip):
            return Response(b"", status=403)

        if request.method == "POST":
            data = request.get_data()
        else:
            dns_b64 = request.args.get("dns", "")
            if not dns_b64:
                return jsonify({
                    "status": "OFFICIALUM1 Cloud DoH Active",
                    "spec": "RFC 8484 DNS-over-HTTPS",
                    "engine": "OFFICIALUM1 Security Firewall"
                }), 200
            padding = '=' * (4 - len(dns_b64) % 4) if len(dns_b64) % 4 != 0 else ''
            try:
                data = base64.urlsafe_b64decode(dns_b64 + padding)
            except Exception:
                return "Invalid DNS message encoding", 400

        if not data:
            return "No DNS payload", 400

        resp = dns_firewall._process_packet(data)
        if not resp:
            return "Resolution Failed", 500

        from core.store import traffic_tracker
        traffic_tracker.record(client_ip, len(data) + len(resp))

        return Response(response=[bytes(resp)], mimetype="application/dns-message", headers={
            "Content-Length": str(len(resp)),
            "Access-Control-Allow-Origin": "*"
        })

    @app.route("/<path:path>")
    def static_files(path):
        return send_from_directory(STATIC_DIR, path)

    return app

def initial_dns_sync(dns_firewall: DnsFirewall):
    time.sleep(2)
    if len(dns_firewall.blocked_domains) < 1000:
        print("[OFFICIALUM1] Initializing background DNS adblock compilation...")
        dns_firewall.download_and_compile_lists()

def main():
    hub_ip = get_local_ip()
    print()
    print("  " + "=" * 58)
    print("  |  OFFICIALUM1 -- MULTI-DEVICE SECURITY GATEWAY         |")
    print("  " + "=" * 58)
    print(f"  |  Hub IP:    {hub_ip:<43}|")
    print(f"  |  Dashboard: http://localhost:8088{' ' * 22}|")
    print("  " + "=" * 58)
    print()

    # 1. Initialize Storage
    store = HubStore()
    store.set_setting("hub_ip", hub_ip)
    print("  [OK] Database & Storage Engine initialized (SQLite WAL)")

    # 2. Start DNS Firewall (Port 53)
    dns_firewall = DnsFirewall(store)
    try:
        dns_firewall.start()
        threading.Thread(target=initial_dns_sync, args=(dns_firewall,), daemon=True).start()
        print("  [OK] DNS Ad-Blocker & DoH Firewall started (Port 53)")
    except Exception as e:
        print(f"  [!!] DNS Port 53 notice: {e}")

    # 3. Start Dedicated Ports Gateway (8101 - 8110)
    proxy_manager = MultiPortManager(store, dns_firewall=dns_firewall)
    try:
        proxy_manager.start_all()
        print("  [OK] Multi-Port Proxy Gateway ready (8100-8110)")
    except Exception as e:
        print(f"  [!!] Proxy Gateway startup notice: {e}")

    # 4. Start Clean Web Dashboard (Port 8088)
    app = create_app(store, dns_firewall)
    print("  [OK] Premium Web Dashboard serving on port 8088")
    print()

    # 5. Start Background Proxy Health Watchdog
    try:
        from core.proxy_checker import start_proxy_watchdog
        start_proxy_watchdog(store, interval_sec=180)
        print("  [OK] Proxy Health Watchdog active (every 3 min)")
    except Exception as e:
        pass

    print()
    print("  >>> All systems operational -- Hub is LIVE!")
    print("  " + "-" * 50)
    print()

    port = int(os.environ.get("PORT", 8088))
    try:
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)
    except (KeyboardInterrupt, SystemExit):
        print("\n[OFFICIALUM1] Shutting down...")
    finally:
        proxy_manager.stop_all()
        dns_firewall.stop()

if __name__ == "__main__":
    main()
