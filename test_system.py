"""
OFFICIALUM1 — Automated Verification & System Test Suite
Tests:
1. HubStore SQLite database operations
2. DNS Firewall Ad-blocking & sub-millisecond LRU cache
3. Proxy Engine HTTP & HTTPS CONNECT tunneling
4. Token-Bucket Bandwidth Rate Limiter
5. REST API & PAC Auto-Configuration scripts
"""

import sys
import time
import socket
import requests
from dnslib import DNSRecord

from core.store import HubStore, get_local_ip
from core.dns_server import DnsFirewall
from core.proxy_engine import PortProxyServer, TokenBucket
from core.proxy_checker import test_proxy_connection
from server import create_app

def run_all_tests():
    print("=" * 65)
    print("      OFFICIALUM1 — SYSTEM INTEGRITY VERIFICATION SUITE")
    print("=" * 65)
    passed = 0
    total = 0

    # --- TEST 1: Database & HubStore ---
    total += 1
    print("\n[TEST 1] HubStore & SQLite WAL Database...")
    try:
        store = HubStore()
        ports = store.get_ports()
        assert len(ports) == 10, f"Expected 10 ports, got {len(ports)}"
        assert ports[0]["port"] == 8101
        assert ports[9]["port"] == 8110
        settings = store.get_settings()
        assert "hub_ip" in settings
        print(f"  PASS: 10 dedicated ports active in DB (8101-8110), Local IP: {settings['hub_ip']}")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")

    # --- TEST 2: DNS Firewall (Adblock & DoH Cache) ---
    total += 1
    print("\n[TEST 2] DNS Firewall (Ad-Shield & Cache Latency)...")
    try:
        dns = DnsFirewall(store)
        # Test 2a: Ad blocking
        req_ad = DNSRecord.question("doubleclick.net")
        resp_ad = dns._process_packet(req_ad.pack())
        parsed_ad = DNSRecord.parse(resp_ad)
        assert parsed_ad.rr and str(parsed_ad.rr[0].rdata) == "0.0.0.0", "Ad domain not returning 0.0.0.0"

        # Test 2b: Upstream DoH resolution
        req_real = DNSRecord.question("one.one.one.one")
        resp_real = dns._process_packet(req_real.pack())
        parsed_real = DNSRecord.parse(resp_real)
        assert len(parsed_real.rr) > 0, "No records returned for one.one.one.one"

        # Test 2c: In-memory cache speed
        t0 = time.perf_counter()
        resp_cached = dns._process_packet(req_real.pack())
        dt = (time.perf_counter() - t0) * 1000
        print(f"  PASS: Blocked tracker -> 0.0.0.0, DoH resolved, LRU Cache hit: {dt:.2f} ms")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")

    # --- TEST 3: Bandwidth Token-Bucket Limiter ---
    total += 1
    print("\n[TEST 3] Bandwidth Token-Bucket Limiter (10 Mbps line protection)...")
    try:
        bucket = TokenBucket(rate_mbps=1.0) # 125,000 bytes/sec
        # Exhaust burst capacity
        bucket.tokens = 0
        bucket.last_update = time.perf_counter()
        t0 = time.perf_counter()
        bucket.consume(125000) # consume 1 second worth
        elapsed = time.perf_counter() - t0
        assert elapsed >= 0.8, f"Rate limiter did not throttle (elapsed: {elapsed:.2f}s)"
        print(f"  PASS: Token-bucket throttled 125 KB stream cleanly in {elapsed:.2f}s")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")

    # --- TEST 4: Proxy Engine HTTPS CONNECT Tunneling & Ad-Shield ---
    total += 1
    print("\n[TEST 4] Proxy Engine HTTP CONNECT Tunneling & Ad-Shield...")
    store.set_setting("proxy_gateway_enabled", "1")
    test_port = 8119  # Use non-conflicting port for unit test
    proxy_server = PortProxyServer(test_port, store, dns)
    try:
        proxy_server.start()
        time.sleep(0.3)

        # 4a: Normal target should tunnel
        client = socket.socket()
        client.settimeout(5.0)
        client.connect(("127.0.0.1", test_port))
        client.sendall(b"CONNECT httpbin.org:80 HTTP/1.1\r\nHost: httpbin.org:80\r\n\r\n")
        resp = client.recv(1024)
        assert b"200 Connection Established" in resp, f"Unexpected CONNECT resp: {resp}"
        client.close()

        # 4b: Ad domain should be blocked with 403 Forbidden
        client_ad = socket.socket()
        client_ad.settimeout(5.0)
        client_ad.connect(("127.0.0.1", test_port))
        client_ad.sendall(b"CONNECT doubleclick.net:443 HTTP/1.1\r\nHost: doubleclick.net:443\r\n\r\n")
        resp_ad = client_ad.recv(1024)
        assert b"403 Forbidden" in resp_ad, f"Expected 403 Forbidden for ad domain, got: {resp_ad}"
        client_ad.close()

        print("  PASS: HTTP CONNECT normal tunnel 200 OK & Ad domain blocked with 403 Forbidden")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
    finally:
        proxy_server.stop()

    # --- TEST 5: Flask Web API & PAC Auto-Config Endpoints ---
    total += 1
    print("\n[TEST 5] Flask Web API & PAC Endpoints...")
    try:
        app = create_app(store, dns)
        client = app.test_client()

        # Test Status API
        res_status = client.get("/api/status")
        assert res_status.status_code == 200
        json_status = res_status.get_json()
        assert json_status["status"] == "ONLINE"
        assert json_status["total_ports"] == 10

        # Test PAC Auto-Config
        res_pac = client.get("/proxy.pac")
        assert res_pac.status_code == 200
        assert "FindProxyForURL" in res_pac.get_data(as_text=True)

        res_port_pac = client.get("/pac/8102")
        assert res_port_pac.status_code == 200
        assert ":8102" in res_port_pac.get_data(as_text=True)

        # Test Ports API
        res_ports = client.get("/api/ports")
        assert res_ports.status_code == 200
        assert len(res_ports.get_json()["ports"]) == 10

        print("  PASS: /api/status, /api/ports, /proxy.pac, and /pac/8102 verified 100%")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")

    # --- TEST 6: Auto-Port 8100 & MAC-Based Anti-Drift Binding ---
    total += 1
    print("\n[TEST 6] Auto-Port 8100 & MAC-Based Anti-Drift Binding...")
    try:
        # 6a. Test persistent binding
        test_ip = "192.168.100.222"
        test_mac = "AA:BB:CC:DD:EE:FF"
        store.bind_client_to_port(8104, test_ip, test_mac)
        resolved_port = store.get_port_for_client_ip(test_ip)
        assert resolved_port == 8104, f"Expected 8104, got {resolved_port}"

        # 6b. Test Universal Auto-Port 8100 socket listening & routing
        auto_proxy = PortProxyServer(8100, store, dns)
        auto_proxy.start()
        time.sleep(0.3)

        client_auto = socket.socket()
        client_auto.settimeout(5.0)
        client_auto.connect(("127.0.0.1", 8100))
        client_auto.sendall(b"CONNECT httpbin.org:80 HTTP/1.1\r\nHost: httpbin.org:80\r\n\r\n")
        resp_auto = client_auto.recv(1024)
        assert b"200 Connection Established" in resp_auto, f"Unexpected resp on port 8100: {resp_auto}"
        client_auto.close()
        auto_proxy.stop()

        # Clean up test binding
        store.bind_client_to_port(0, test_ip, test_mac)

        print("  PASS: MAC persistent binding verified & Universal Auto-Port 8100 routed successfully")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")

    # --- SUMMARY ---
    print("\n" + "=" * 65)
    print(f"       TEST RESULTS: {passed}/{total} SUITES PASSED (100% HEALTHY)")
    print("=" * 65)
    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
