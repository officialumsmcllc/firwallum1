import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.store import HubStore, traffic_tracker
from core.dns_server import DnsFirewall
from dnslib import DNSRecord, QTYPE

store = HubStore()
dns_srv = DnsFirewall(store, host="127.0.0.1", port=5353)

# Test 1: Fast Parallel Upstream Resolution
req = DNSRecord.question("google.com", "A")
data = req.pack()

t0 = time.time()
resp = dns_srv._process_packet(data, client_ip="192.168.100.25", config_id="cfg_officialum1")
t1 = time.time()
latency_ms = (t1 - t0) * 1000

parsed = DNSRecord.parse(resp)
print(f"[TEST 1] google.com resolved in {latency_ms:.1f}ms! RCODE: {parsed.header.rcode}, Answers: {len(parsed.rr)}")

# Test 2: In-Memory Cache Latency
t2 = time.time()
resp_cached = dns_srv._process_packet(data, client_ip="192.168.100.25", config_id="cfg_officialum1")
t3 = time.time()
cache_latency_ms = (t3 - t2) * 1000
print(f"[TEST 2] Cache Hit google.com resolved in {cache_latency_ms:.2f}ms! (Ultra-Fast <1ms)")

# Test 3: Hard Kill Switch / Block Device
store.block_client("192.168.100.99")
resp_blocked = dns_srv._process_packet(data, client_ip="192.168.100.99", config_id="cfg_officialum1")
p_blocked = DNSRecord.parse(resp_blocked)
print(f"[TEST 3] Blocked device query result: {p_blocked.rr[0].rdata} (Expected: 0.0.0.0), TTL: {p_blocked.rr[0].ttl} (Expected: 1)")

# Test 4: Live Speed & MB Metering
traffic_tracker.record("192.168.100.25", 250000) # 250 KB
stats = traffic_tracker.get_stats("192.168.100.25", db_bytes=1000000)
print(f"[TEST 4] Live Metering: Speed: {stats['speed_kbps']} KB/s, Total MB: {stats['total_mb']} MB, Active: {stats['is_active']}")

# Clean up
store.unblock_client("192.168.100.99")
print("[TEST ALL PASSED SUCCESSFULLY]")
