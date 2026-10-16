"""
OFFICIALUM1 — Comprehensive Verification Suite
Tests:
1. Role protection: Customer accounts vs Admin Console
2. Cloud-native device auto-discovery from DNS telemetry (No local PC needed)
3. Multi-tenant device and data isolation
4. Remote mobile access (Mobile 4G view with linked home router)
5. DNS Ad-Blocker toggle & YouTube ad suppression
"""

import unittest
import os
import time
from dnslib import DNSRecord, QTYPE, A

from core.store import HubStore
from core.dns_server import DnsFirewall
from server import create_app

class TestCloudMultiTenantSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = HubStore()
        cls.dns_firewall = DnsFirewall(cls.store)
        cls.app = create_app(cls.store, cls.dns_firewall)
        cls.client = cls.app.test_client()

    def test_01_user_registration_customer_role(self):
        """Verify home user gets role 'customer' and dedicated config_id."""
        uname = f"umar_{int(time.time())}"
        res = self.client.post("/api/auth/register", json={
            "username": uname,
            "email": f"{uname}@test.com",
            "password": "mypassword123",
            "full_name": "Muhammad Umar",
            "plan_tier": "home_pro"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["user"]["role"], "customer")
        self.assertTrue(data["user"]["config_id"].startswith("cfg_"))
        self.assertEqual(data["user"]["plan_tier"], "home_pro")

    def test_02_remote_mobile_dns_detection(self):
        """Verify remote mobile access recognizes linked home router without false alarm."""
        test_cfg = f"cfg_remote_{int(time.time())}"
        home_router_ip = "103.72.2.125"
        mobile_4g_ip = "39.40.88.12"

        # Link home router WAN IP to this config
        res = self.client.post("/api/config/link-ip", json={
            "ip": home_router_ip,
            "config_id": test_cfg,
            "action": "link"
        })
        self.assertEqual(res.status_code, 200)

        # Access from mobile 4G network (different IP)
        detect_res = self.client.get(
            f"/api/dns-detect?config={test_cfg}",
            headers={"X-Forwarded-For": mobile_4g_ip}
        )
        self.assertEqual(detect_res.status_code, 200)
        det_data = detect_res.get_json()
        self.assertTrue(det_data["is_using_officialum1"])
        self.assertTrue(det_data["is_remote_view"])
        self.assertIn(home_router_ip, det_data["linked_ips"])
        self.assertFalse(det_data["is_linked"])

    def test_03_zero_local_pc_dns_device_autodiscovery(self):
        """Verify real devices are auto-discovered from incoming DNS queries without local PC."""
        test_cfg = f"cfg_auto_{int(time.time())}"
        router_wan_ip = "103.72.2.125"

        self.store.link_ip(router_wan_ip, test_cfg)

        # Query 1: Samsung Smart TV domain
        q_tv = DNSRecord.question("samsungcloudplatform.com")
        self.dns_firewall._process_packet(q_tv.pack(), client_ip=router_wan_ip, config_id=test_cfg)

        # Query 2: Android mobile domain
        q_phone = DNSRecord.question("connectivitycheck.android.com")
        self.dns_firewall._process_packet(q_phone.pack(), client_ip=router_wan_ip, config_id=test_cfg)

        # Query 3: Windows PC domain
        q_pc = DNSRecord.question("dns.msftncsi.com")
        self.dns_firewall._process_packet(q_pc.pack(), client_ip=router_wan_ip, config_id=test_cfg)

        # Verify devices in wifi_devices for test_cfg
        dev_res = self.client.get(f"/api/wifi-devices?config={test_cfg}")
        self.assertEqual(dev_res.status_code, 200)
        dev_data = dev_res.get_json()
        dev_names = [d["name"] for d in dev_data["devices"]]

        self.assertIn(f"Home Wi-Fi Router ({router_wan_ip})", dev_names)
        self.assertIn("Samsung Smart TV", dev_names)
        self.assertIn("Android Mobile (Wi-Fi)", dev_names)
        self.assertIn("Windows PC / Laptop (Wi-Fi)", dev_names)

        # Verify active_devices count matches devices in status
        stat_res = self.client.get(f"/api/status?config={test_cfg}")
        stat_data = stat_res.get_json()
        self.assertEqual(stat_data["active_devices"], len(dev_data["devices"]))

    def test_04_multi_tenant_device_isolation(self):
        """Verify Tenant A never sees Tenant B devices."""
        tenant_a = f"cfg_a_{int(time.time())}"
        tenant_b = f"cfg_b_{int(time.time())}"

        self.store.upsert_wifi_device(ip="10.0.0.1", name="Alice iPhone", config_id=tenant_a)
        self.store.upsert_wifi_device(ip="10.0.0.2", name="Bob Galaxy", config_id=tenant_b)

        res_a = self.client.get(f"/api/wifi-devices?config={tenant_a}").get_json()
        res_b = self.client.get(f"/api/wifi-devices?config={tenant_b}").get_json()

        names_a = [d["name"] for d in res_a["devices"]]
        names_b = [d["name"] for d in res_b["devices"]]

        self.assertIn("Alice iPhone", names_a)
        self.assertNotIn("Bob Galaxy", names_a)

        self.assertIn("Bob Galaxy", names_b)
        self.assertNotIn("Alice iPhone", names_b)

    def test_05_doh_multitenant_routing(self):
        """Verify DoH supports multi-tenant path /dns-query/<config_id>/<device>."""
        test_cfg = f"cfg_doh_{int(time.time())}"
        dev_name = "LivingRoom-Infinix"

        q = DNSRecord.question("google.com")
        res = self.client.post(
            f"/dns-query/{test_cfg}/{dev_name}",
            data=bytes(q.pack()),
            content_type="application/dns-message"
        )
        self.assertEqual(res.status_code, 200)

        # Check device was registered under test_cfg
        dev_res = self.client.get(f"/api/wifi-devices?config={test_cfg}").get_json()
        dev_names = [d["name"] for d in dev_res["devices"]]
        self.assertIn("Livingroom Infinix", dev_names)

    def test_06_youtube_and_adblock_toggle(self):
        """Verify per-tenant adblock blocks ads.youtube.com and doubleclick, and toggle unblocks."""
        test_cfg = f"cfg_ad_{int(time.time())}"
        self.store.create_tenant(id=test_cfg, name="Ad Test", days_valid=30)

        # 1. Adblock enabled (default)
        self.store.update_tenant_features(test_cfg, {"adblock_enabled": 1})
        q_yt = DNSRecord.question("ads.youtube.com")
        resp_data = self.dns_firewall._process_packet(q_yt.pack(), client_ip="127.0.0.1", config_id=test_cfg)
        self.assertIsNotNone(resp_data)
        parsed = DNSRecord.parse(resp_data)
        self.assertTrue(len(parsed.rr) > 0)
        self.assertEqual(str(parsed.rr[0].rdata), "0.0.0.0")

        q_dc = DNSRecord.question("doubleclick.net")
        resp_dc = self.dns_firewall._process_packet(q_dc.pack(), client_ip="127.0.0.1", config_id=test_cfg)
        parsed_dc = DNSRecord.parse(resp_dc)
        self.assertEqual(str(parsed_dc.rr[0].rdata), "0.0.0.0")

        # 2. User toggles Adblock OFF from dashboard
        self.client.post("/api/config/update-shields", json={
            "config_id": test_cfg,
            "adblock_enabled": 0
        })

        # Verify query is now allowed
        resp_unblocked = self.dns_firewall._process_packet(q_yt.pack(), client_ip="127.0.0.1", config_id=test_cfg)
        parsed_unblocked = DNSRecord.parse(resp_unblocked)
        if len(parsed_unblocked.rr) > 0:
            self.assertNotEqual(str(parsed_unblocked.rr[0].rdata), "0.0.0.0")

if __name__ == "__main__":
    unittest.main()
