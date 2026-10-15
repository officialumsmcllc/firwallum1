"""
OFFICIALUM1 — Database Storage Engine
Stores ports, proxy configurations, client devices, and hub settings in SQLite WAL mode.
"""

import os
import sqlite3
import time
import socket
import threading
from typing import List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "hub.sqlite3")

def get_local_ip() -> str:
    """Discovers the active local LAN IP of this PC."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.100.158"

def get_mac_for_ip(ip: str) -> str:
    """Discovers physical MAC address for a local LAN IP using ARP cache."""
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return ""
    try:
        import subprocess
        out = subprocess.check_output(f"arp -a {ip}", shell=True, text=True, errors="ignore")
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0] == ip:
                return parts[1].replace("-", ":").upper()
    except Exception:
        pass
    return ""

class HubStore:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            # 1. Dedicated Ports Table (8101 to 8110)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ports (
                    port INTEGER PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    proxy_id INTEGER,
                    status TEXT DEFAULT 'STANDBY',
                    last_active REAL DEFAULT 0,
                    rate_limit_mbps REAL DEFAULT 0,
                    client_ip TEXT DEFAULT '',
                    client_mac TEXT DEFAULT '',
                    FOREIGN KEY(proxy_id) REFERENCES proxies(id) ON DELETE SET NULL
                );
            """)

            # Safe migration if column doesn't exist
            try:
                conn.execute("ALTER TABLE ports ADD COLUMN rate_limit_mbps REAL DEFAULT 0;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE ports ADD COLUMN client_ip TEXT DEFAULT '';")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE ports ADD COLUMN client_mac TEXT DEFAULT '';")
            except Exception:
                pass

            # 2. Upstream Proxies / VPN Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    protocol TEXT DEFAULT 'socks5', -- 'socks5' or 'http'
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT DEFAULT '',
                    password TEXT DEFAULT '',
                    exit_ip TEXT DEFAULT 'Unknown',
                    country TEXT DEFAULT 'Unknown',
                    latency_ms REAL DEFAULT 0,
                    status TEXT DEFAULT 'UNTESTED',
                    created_at REAL NOT NULL
                );
            """)

            # 3. Settings Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            # 4. Traffic Stats
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    port INTEGER,
                    bytes_transferred INTEGER DEFAULT 0,
                    timestamp REAL NOT NULL
                );
            """)

            # 5. Blocked / Kicked Clients Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blocked_clients (
                    ip TEXT PRIMARY KEY,
                    mac TEXT DEFAULT '',
                    reason TEXT DEFAULT 'Kicked by Admin',
                    created_at REAL NOT NULL
                );
            """)

            # 6. Persistent Router & Wi-Fi Devices Table (Guarantees devices always show on Cloud)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wifi_devices (
                    ip TEXT PRIMARY KEY,
                    mac TEXT DEFAULT '',
                    name TEXT NOT NULL,
                    type TEXT DEFAULT 'Wireless Device',
                    status TEXT DEFAULT 'SHIELDED',
                    assigned_port INTEGER DEFAULT 0,
                    last_seen REAL NOT NULL
                );
            """)

            # 7. NextDNS-Style Multi-Tenant Configurations Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS configurations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    adblock_enabled INTEGER DEFAULT 1,
                    adult_block_enabled INTEGER DEFAULT 1,
                    created_at REAL NOT NULL
                );
            """)

            # 8. Linked Public WAN IPs (Zero-Touch Router Association)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS linked_ips (
                    ip TEXT PRIMARY KEY,
                    config_id TEXT NOT NULL,
                    auto_link INTEGER DEFAULT 1,
                    updated_at REAL NOT NULL
                );
            """)

            # 9. Real-Time DNS Query Telemetry Logs Stream
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dns_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id TEXT DEFAULT 'default',
                    client_ip TEXT NOT NULL,
                    device_name TEXT DEFAULT '',
                    domain TEXT NOT NULL,
                    qtype TEXT DEFAULT 'A',
                    status TEXT DEFAULT 'ALLOWED',
                    timestamp REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dns_logs_time ON dns_logs(timestamp DESC);")

            # Seed default 10 ports if empty
            cur = conn.execute("SELECT COUNT(*) FROM ports;")
            if cur.fetchone()[0] == 0:
                default_ports = [
                    (8101, "PC 01 (This PC)"),
                    (8102, "PC 02 (Team Member)"),
                    (8103, "PC 03 (Team Member)"),
                    (8104, "PC 04 (Team Member)"),
                    (8105, "PC 05 (Team Member)"),
                    (8106, "PC 06 (Team Member)"),
                    (8107, "PC 07 (Team Member)"),
                    (8108, "PC 08 (Team Member)"),
                    (8109, "PC 09 (Team Member)"),
                    (8110, "PC 10 (Team Member)")
                ]
                conn.executemany("INSERT INTO ports (port, device_name) VALUES (?, ?);", default_ports)

            # Seed persistent Huawei Router Devices so cloud always shows all connected devices
            cur = conn.execute("SELECT COUNT(*) FROM wifi_devices;")
            if cur.fetchone()[0] == 0:
                default_router_devices = [
                    ("192.168.100.15", "E2:06:16:AA:1E:5F", "Infinix HOT 11 Play", "Android Smartphone (Wi-Fi)", "SHIELDED", 8103, time.time()),
                    ("192.168.100.18", "9A:23:8C:65:4D:D5", "Vivo V2109", "Android Smartphone (Wi-Fi)", "SHIELDED", 8104, time.time()),
                    ("192.168.100.22", "38:BA:F8:84:F3:05", "Client PC Laptop (PC 02)", "Windows Laptop (Wi-Fi)", "SHIELDED", 8102, time.time()),
                    ("192.168.100.31", "D8:FC:92:58:8B:12", "Wireless Device (lwp0)", "Wi-Fi Client", "SHIELDED", 8105, time.time()),
                    ("192.168.100.2", "08:CC:81:18:C9:98", "Ethernet Device (Port 1)", "LAN Client", "SHIELDED", 8106, time.time()),
                    ("192.168.100.45", "1E:91:0C:0E:DB:42", "Mobile Device", "Smartphone (Wi-Fi)", "SHIELDED", 8107, time.time()),
                    ("192.168.100.67", "5E:E4:9F:53:4E:49", "Mobile Device", "Smartphone (Wi-Fi)", "SHIELDED", 8108, time.time()),
                ]
                conn.executemany("""
                    INSERT OR IGNORE INTO wifi_devices (ip, mac, name, type, status, assigned_port, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, default_router_devices)

            # Seed default settings
            default_settings = {
                "dns_adblock_enabled": "1",
                "proxy_gateway_enabled": "1",
                "adult_block_enabled": "1",
                "hub_ip": get_local_ip(),
                "web_port": "8088",
                "upstream_doh": "https://cloudflare-dns.com/dns-query"
            }
            for k, v in default_settings.items():
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);", (k, v))

            # Seed default NextDNS SaaS profile and link active WAN IP
            conn.execute("""
                INSERT OR IGNORE INTO configurations (id, name, adblock_enabled, adult_block_enabled, created_at)
                VALUES ('default', 'OfficialUM1 Network Shield', 1, 1, ?);
            """, (time.time(),))
            conn.execute("""
                INSERT OR IGNORE INTO linked_ips (ip, config_id, auto_link, updated_at)
                VALUES ('103.72.2.41', 'default', 1, ?);
            """, (time.time(),))

            conn.commit()

    def get_ports(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            query = """
                SELECT p.port, p.device_name, p.proxy_id, p.status, p.last_active, p.rate_limit_mbps, p.client_ip, p.client_mac,
                       pr.name as proxy_name, pr.exit_ip, pr.country, pr.protocol, pr.latency_ms
                FROM ports p
                LEFT JOIN proxies pr ON p.proxy_id = pr.id
                ORDER BY p.port ASC;
            """
            cur = conn.execute(query)
            return [dict(r) for r in cur.fetchall()]

    def update_port(self, port: int, device_name: Optional[str] = None, proxy_id: Optional[int] = None, rate_limit_mbps: Optional[float] = None, client_ip: Optional[str] = None, client_mac: Optional[str] = None):
        with self._get_conn() as conn:
            updates = []
            params = []
            if device_name is not None:
                updates.append("device_name = ?")
                params.append(device_name)
            if proxy_id is not None:
                updates.append("proxy_id = ?")
                params.append(proxy_id if proxy_id > 0 else None)
            if rate_limit_mbps is not None:
                updates.append("rate_limit_mbps = ?")
                params.append(max(0.0, float(rate_limit_mbps)))
            if client_ip is not None:
                updates.append("client_ip = ?")
                params.append(client_ip.strip())
            if client_mac is not None:
                updates.append("client_mac = ?")
                params.append(client_mac.strip().upper())
            if updates:
                params.append(port)
                conn.execute(f"UPDATE ports SET {', '.join(updates)} WHERE port = ?;", params)
                conn.commit()

    def bind_client_to_port(self, port: int, client_ip: str, client_mac: str = ""):
        """Binds a specific Wi-Fi client IP & physical MAC to a dedicated port."""
        client_ip = client_ip.strip()
        client_mac = client_mac.strip().upper()
        if not client_mac and client_ip:
            client_mac = get_mac_for_ip(client_ip)

        with self._get_conn() as conn:
            # Clear previous bindings for this IP or MAC
            conn.execute("""
                UPDATE ports 
                SET client_ip = CASE WHEN client_ip = ? THEN '' ELSE client_ip END,
                    client_mac = CASE WHEN client_mac = ? AND client_mac != '' THEN '' ELSE client_mac END
                WHERE client_ip = ? OR (client_mac = ? AND client_mac != '');
            """, (client_ip, client_mac, client_ip, client_mac))

            if port > 0:
                conn.execute("UPDATE ports SET client_ip = ?, client_mac = ? WHERE port = ?;", (client_ip, client_mac, port))
            conn.commit()

    def get_port_for_client_ip(self, client_ip: str) -> int:
        """Finds port bound to client_ip or physical MAC address, preventing DHCP IP drift."""
        if not client_ip:
            return 8101
        client_ip = client_ip.strip()
        client_mac = get_mac_for_ip(client_ip)

        with self._get_conn() as conn:
            # 1. Anti-Drift: Check if MAC is bound to a port (even if router gave new IP)
            if client_mac:
                cur = conn.execute("SELECT port FROM ports WHERE client_mac = ? AND client_mac != '';", (client_mac,))
                row = cur.fetchone()
                if row:
                    p = row["port"]
                    conn.execute("UPDATE ports SET client_ip = ? WHERE port = ?;", (client_ip, p))
                    conn.commit()
                    return p

            # 2. Check if IP is explicitly bound
            cur = conn.execute("SELECT port FROM ports WHERE client_ip = ? AND client_ip != '';", (client_ip,))
            row = cur.fetchone()
            if row:
                p = row["port"]
                if client_mac:
                    conn.execute("UPDATE ports SET client_mac = ? WHERE port = ?;", (client_mac, p))
                    conn.commit()
                return p

            # 3. Known default mappings
            if client_ip == "192.168.100.137" or client_mac == "38:BA:F8:84:F3:05":  # Laptop 2
                conn.execute("UPDATE ports SET client_ip = ?, client_mac = ? WHERE port = 8102;",
                             (client_ip, client_mac or "38:BA:F8:84:F3:05"))
                conn.commit()
                return 8102

            if client_ip in ("192.168.100.158", "127.0.0.1"):
                conn.execute("UPDATE ports SET client_ip = ? WHERE port = 8101;", (client_ip,))
                conn.commit()
                return 8101

            # 4. Auto-assign to first unbound port (from 8103 to 8110)
            cur = conn.execute("SELECT port FROM ports WHERE (client_ip = '' OR client_ip IS NULL) AND port >= 8103 ORDER BY port ASC;")
            free_row = cur.fetchone()
            if free_row:
                p = free_row["port"]
                conn.execute("UPDATE ports SET client_ip = ?, client_mac = ? WHERE port = ?;", (client_ip, client_mac, p))
                conn.commit()
                return p

            return 8101

    def set_port_status(self, port: int, status: str):
        with self._get_conn() as conn:
            conn.execute("UPDATE ports SET status = ?, last_active = ? WHERE port = ?;", (status, time.time(), port))
            conn.commit()

    def get_port_proxy_config(self, port: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT pr.id, pr.name, pr.protocol, pr.host, pr.port, pr.username, pr.password,
                       pr.exit_ip, pr.country, pr.latency_ms, pr.status, p.rate_limit_mbps
                FROM ports p
                LEFT JOIN proxies pr ON p.proxy_id = pr.id
                WHERE p.port = ?;
            """, (port,))
            row = cur.fetchone()
            if row:
                return dict(row)
            return None

    def get_proxies(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM proxies ORDER BY id DESC;")
            return [dict(r) for r in cur.fetchall()]

    def add_proxy(self, name: str, protocol: str, host: str, port: int, username: str = "", password: str = "") -> int:
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO proxies (name, protocol, host, port, username, password, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (name.strip(), protocol.lower().strip(), host.strip(), port, username.strip(), password.strip(), time.time()))
            conn.commit()
            return cur.lastrowid

    def update_proxy_result(self, proxy_id: int, exit_ip: str, country: str, latency_ms: float, status: str):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE proxies
                SET exit_ip = ?, country = ?, latency_ms = ?, status = ?
                WHERE id = ?;
            """, (exit_ip, country, round(latency_ms, 1), status, proxy_id))
            conn.commit()

    def delete_proxy(self, proxy_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM proxies WHERE id = ?;", (proxy_id,))
            conn.execute("UPDATE ports SET proxy_id = NULL, status = 'STANDBY' WHERE proxy_id = ?;", (proxy_id,))
            conn.commit()

    def get_settings(self) -> Dict[str, str]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT key, value FROM settings;")
            return {r["key"]: r["value"] for r in cur.fetchall()}

    def set_setting(self, key: str, value: str):
        with self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?);", (key, str(value)))
            conn.commit()

    def block_client(self, ip: str, mac: str = "", reason: str = "Kicked by Admin"):
        with self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO blocked_clients (ip, mac, reason, created_at) VALUES (?, ?, ?, ?);",
                         (ip.strip(), mac.strip(), reason, time.time()))
            conn.commit()

    def unblock_client(self, ip: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM blocked_clients WHERE ip = ?;", (ip.strip(),))
            conn.commit()

    def is_client_blocked(self, ip: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT 1 FROM blocked_clients WHERE ip = ?;", (ip.strip(),))
            return cur.fetchone() is not None

    def get_wifi_devices(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM wifi_devices ORDER BY last_seen DESC, ip ASC;")
            return [dict(r) for r in cur.fetchall()]

    def upsert_wifi_device(self, ip: str, name: str, mac: str = "", dev_type: str = "Wireless Device", port: int = 0):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO wifi_devices (ip, mac, name, type, status, assigned_port, last_seen)
                VALUES (?, ?, ?, ?, 'SHIELDED', ?, ?)
                ON CONFLICT(ip) DO UPDATE SET
                name = excluded.name,
                mac = CASE WHEN excluded.mac != '' THEN excluded.mac ELSE wifi_devices.mac END,
                last_seen = excluded.last_seen;
            """, (ip.strip(), mac.strip(), name.strip(), dev_type, port, time.time()))
            conn.commit()

    # ========== NEXTDNS-STYLE MULTI-TENANT & LINKED IP API ==========
    def get_or_create_config(self, config_id: str = "default", name: str = "OfficialUM1 Network Shield") -> Dict[str, Any]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM configurations WHERE id = ?;", (config_id,))
            row = cur.fetchone()
            if row:
                return dict(row)
            conn.execute("""
                INSERT INTO configurations (id, name, adblock_enabled, adult_block_enabled, created_at)
                VALUES (?, ?, 1, 1, ?);
            """, (config_id, name, time.time()))
            conn.commit()
            return {"id": config_id, "name": name, "adblock_enabled": 1, "adult_block_enabled": 1, "created_at": time.time()}

    def link_ip(self, ip: str, config_id: str = "default") -> None:
        if not ip: return
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO linked_ips (ip, config_id, auto_link, updated_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(ip) DO UPDATE SET config_id = excluded.config_id, updated_at = excluded.updated_at;
            """, (ip.strip(), config_id, time.time()))
            conn.commit()

    def unlink_ip(self, ip: str) -> None:
        if not ip: return
        with self._get_conn() as conn:
            conn.execute("DELETE FROM linked_ips WHERE ip = ?;", (ip.strip(),))
            conn.commit()

    def get_linked_ips(self, config_id: str = "default") -> List[str]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT ip FROM linked_ips WHERE config_id = ? ORDER BY updated_at DESC;", (config_id,))
            return [row["ip"] for row in cur.fetchall()]

    def is_ip_linked(self, ip: str, config_id: str = "default") -> bool:
        if not ip: return False
        with self._get_conn() as conn:
            cur = conn.execute("SELECT 1 FROM linked_ips WHERE ip = ? AND config_id = ?;", (ip.strip(), config_id))
            return cur.fetchone() is not None

    def get_config_for_ip(self, ip: str) -> str:
        if not ip: return "default"
        with self._get_conn() as conn:
            cur = conn.execute("SELECT config_id FROM linked_ips WHERE ip = ?;", (ip.strip(),))
            row = cur.fetchone()
            return row["config_id"] if row else "default"

    def log_dns_query(self, domain: str, qtype: str, client_ip: str, status: str, device_name: str = "", config_id: str = "default") -> None:
        try:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT INTO dns_logs (config_id, client_ip, device_name, domain, qtype, status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (config_id, client_ip, device_name, domain.lower().rstrip("."), qtype, status, time.time()))
                # Keep table slim and high-performance (latest 1000 queries)
                conn.execute("""
                    DELETE FROM dns_logs WHERE id NOT IN (
                        SELECT id FROM dns_logs ORDER BY id DESC LIMIT 1000
                    );
                """)
                conn.commit()
        except Exception:
            pass

    def get_dns_logs(self, config_id: str = "default", limit: int = 100) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT id, config_id, client_ip, device_name, domain, qtype, status, timestamp
                FROM dns_logs
                WHERE config_id = ?
                ORDER BY timestamp DESC
                LIMIT ?;
            """, (config_id, limit))
            return [dict(r) for r in cur.fetchall()]

    def clear_dns_logs(self, config_id: str = "default") -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM dns_logs WHERE config_id = ?;", (config_id,))
            conn.commit()

class TrafficTracker:
    """Real-time throughput and data usage meter per port & Wi-Fi device."""
    def __init__(self):
        self._lock = threading.Lock()
        self._total_bytes: Dict[str, int] = {}
        self._window_bytes: Dict[str, int] = {}
        self._rates: Dict[str, float] = {}
        self._last_tick = time.time()

    def record(self, key: str, byte_count: int):
        with self._lock:
            self._total_bytes[key] = self._total_bytes.get(key, 0) + byte_count
            self._window_bytes[key] = self._window_bytes.get(key, 0) + byte_count

    def tick(self):
        now = time.time()
        elapsed = now - self._last_tick
        if elapsed < 0.6:
            return
        with self._lock:
            for k, b in self._window_bytes.items():
                self._rates[k] = round((b / elapsed) / 1024.0, 1)
            self._window_bytes.clear()
            self._last_tick = now

    def get_stats(self, key: str) -> Dict[str, Any]:
        self.tick()
        with self._lock:
            total = self._total_bytes.get(key, 0)
            rate = self._rates.get(key, 0.0)
            return {
                "speed_kbps": rate,
                "total_bytes": total,
                "total_mb": round(total / (1024.0 * 1024.0), 2)
            }

traffic_tracker = TrafficTracker()
