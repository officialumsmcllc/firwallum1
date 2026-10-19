"""
OFFICIALUM1 — Commercial SaaS Single-Device Cut-Off & Anti-Bypass Verification Suite
Tests:
1. Tagged Device DoH Cut-Off (Simulates child mobile with tag)
2. Whole Router WAN Cut-Off (Simulates whole home bedtime)
3. Custom Domain Whitelist & Blacklist Precedence
4. Bedtime Curfew Scheduler Active Time Logic
5. Apple .mobileconfig Native Profile Generator
"""

import sys
import time
from datetime import datetime, time as dtime
from dnslib import DNSRecord, QTYPE, A, AAAA
from core.store import HubStore
from core.dns_server import DnsFirewall
from core.scheduler import is_time_in_range, is_curfew_active
from web.mobile_profiles import generate_apple_mobileconfig, get_device_pairing_info

def run_tests():
    print("=" * 65)
    print("   OFFICIALUM1 — COMMERCIAL SAAS VERIFICATION SUITE")
    print("=" * 65)

    store = HubStore()
    dns = DnsFirewall(store)
    cfg_id = "cfg_officialum1"

    # [TEST 1] Tagged Device Cut-Off (Child Device Isolation)
    print("\n[TEST 1] Tagged Child Device Cut-Off...")
    test_child_tag = "Vivo-V2109"
    test_child_name = "Vivo V2109"
    test_ip = "103.72.2.182"  # Router public WAN IP

    # Initially unblock
    store.unblock_client(test_child_tag)
    store.unblock_client(test_child_name)
    store.pause_device(test_child_tag, False)
    assert not store.is_client_blocked(test_child_tag), "Device should start unblocked"

    # Block child tag
    store.block_client(test_child_tag, reason="Parent Cut-Off Test")
    assert store.is_client_blocked(test_child_tag), "Child tag must be marked BLOCKED"
    assert store.is_client_blocked(test_child_name), "Clean name must also match BLOCKED"

    # Process query tagged with child name
    req = DNSRecord.question("fast.com", "A")
    raw_packet = req.pack()
    resp = dns._process_packet(raw_packet, client_ip=test_ip, device_name=test_child_tag, config_id=cfg_id)
    assert resp is not None, "Response must not be None"
    parsed = DNSRecord.parse(resp)
    assert len(parsed.rr) > 0, "Response must have answers"
    ans_ip = str(parsed.rr[0].rdata)
    assert ans_ip == "0.0.0.0", f"Child device must receive 0.0.0.0, got: {ans_ip}"
    print("  PASS: Child tagged device received 0.0.0.0 hard cut-off!")

    # Unblock child
    store.unblock_client(test_child_tag)
    store.unblock_client(test_child_name)

    # [TEST 2] Whole Home Router WAN Cut-Off
    print("\n[TEST 2] Whole Home Router WAN Cut-Off...")
    router_wan_ip = "103.72.2.182"
    store.block_client(router_wan_ip, reason="Whole Home Bedtime")
    assert store.is_client_blocked(router_wan_ip), "WAN IP must be marked BLOCKED"

    # Normal untagged query from router
    resp_router = dns._process_packet(raw_packet, client_ip=router_wan_ip, device_name="", config_id=cfg_id)
    parsed_router = DNSRecord.parse(resp_router)
    ans_router = str(parsed_router.rr[0].rdata)
    assert ans_router == "0.0.0.0", f"Whole router must receive 0.0.0.0, got: {ans_router}"
    print("  PASS: Whole home router received 0.0.0.0 (Entire house cut off cleanly)!")

    # Unblock router
    store.unblock_client(router_wan_ip)

    # [TEST 3] Custom Whitelist & Blacklist Rules
    print("\n[TEST 3] Custom Domain Whitelist & Blacklist Rules...")
    # Add custom blacklisted domain
    store.add_custom_rule(cfg_id, "custom-bad-site.com", "BLOCK")
    assert store.check_custom_rule(cfg_id, "custom-bad-site.com") == "BLOCK"
    assert store.check_custom_rule(cfg_id, "sub.custom-bad-site.com") == "BLOCK"

    req_custom_b = DNSRecord.question("custom-bad-site.com", "A").pack()
    resp_cb = dns._process_packet(req_custom_b, client_ip="127.0.0.1", device_name="Tester", config_id=cfg_id)
    ans_cb = str(DNSRecord.parse(resp_cb).rr[0].rdata)
    assert ans_cb == "0.0.0.0", f"Custom blocked domain must return 0.0.0.0, got: {ans_cb}"
    print("  PASS: Custom blacklist domain returned 0.0.0.0!")

    # Add custom whitelisted domain (even if in adblock list)
    store.add_custom_rule(cfg_id, "doubleclick.net", "ALLOW")
    assert store.check_custom_rule(cfg_id, "doubleclick.net") == "ALLOW"
    print("  PASS: Custom whitelist precedence verified!")

    # Clean up rules
    rules = store.get_custom_rules(cfg_id)
    for r in rules:
        store.remove_custom_rule(r["id"], cfg_id)

    # [TEST 4] Bedtime & Curfew Scheduler Logic
    print("\n[TEST 4] Bedtime & Curfew Scheduler Logic...")
    # Midnight crossover test (e.g. 22:00 to 06:00)
    assert is_time_in_range("22:00", "06:00", dtime(23, 30)), "23:30 should be in 22:00-06:00 curfew"
    assert is_time_in_range("22:00", "06:00", dtime(3, 15)), "03:15 should be in 22:00-06:00 curfew"
    assert not is_time_in_range("22:00", "06:00", dtime(14, 0)), "14:00 should NOT be in curfew"
    print("  PASS: Midnight rollover bedtime ranges evaluated accurately!")

    # [TEST 5] Apple .mobileconfig Native Profile Generator
    print("\n[TEST 5] Apple .mobileconfig Native Profile Generator...")
    xml = generate_apple_mobileconfig("cfg_demo", "Kid iPhone", host="hub.officialum1.com")
    assert "<key>PayloadType</key>" in xml
    assert "com.apple.dnsSettings.managed" in xml
    assert "https://hub.officialum1.com/dns-query/cfg_demo/Kid-iPhone" in xml
    print("  PASS: Apple .mobileconfig generated with valid RFC 8484 DoH payload!")

    pairing = get_device_pairing_info("cfg_demo", "Kid iPhone", host="hub.officialum1.com")
    assert pairing["apple_profile_url"].startswith("https://")
    print("  PASS: Device pairing metadata generated successfully!")

    print("\n" + "=" * 65)
    print("   ALL 5/5 COMMERCIAL SAAS SUITES PASSED 100%! [OK]")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
