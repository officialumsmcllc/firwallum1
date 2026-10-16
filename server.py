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

    # Anti-Index & Privacy Shield: Prevent Google, Bing & spiders from indexing personal hub
    @app.after_request
    def set_privacy_headers(response):
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.route("/robots.txt")
    def robots():
        return send_from_directory(STATIC_DIR, "robots.txt")

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/admin")
    def admin_page():
        return send_from_directory(STATIC_DIR, "admin.html")

    @app.route("/login")
    def login_page():
        return send_from_directory(STATIC_DIR, "login.html")

    @app.route("/expired")
    def expired_page():
        return send_from_directory(STATIC_DIR, "expired.html")

    @app.route("/connect")
    def connect_page():
        return send_from_directory(STATIC_DIR, "connect.html")

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
    @app.route("/dns-query/<p1>", methods=["GET", "POST"])
    @app.route("/dns-query/<p1>/<p2>", methods=["GET", "POST"])
    def doh_query(p1=None, p2=None):
        """
        RFC 8484 DNS-over-HTTPS (DoH) Endpoint with Multi-Tenant & Device Tagging.
        Supports:
        - https://hub.officialum1.com/dns-query
        - https://hub.officialum1.com/dns-query/<device_name>
        - https://hub.officialum1.com/dns-query/<config_id>/<device_name>
        - https://hub.officialum1.com/dns-query?config=<config_id>&device=<device_name>
        """
        raw_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()

        # Resolve config_id and device_name from path or query parameters
        target_config = request.args.get("config", "").strip()
        dev_tag = request.args.get("device") or request.args.get("name") or ""

        if p1 and p2:
            target_config = p1
            dev_tag = p2
        elif p1:
            if p1.startswith("cfg_"):
                target_config = p1
            else:
                dev_tag = p1

        if not target_config:
            target_config = store.get_config_for_ip(raw_ip)

        client_key = f"{raw_ip} - {dev_tag}" if dev_tag else raw_ip

        # Track client in firewall
        if client_key and hasattr(dns_firewall, "live_clients"):
            with dns_firewall._client_lock:
                dns_firewall.live_clients[client_key] = time.time()

        if store.is_client_blocked(raw_ip) or store.is_client_blocked(client_key):
            return Response(b"", status=403)

        if request.method == "POST":
            data = request.get_data()
        else:
            dns_b64 = request.args.get("dns", "")
            if not dns_b64:
                return jsonify({
                    "status": "OFFICIALUM1 Cloud DoH Active",
                    "spec": "RFC 8484 DNS-over-HTTPS",
                    "engine": "OFFICIALUM1 Security Firewall",
                    "config_id": target_config,
                    "client_ip": raw_ip
                }), 200
            padding = '=' * (4 - len(dns_b64) % 4) if len(dns_b64) % 4 != 0 else ''
            try:
                data = base64.urlsafe_b64decode(dns_b64 + padding)
            except Exception:
                return "Invalid DNS message encoding", 400

        if not data:
            return "No DNS payload", 400

        resp = dns_firewall._process_packet(data, client_ip=raw_ip, device_name=dev_tag or "", config_id=target_config)
        if not resp:
            return "Resolution Failed", 500

        from core.store import traffic_tracker
        traffic_tracker.record(client_key, len(data) + len(resp))
        if target_config:
            traffic_tracker.record(f"{target_config}:{raw_ip}", len(data) + len(resp))

        return Response(response=[bytes(resp)], mimetype="application/dns-message", headers={
            "Content-Length": str(len(resp)),
            "Access-Control-Allow-Origin": "*"
        })

    @app.route("/apple.mobileconfig")
    @app.route("/api/setup/apple-profile")
    def apple_profile():
        """Generates a native Apple Configuration Profile for iOS & macOS."""
        dev_name = request.args.get("name", "OFFICIALUM1 Shield")
        doh_url = f"https://hub.officialum1.com/dns-query/{dev_name}" if dev_name else "https://hub.officialum1.com/dns-query"
        profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>DNSSettings</key>
            <dict>
                <key>DNSProtocol</key>
                <string>HTTPS</string>
                <key>ServerURL</key>
                <string>{doh_url}</string>
            </dict>
            <key>PayloadDescription</key>
            <string>Configures device to use OFFICIALUM1 Encrypted DNS Security Shield.</string>
            <key>PayloadDisplayName</key>
            <string>OFFICIALUM1 Security Shield</string>
            <key>PayloadIdentifier</key>
            <string>com.officialum1.dns</string>
            <key>PayloadType</key>
            <string>com.apple.dnsSettings.managed</string>
            <key>PayloadUUID</key>
            <string>e93574d7-4d9a-4c2e-9d22-1d54e12e1234</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>
    </array>
    <key>PayloadDescription</key>
    <string>OFFICIALUM1 Encrypted DNS Profile for iOS &amp; macOS.</string>
    <key>PayloadDisplayName</key>
    <string>OFFICIALUM1 Security Profile</string>
    <key>PayloadIdentifier</key>
    <string>com.officialum1.profile</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>c01a2f90-8b1e-436d-9799-d4d7f7fa4567</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>"""
        return Response(
            profile_xml,
            mimetype="application/x-apple-aspen-config",
            headers={"Content-Disposition": 'attachment; filename="officialum1.mobileconfig"'}
        )

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
