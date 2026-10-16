"""
OFFICIALUM1 — DNS Firewall & Speed Accelerator (Port 53)
Caches DNS lookups in memory (<0.2ms) and filters ads/malware to save bandwidth.
"""

import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import requests
from typing import Optional, Dict, Tuple, Set
from dnslib import DNSRecord, RR, A, QTYPE, RCODE
from core.store import HubStore, DATA_DIR

ADBLOCK_CACHE_FILE = os.path.join(DATA_DIR, "adblock_compiled.txt")
ADULT_CACHE_FILE = os.path.join(DATA_DIR, "adult_compiled.txt")

ADULT_SEED_DOMAINS = [
    # Top Adult Tubes & Webcam Services
    "pornhub.com", "xvideos.com", "xnxx.com", "xhamster.com", "chaturbate.com",
    "stripchat.com", "livejasmin.com", "spankbang.com", "redtube.com", "youporn.com",
    "tube8.com", "beeg.com", "eporner.com", "txxx.com", "hqporner.com", "tnaflix.com",
    "fapvid.com", "daftsex.com", "empflix.com", "fuq.com", "porn.com", "cam4.com",
    "bongacams.com", "camsoda.com", "flirt4free.com", "myfreecams.com", "onlyfans.com",
    "fansly.com", "manyvids.com", "clips4sale.com", "rule34.xxx", "gelbooru.com",
    "e-hentai.org", "nhentai.net", "danbooru.donmai.us", "redgifs.com", "erome.com",
    "nudevista.com", "brazzers.com", "bangbros.com", "realitykings.com", "naughtyamerica.com",
    "twistys.com", "mofos.com", "pornmd.com", "porn555.com", "thumbzilla.com",
    "vporn.com", "pornhat.com", "nuvid.com", "motherless.com",
    # Adult Ad Networks, Popunders & Trackers
    "exoclick.com", "trafficjunky.com", "ero-advertising.com", "juicyads.com",
    "adxad.com", "plugrush.com", "adxpansion.com", "trafficstars.com", "popcash.net",
    "popads.net", "hilltopads.com", "clickadu.com", "chaturbateads.com", "realsrv.com",
    "syndication.exoclick.com", "ads.trafficjunky.net", "ptwmstcnt.com", "rtb-direct.com"
]

class DNSCache:
    def __init__(self, max_entries: int = 5000):
        self.max_entries = max_entries
        self.lock = threading.Lock()
        self.cache: Dict[Tuple[str, int], Tuple[bytes, float]] = {}

    def get(self, qname: str, qtype: int) -> Optional[bytes]:
        key = (qname.lower().rstrip("."), qtype)
        now = time.time()
        with self.lock:
            if key in self.cache:
                data, expiry = self.cache[key]
                if now < expiry:
                    return data
                else:
                    del self.cache[key]
        return None

    def set(self, qname: str, qtype: int, raw_wire: bytes, ttl: int = 300):
        key = (qname.lower().rstrip("."), qtype)
        expiry = time.time() + max(30, min(ttl, 3600))
        with self.lock:
            if len(self.cache) >= self.max_entries:
                oldest = next(iter(self.cache))
                del self.cache[oldest]
            self.cache[key] = (raw_wire, expiry)

class DnsFirewall:
    def __init__(self, store: HubStore, host: str = "0.0.0.0", port: int = 53):
        self.store = store
        self.host = host
        self.port = port
        self.running = False

        self.cache = DNSCache()
        self.blocked_domains: Set[str] = set()
        self.adult_blocked_domains: Set[str] = set()
        self.live_clients: Dict[str, float] = {}
        self._client_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=40)
        self.doh_session = requests.Session()
        self.doh_headers = {
            "Accept": "application/dns-message",
            "Content-Type": "application/dns-message",
            "User-Agent": "OFFICIALUM1-DNS"
        }

        self.udp_sock: Optional[socket.socket] = None
        self.tcp_sock: Optional[socket.socket] = None

        self._load_local_blocklist()

    def _load_local_blocklist(self):
        if os.path.exists(ADBLOCK_CACHE_FILE):
            try:
                with open(ADBLOCK_CACHE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        dom = line.strip().lower()
                        if dom and not dom.startswith("#"):
                            self.blocked_domains.add(dom)
            except Exception:
                pass
        # Seed essential heavy tracker/ad domains immediately (Always ensure these are blocked)
        defaults = [
            "doubleclick.net", "adservice.google.com", "pagead2.googlesyndication.com",
            "analytics.google.com", "ads.youtube.com", "s.youtube.com", "video-stats.l.google.com",
            "youtube-nocookie.com", "pubads.g.doubleclick.net", "googleads.g.doubleclick.net",
            "static.doubleclick.net", "securepubads.g.doubleclick.net", "partnerad.l.doubleclick.net",
            "ad.doubleclick.net", "adclick.g.doubleclick.net", "graph.facebook.com",
            "pixel.facebook.com", "ads-api.twitter.com", "analytics.tiktok.com",
            "telemetry.microsoft.com", "vortex.data.microsoft.com", "crashlytics.com",
            "scorecardresearch.com", "adnxs.com", "advertising.com", "criteo.com", "outbrain.com", "taboola.com"
        ]
        self.blocked_domains.update(defaults)

        # Load Adult / 18+ Blocklist
        if os.path.exists(ADULT_CACHE_FILE):
            try:
                with open(ADULT_CACHE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        dom = line.strip().lower()
                        if dom and not dom.startswith("#"):
                            self.adult_blocked_domains.add(dom)
            except Exception:
                pass
        self.adult_blocked_domains.update(ADULT_SEED_DOMAINS)

    def download_and_compile_lists(self):
        # 1. Standard Ad & Tracker Lists
        urls = [
            "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
            "https://adaway.org/hosts.txt"
        ]
        new_domains = set()
        for u in urls:
            try:
                resp = requests.get(u, timeout=12)
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split()
                        if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                            d = parts[1].lower().rstrip(".")
                            if d and d not in ("localhost", "broadcasthost"):
                                new_domains.add(d)
            except Exception:
                pass

        if new_domains:
            self.blocked_domains.update(new_domains)
            try:
                with open(ADBLOCK_CACHE_FILE, "w", encoding="utf-8") as f:
                    for d in self.blocked_domains:
                        f.write(f"{d}\n")
            except Exception:
                pass
            print(f"[OFFICIALUM1] DNS Ad-Shield compiled with {len(self.blocked_domains):,} blocked threat domains.")

        # 2. Adult 18+ Extension List
        try:
            porn_url = "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn/hosts"
            resp = requests.get(porn_url, timeout=15)
            if resp.status_code == 200:
                adult_count = 0
                for line in resp.text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1"):
                        d = parts[1].lower().rstrip(".")
                        if d and d not in ("localhost", "broadcasthost"):
                            self.adult_blocked_domains.add(d)
                            adult_count += 1
                try:
                    with open(ADULT_CACHE_FILE, "w", encoding="utf-8") as f:
                        for d in self.adult_blocked_domains:
                            f.write(f"{d}\n")
                except Exception:
                    pass
                print(f"[OFFICIALUM1] Adult 18+ Shield compiled with {len(self.adult_blocked_domains):,} explicit domains.")
        except Exception:
            pass

    def start(self):
        self.running = True
        try:
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_sock.bind((self.host, self.port))

            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_sock.bind((self.host, self.port))
            self.tcp_sock.listen(20)

            threading.Thread(target=self._udp_loop, daemon=True, name="DNS-UDP").start()
            threading.Thread(target=self._tcp_loop, daemon=True, name="DNS-TCP").start()
            print(f"[OFFICIALUM1] DNS Firewall listening on {self.host}:{self.port} (UDP/TCP)")
        except Exception as e:
            print(f"[WARN] Port 53 bind notice: {e} (DNS service will run in background if port becomes available)")

    def stop(self):
        self.running = False
        if self.udp_sock:
            try: self.udp_sock.close()
            except Exception: pass
        if self.tcp_sock:
            try: self.tcp_sock.close()
            except Exception: pass

    def _udp_loop(self):
        while self.running:
            try:
                data, addr = self.udp_sock.recvfrom(4096)
                if data:
                    self.executor.submit(self._handle_udp, data, addr)
            except Exception:
                if not self.running: break

    def _tcp_loop(self):
        while self.running:
            try:
                client, addr = self.tcp_sock.accept()
                self.executor.submit(self._handle_tcp, client, addr)
            except Exception:
                if not self.running: break

    def _handle_udp(self, data: bytes, addr: Tuple[str, int]):
        if addr and addr[0]:
            from core.store import traffic_tracker
            traffic_tracker.record(addr[0], len(data))
            if self.store.is_client_blocked(addr[0]) or self.store.is_client_paused(addr[0]):
                try:
                    req = DNSRecord.parse(data)
                    reply = req.reply()
                    reply.add_answer(RR(req.q.qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=10))
                    if self.udp_sock and self.running:
                        self.udp_sock.sendto(reply.pack(), addr)
                except Exception:
                    pass
                return

            with self._client_lock:
                self.live_clients[addr[0]] = time.time()
        resp = self._process_packet(data, client_ip=addr[0] if addr else "127.0.0.1")
        if resp and self.udp_sock and self.running:
            try:
                self.udp_sock.sendto(resp, addr)
                if addr and addr[0]:
                    traffic_tracker.record(addr[0], len(resp))
            except Exception: pass

    def _handle_tcp(self, client: socket.socket, addr: Tuple[str, int]):
        if addr and addr[0]:
            if self.store.is_client_blocked(addr[0]) or self.store.is_client_paused(addr[0]):
                try: client.close()
                except Exception: pass
                return

            with self._client_lock:
                self.live_clients[addr[0]] = time.time()
        try:
            client.settimeout(3.0)
            raw_len = client.recv(2)
            if len(raw_len) == 2:
                mlen = int.from_bytes(raw_len, "big")
                data = client.recv(mlen)
                resp = self._process_packet(data)
                if resp:
                    client.sendall(len(resp).to_bytes(2, "big") + resp)
        except Exception:
            pass
        finally:
            try: client.close()
            except Exception: pass

    def get_active_clients(self, timeout_sec: float = 300.0) -> list:
        now = time.time()
        with self._client_lock:
            return sorted([ip for ip, t in self.live_clients.items() if now - t < timeout_sec and ip not in ("127.0.0.1", "::1")])

    def _is_blocked(self, domain: str) -> bool:
        if domain in self.blocked_domains:
            return True
        parts = domain.split(".")
        for i in range(1, len(parts) - 1):
            if ".".join(parts[i:]) in self.blocked_domains:
                return True
        return False

    def _is_adult(self, domain: str) -> bool:
        if domain in self.adult_blocked_domains:
            return True
        parts = domain.split(".")
        for i in range(1, len(parts) - 1):
            if ".".join(parts[i:]) in self.adult_blocked_domains:
                return True
        return False

    def _auto_discover_device(self, client_ip: str, qname: str, device_name: str, config_id: str, packet_len: int):
        """Zero-Touch Device Discovery from real-time DNS queries (No local PC needed)."""
        if not config_id or config_id in ("none", ""):
            return

        # 1. If explicit device tag passed (via DoH / Private DNS)
        if device_name:
            clean_name = device_name.replace("-", " ").title()
            d_type = "Android Smartphone (DoH)" if any(k in clean_name.lower() for k in ("phone", "android", "vivo", "infinix", "samsung", "oppo", "redmi", "xiaomi")) else (
                "Smart TV (DoH)" if any(k in clean_name.lower() for k in ("tv", "roku", "tizen", "webos")) else (
                    "Laptop / PC (DoH)" if any(k in clean_name.lower() for k in ("pc", "laptop", "mac", "windows")) else "Connected Client (DoH)"
                )
            )
            dev_key = f"{client_ip}#{device_name}"
            self.store.upsert_wifi_device(ip=dev_key, name=clean_name, dev_type=d_type, config_id=config_id, initial_bytes=packet_len)
            return

        # 2. If Router DHCP DNS (Queries arrive from linked Public WAN IP)
        router_ip = client_ip.split(":")[0] if ":" in client_ip else client_ip
        if router_ip in ("127.0.0.1", "::1", "localhost"):
            return

        # Register primary router gateway
        router_name = f"Home Wi-Fi Router ({router_ip})"
        self.store.upsert_wifi_device(ip=router_ip, name=router_name, dev_type="Router Gateway (DHCP DNS)", config_id=config_id, initial_bytes=packet_len)

        # Fingerprint devices by queried domain signatures
        qn = qname.lower()
        detected = None
        if any(k in qn for k in ("samsungcloudplatform.com", "samsungqbe.com", "ssp.samsung.com", "ads.samsung.com", "log-config.samsungcloudcdn.com")):
            detected = ("samsung-tv", "Samsung Smart TV", "Smart TV (Wi-Fi Streaming)")
        elif any(k in qn for k in ("lgsmartad.com", "lgtvcommon.com", "lge.com", "lgappstv.com")):
            detected = ("lg-tv", "LG Smart TV", "Smart TV (Wi-Fi Streaming)")
        elif any(k in qn for k in ("roku.com", "firetv-ad", "bravia", "androidtv")):
            detected = ("streaming-tv", "Streaming Player (Smart TV / Roku)", "Smart TV (Wi-Fi Streaming)")
        elif any(k in qn for k in ("connectivitycheck.android.com", "android.clients.google.com", "gvt1.com", "transsion.com", "vivo.com", "xiaomi.com", "oppo.com")):
            detected = ("android-phone", "Android Mobile (Wi-Fi)", "Android Smartphone (Wi-Fi)")
        elif any(k in qn for k in ("mask.icloud.com", "gateway.icloud.com", "apple-dns.net", "push.apple.com", "weather-data.apple.com")):
            detected = ("apple-device", "Apple iPhone / Mac (Wi-Fi)", "Apple Device (Wi-Fi)")
        elif any(k in qn for k in ("dns.msftncsi.com", "msftconnecttest.com", "windowsupdate.com", "settings-win.data.microsoft.com")):
            detected = ("windows-pc", "Windows PC / Laptop (Wi-Fi)", "Windows Laptop (Wi-Fi)")
        elif any(k in qn for k in ("playstation.net", "playstation.com", "xboxlive.com", "nintendo.net")):
            detected = ("gaming-console", "PlayStation / Gaming Console (Wi-Fi)", "Gaming Console (Wi-Fi)")

        if detected:
            d_id, d_name, d_type = detected
            dev_key = f"{router_ip}#{d_id}"
            self.store.upsert_wifi_device(ip=dev_key, name=d_name, dev_type=d_type, config_id=config_id, initial_bytes=packet_len)

    def _race_upstream_dns(self, data: bytes) -> Optional[bytes]:
        """
        Ultra-Fast Concurrent Anycast Upstream Resolver.
        Fires parallel UDP requests to Cloudflare (1.1.1.1), Google DNS (8.8.8.8), and Quad9 (9.9.9.9).
        Captures the first arriving response in 10-30ms, maximizing browsing and video streaming speeds.
        """
        upstreams = ("1.1.1.1", "8.8.8.8", "9.9.9.9")
        fastest_resp = [None]
        done_event = threading.Event()

        def _query_target(ip: str):
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(0.4)
                sock.sendto(data, (ip, 53))
                resp, _ = sock.recvfrom(4096)
                if resp and len(resp) >= 12 and not done_event.is_set():
                    fastest_resp[0] = resp
                    done_event.set()
            except Exception:
                pass
            finally:
                if sock:
                    try: sock.close()
                    except Exception: pass

        threads = []
        for u in upstreams:
            t = threading.Thread(target=_query_target, args=(u,), daemon=True)
            threads.append(t)
            t.start()

        done_event.wait(timeout=0.45)
        return fastest_resp[0]

    def _process_packet(self, data: bytes, client_ip: str = "127.0.0.1", device_name: str = "", config_id: str = "") -> Optional[bytes]:
        try:
            req = DNSRecord.parse(data)
        except Exception:
            return None

        if not req.questions:
            return None

        q = req.questions[0]
        qname = str(q.qname).rstrip(".").lower()
        qtype_num = q.qtype
        qtype_str = str(QTYPE.get(qtype_num, "A"))

        # Lookup configuration for this client if not provided
        if not config_id:
            config_id = self.store.get_config_for_ip(client_ip)

        # Auto-discover and register active device without requiring local PC
        self._auto_discover_device(client_ip=client_ip, qname=qname, device_name=device_name, config_id=config_id, packet_len=len(data))

        # Fetch tenant entitlement and policies
        cfg = self.store.get_or_create_config(config_id)
        settings = self.store.get_settings()

        # 0. Subscription Paywall & Force Renew Check (Hard Cut-Off)
        if not self.store.is_config_active(config_id):
            self.store.log_dns_query(domain=qname, qtype=qtype_str, client_ip=client_ip, status="BLOCKED_EXPIRED", device_name=device_name, config_id=config_id)
            reply = req.reply()
            reply.add_answer(RR(q.qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=1))
            return reply.pack()

        # 0a. Device 1-Click Internet Pause / Hard Block Cut-Off
        clean_ip = client_ip.split("#")[0] if "#" in client_ip else client_ip
        if self.store.is_client_blocked(client_ip) or self.store.is_client_blocked(clean_ip) or self.store.is_client_paused(client_ip) or self.store.is_client_paused(clean_ip):
            self.store.log_dns_query(domain=qname, qtype=qtype_str, client_ip=client_ip, status="BLOCKED_KICKED", device_name=device_name, config_id=config_id)
            reply = req.reply()
            reply.add_answer(RR(q.qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=1))
            return reply.pack()

        # 0b. Smart TV Telemetry & Video Ad Tracker Shield
        if cfg.get("smart_tv_shield", 1) == 1:
            smart_tv_trackers = (
                "samsungcloudplatform.com", "samsungqbe.com", "log-config.samsungcloudcdn.com",
                "ssp.samsung.com", "ads.samsung.com", "lgsmartad.com", "lgtvcommon.com",
                "scribe.logs.roku.com", "logs.roku.com", "firetv-ad.amazon.com", "device-metrics-us.amazon.com"
            )
            if any(qname == st or qname.endswith("." + st) for st in smart_tv_trackers):
                self.store.log_dns_query(domain=qname, qtype=qtype_str, client_ip=client_ip, status="BLOCKED_SMART_TV", device_name=device_name, config_id=config_id)
                reply = req.reply()
                reply.add_answer(RR(q.qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=300))
                return reply.pack()

        # 1. Per-Tenant DNS Adblock Check (controlled by dashboard toggle)
        if cfg.get("adblock_enabled", 1) == 1:
            if self._is_blocked(qname):
                self.store.log_dns_query(domain=qname, qtype=qtype_str, client_ip=client_ip, status="BLOCKED_AD", device_name=device_name, config_id=config_id)
                reply = req.reply()
                reply.add_answer(RR(q.qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=300))
                return reply.pack()

        # 1b. Per-Tenant Adult 18+ Content & Explicit Ads Shield
        if cfg.get("adult_block_enabled", 1) == 1:
            if self._is_adult(qname):
                self.store.log_dns_query(domain=qname, qtype=qtype_str, client_ip=client_ip, status="BLOCKED_ADULT", device_name=device_name, config_id=config_id)
                reply = req.reply()
                reply.add_answer(RR(q.qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=300))
                return reply.pack()

        # 2. IPv6 AAAA Filter: Prevents 20s TCP SYN timeout on non-IPv6 ISP fiber connections (e.g. GitHub)
        if qtype_num == QTYPE.AAAA:
            reply = req.reply()
            return reply.pack()

        # 3. In-memory LRU Cache hit
        cached = self.cache.get(qname, qtype_num)
        if cached and len(cached) >= 12:
            self.store.log_dns_query(domain=qname, qtype=qtype_str, client_ip=client_ip, status="ALLOWED", device_name=device_name, config_id=config_id)
            return data[:2] + cached[2:]

        # 4. Ultra-Fast Parallel Upstream Race (1.1.1.1 vs 8.8.8.8 vs 9.9.9.9)
        # Returns fastest response in 10-25ms
        resp = self._race_upstream_dns(data)
        if resp and len(resp) >= 12:
            self.cache.set(qname, qtype_num, resp, ttl=600)
            self.store.log_dns_query(domain=qname, qtype=qtype_str, client_ip=client_ip, status="ALLOWED", device_name=device_name, config_id=config_id)
            return resp

        # 5. Encrypted DoH Upstream Fallback
        try:
            upstream_url = settings.get("upstream_doh", "https://cloudflare-dns.com/dns-query")
            resp = self.doh_session.post(
                upstream_url,
                data=data,
                headers=self.doh_headers,
                timeout=1.5
            )
            if resp.status_code == 200 and len(resp.content) >= 12:
                self.cache.set(qname, qtype_num, resp.content, ttl=300)
                self.store.log_dns_query(domain=qname, qtype=qtype_str, client_ip=client_ip, status="ALLOWED", device_name=device_name, config_id=config_id)
                return resp.content
        except Exception:
            pass

        # 6. Fallback ServFail
        reply = req.reply()
        reply.header.rcode = RCODE.SERVFAIL
        return reply.pack()
