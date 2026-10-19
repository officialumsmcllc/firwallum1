"""
OFFICIALUM1 — Database Storage Engine
Stores ports, proxy configurations, client devices, and hub settings in SQLite WAL mode.
"""

import os
import sqlite3
import time
import socket
import threading
import hashlib
import secrets
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
                    config_id TEXT DEFAULT 'default',
                    mac TEXT DEFAULT '',
                    reason TEXT DEFAULT 'Kicked by Admin',
                    created_at REAL NOT NULL
                );
            """)

            # 6. Persistent Router & Wi-Fi Devices Table (Guarantees devices always show on Cloud)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wifi_devices (
                    ip TEXT PRIMARY KEY,
                    config_id TEXT DEFAULT 'default',
                    mac TEXT DEFAULT '',
                    name TEXT NOT NULL,
                    type TEXT DEFAULT 'Wireless Device',
                    status TEXT DEFAULT 'SHIELDED',
                    assigned_port INTEGER DEFAULT 0,
                    bytes_used INTEGER DEFAULT 0,
                    last_speed_kbps REAL DEFAULT 0.0,
                    last_seen REAL NOT NULL
                );
            """)

            # 7. NextDNS-Style Multi-Tenant Configurations Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS configurations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner_name TEXT DEFAULT '',
                    owner_email TEXT DEFAULT '',
                    owner_phone TEXT DEFAULT '',
                    plan_tier TEXT DEFAULT 'pro',
                    status TEXT DEFAULT 'active',
                    adblock_enabled INTEGER DEFAULT 1,
                    adult_block_enabled INTEGER DEFAULT 1,
                    safesearch_enabled INTEGER DEFAULT 1,
                    smart_tv_shield INTEGER DEFAULT 1,
                    block_tiktok INTEGER DEFAULT 0,
                    block_gaming INTEGER DEFAULT 0,
                    block_gambling INTEGER DEFAULT 1,
                    proxy_tunnel_enabled INTEGER DEFAULT 0,
                    speed_limit_mbps REAL DEFAULT 0.0,
                    created_at REAL NOT NULL,
                    expires_at REAL DEFAULT 0
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dns_logs_cfg ON dns_logs(config_id, timestamp DESC);")

            # 10. SaaS Customer Accounts & Authentication Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    full_name TEXT DEFAULT '',
                    role TEXT DEFAULT 'customer',
                    config_id TEXT DEFAULT 'default',
                    plan_tier TEXT DEFAULT 'home_pro',
                    status TEXT DEFAULT 'active',
                    created_at REAL NOT NULL,
                    last_login REAL DEFAULT 0
                );
            """)

            # 11. Custom Customer Whitelist / Blacklist Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    action TEXT NOT NULL, -- 'BLOCK' or 'ALLOW'
                    created_at REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_custom_rules ON custom_rules(config_id, domain);")

            # 12. Device Bedtime & Curfew Scheduler Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bedtime_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id TEXT NOT NULL,
                    device_identifier TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    days TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6',
                    is_active INTEGER DEFAULT 1,
                    created_at REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bedtime_dev ON bedtime_schedules(config_id, device_identifier);")

            # --- DYNAMIC SCHEMA MIGRATIONS (Preserves existing data) ---
            cfg_cols = [r["name"] for r in conn.execute("PRAGMA table_info(configurations);").fetchall()]
            for col, ctype, cdef in [
                ("owner_name", "TEXT", "''"), ("owner_email", "TEXT", "''"), ("owner_phone", "TEXT", "''"),
                ("plan_tier", "TEXT", "'pro'"), ("status", "TEXT", "'active'"),
                ("safesearch_enabled", "INTEGER", "1"), ("smart_tv_shield", "INTEGER", "1"),
                ("block_tiktok", "INTEGER", "0"), ("block_gaming", "INTEGER", "0"),
                ("block_youtube", "INTEGER", "0"), ("block_roblox", "INTEGER", "0"),
                ("block_gambling", "INTEGER", "1"),
                ("proxy_tunnel_enabled", "INTEGER", "0"), ("speed_limit_mbps", "REAL", "0.0"),
                ("expires_at", "REAL", str(time.time() + 30 * 86400))
            ]:
                if col not in cfg_cols:
                    conn.execute(f"ALTER TABLE configurations ADD COLUMN {col} {ctype} DEFAULT {cdef};")

            dev_cols = [r["name"] for r in conn.execute("PRAGMA table_info(wifi_devices);").fetchall()]
            if "config_id" not in dev_cols:
                conn.execute("ALTER TABLE wifi_devices ADD COLUMN config_id TEXT DEFAULT 'default';")
            if "bytes_used" not in dev_cols:
                conn.execute("ALTER TABLE wifi_devices ADD COLUMN bytes_used INTEGER DEFAULT 0;")
            if "last_speed_kbps" not in dev_cols:
                conn.execute("ALTER TABLE wifi_devices ADD COLUMN last_speed_kbps REAL DEFAULT 0.0;")

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
            # Seed persistent Huawei Router Devices with real router devices
            real_router_devices = [
                ("192.168.100.158", "cfg_officialum1", "48:4D:7E:E9:25:DD", "Host PC (Admin)", "PC (Firewall Admin)", "SHIELDED", 8101, 0, 0.0, time.time()),
                ("192.168.100.95", "cfg_officialum1", "9A:23:8C:65:4D:D5", "Vivo V2109", "Android Smartphone (Wi-Fi)", "SHIELDED", 8104, 0, 0.0, time.time()),
                ("192.168.100.98", "cfg_officialum1", "1E:91:0C:0E:DB:42", "Infinix HOT 11 Play", "Android Smartphone (Wi-Fi)", "SHIELDED", 8107, 0, 0.0, time.time()),
                ("192.168.100.100", "cfg_officialum1", "5E:E4:9F:53:4E:49", "Mobile Device (Wi-Fi)", "Smartphone (Wi-Fi)", "SHIELDED", 8108, 0, 0.0, time.time()),
                ("192.168.100.137", "cfg_officialum1", "38:BA:F8:84:F3:05", "Client PC Laptop (PC 02)", "Windows Laptop (Wi-Fi)", "SHIELDED", 8102, 0, 0.0, time.time()),
                ("192.168.100.61", "cfg_officialum1", "08:CC:81:18:C9:98", "Ethernet Device (Port 1)", "LAN Client", "SHIELDED", 8106, 0, 0.0, time.time()),
            ]
            for dev in real_router_devices:
                conn.execute("""
                    INSERT INTO wifi_devices (ip, config_id, mac, name, type, status, assigned_port, bytes_used, last_speed_kbps, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ip) DO UPDATE SET
                    mac = CASE WHEN excluded.mac != '' THEN excluded.mac ELSE wifi_devices.mac END,
                    name = CASE WHEN wifi_devices.name = '' OR wifi_devices.name LIKE 'Device %' THEN excluded.name ELSE wifi_devices.name END,
                    type = excluded.type;
                """, dev)

            # Clean up any legacy dummy IPs
            fake_dummy_ips = ("192.168.100.15", "192.168.100.18", "192.168.100.22", "192.168.100.31", "192.168.100.2", "192.168.100.45", "192.168.100.67")
            placeholders = ",".join("?" for _ in fake_dummy_ips)
            conn.execute(f"DELETE FROM wifi_devices WHERE ip IN ({placeholders});", fake_dummy_ips)

            # Seed default settings
            default_settings = {
                "dns_adblock_enabled": "1",
                "proxy_gateway_enabled": "1",
                "adult_block_enabled": "1",
                "hub_ip": get_local_ip(),
                "web_port": "8088",
                "upstream_doh": "https://cloudflare-dns.com/dns-query",
                "admin_secret": "admintelecom"
            }
            for k, v in default_settings.items():
                conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);", (k, v))

            # Seed default profile cfg_officialum1 and link active WAN IP
            conn.execute("""
                INSERT OR IGNORE INTO configurations (id, name, owner_name, plan_tier, status, adblock_enabled, adult_block_enabled, smart_tv_shield, created_at, expires_at)
                VALUES ('cfg_officialum1', 'OfficialUM1 Enterprise Shield', 'OfficialUM1 Enterprise', 'business', 'active', 1, 1, 1, ?, ?);
            """, (time.time(), time.time() + 365 * 86400))
            conn.execute("""
                INSERT OR IGNORE INTO linked_ips (ip, config_id, auto_link, updated_at)
                VALUES ('103.72.2.7', 'cfg_officialum1', 1, ?);
            """, (time.time(),))

            # Auto-migrate any existing 'default' config data into 'cfg_officialum1' and remove 'default'
            conn.execute("UPDATE OR IGNORE wifi_devices SET config_id = 'cfg_officialum1' WHERE config_id = 'default';")
            conn.execute("UPDATE OR IGNORE linked_ips SET config_id = 'cfg_officialum1' WHERE config_id = 'default';")
            conn.execute("UPDATE dns_logs SET config_id = 'cfg_officialum1' WHERE config_id = 'default';")
            conn.execute("UPDATE users SET config_id = 'cfg_officialum1' WHERE config_id = 'default';")
            conn.execute("DELETE FROM users WHERE username = 'demo';")
            conn.execute("DELETE FROM configurations WHERE id = 'default';")

            # Seed permanent enterprise user officialum1 if users table is empty
            user_cnt = conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
            if user_cnt == 0:
                pwd_hash, salt = self.hash_password("admintelecom")
                conn.execute("""
                    INSERT INTO users (username, email, password_hash, salt, full_name, role, config_id, plan_tier, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, ("officialum1", "admin@officialum1.com", pwd_hash, salt, "OfficialUM1 Enterprise", "customer", "cfg_officialum1", "business", "active", time.time()))

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
        clean_ip = ip.strip()
        base_ip = clean_ip.split("#")[0].split(" - ")[0] if ("#" in clean_ip or " - " in clean_ip) else clean_ip
        space_name = clean_ip.replace("-", " ")
        dash_name = clean_ip.replace(" ", "-")
        with self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO blocked_clients (ip, mac, reason, created_at) VALUES (?, ?, ?, ?);",
                         (clean_ip, mac.strip(), reason, time.time()))
            if base_ip != clean_ip:
                conn.execute("INSERT OR REPLACE INTO blocked_clients (ip, mac, reason, created_at) VALUES (?, ?, ?, ?);",
                             (base_ip, mac.strip(), reason, time.time()))
            conn.execute("""
                UPDATE wifi_devices 
                SET status = 'BLOCKED' 
                WHERE ip = ? OR ip LIKE ? OR name = ? OR name = ? OR name = ? OR name LIKE ?;
            """, (clean_ip, f"{base_ip}%", clean_ip, space_name, dash_name, f"%{clean_ip}%"))
            conn.commit()

    def unblock_client(self, ip: str):
        clean_ip = ip.strip()
        base_ip = clean_ip.split("#")[0].split(" - ")[0] if ("#" in clean_ip or " - " in clean_ip) else clean_ip
        space_name = clean_ip.replace("-", " ")
        dash_name = clean_ip.replace(" ", "-")
        with self._get_conn() as conn:
            cur = conn.execute("SELECT name, mac FROM wifi_devices WHERE ip = ? OR ip = ? OR name = ?;", (clean_ip, base_ip, clean_ip))
            row = cur.fetchone()
            d_name = row["name"] if row else ""
            d_mac = row["mac"] if row else ""

            conn.execute("DELETE FROM blocked_clients WHERE ip = ? OR ip = ? OR ip = ? OR ip = ?;", (clean_ip, base_ip, space_name, dash_name))
            if d_name:
                conn.execute("DELETE FROM blocked_clients WHERE ip = ?;", (d_name,))
            if d_mac:
                conn.execute("DELETE FROM blocked_clients WHERE mac = ?;", (d_mac,))
            conn.execute("""
                UPDATE wifi_devices 
                SET status = 'SHIELDED' 
                WHERE ip = ? OR ip LIKE ? OR name = ? OR name = ? OR name = ? OR name LIKE ?;
            """, (clean_ip, f"{base_ip}%", clean_ip, space_name, dash_name, f"%{clean_ip}%"))
            conn.commit()

    def is_client_blocked(self, identifier: str, config_id: str = "") -> bool:
        if not identifier: return False
        clean = identifier.strip()
        base = clean.split("#")[0].split(" - ")[0] if ("#" in clean or " - " in clean) else clean
        tag = clean.split("#")[-1].strip() if "#" in clean else ""
        space_name = clean.replace("-", " ")
        dash_name = clean.replace(" ", "-")

        with self._get_conn() as conn:
            # 1. Check blocked_clients table
            cur = conn.execute("""
                SELECT 1 FROM blocked_clients 
                WHERE ip = ? OR ip = ? OR ip = ? OR ip = ? OR ip = ? 
                   OR ip LIKE ? OR mac = ?;
            """, (clean, base, tag, space_name, dash_name, f"%{clean}%", clean))
            if cur.fetchone() is not None:
                return True

            # 2. Check wifi_devices table for status BLOCKED or KICKED
            cur2 = conn.execute("""
                SELECT 1 FROM wifi_devices 
                WHERE (ip = ? OR ip = ? OR ip = ? OR name = ? OR name = ? OR name = ? OR mac = ? 
                       OR name LIKE ? OR ip LIKE ?) 
                  AND status IN ('BLOCKED', 'KICKED');
            """, (clean, base, tag, clean, space_name, dash_name, clean, f"%{clean}%", f"%{clean}%"))
            if cur2.fetchone() is not None:
                return True

        return False

    def is_client_paused(self, identifier: str, config_id: str = "") -> bool:
        if not identifier: return False
        clean = identifier.strip()
        base = clean.split("#")[0].split(" - ")[0] if ("#" in clean or " - " in clean) else clean
        tag = clean.split("#")[-1].strip() if "#" in clean else ""
        space_name = clean.replace("-", " ")
        dash_name = clean.replace(" ", "-")

        # 1. Dynamic bedtime curfew schedule check
        try:
            if self.is_device_in_bedtime(config_id or "cfg_officialum1", clean):
                return True
        except Exception:
            pass

        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT 1 FROM wifi_devices 
                WHERE (ip = ? OR ip = ? OR ip = ? OR name = ? OR name = ? OR name = ? OR mac = ? 
                       OR name LIKE ? OR ip LIKE ?) 
                  AND status = 'PAUSED';
            """, (clean, base, tag, clean, space_name, dash_name, clean, f"%{clean}%", f"%{clean}%"))
            return cur.fetchone() is not None

    def get_wifi_devices(self, config_id: str = "cfg_officialum1") -> List[Dict[str, Any]]:
        if not config_id or config_id == "default":
            config_id = "cfg_officialum1"
        with self._get_conn() as conn:
            if config_id and config_id != "all":
                cur = conn.execute("SELECT * FROM wifi_devices WHERE config_id = ? ORDER BY last_seen DESC, ip ASC;", (config_id,))
            else:
                cur = conn.execute("SELECT * FROM wifi_devices ORDER BY last_seen DESC, ip ASC;")
            return [dict(r) for r in cur.fetchall()]

    def upsert_wifi_device(self, ip: str, name: str, mac: str = "", dev_type: str = "Wireless Device", port: int = 0, config_id: str = "cfg_officialum1", initial_bytes: int = 0):
        if not config_id or config_id == "default":
            config_id = "cfg_officialum1"
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO wifi_devices (ip, config_id, mac, name, type, status, assigned_port, bytes_used, last_seen)
                VALUES (?, ?, ?, ?, ?, 'SHIELDED', ?, ?, ?)
                ON CONFLICT(ip) DO UPDATE SET
                config_id = CASE WHEN excluded.config_id != 'default' THEN excluded.config_id ELSE wifi_devices.config_id END,
                name = excluded.name,
                mac = CASE WHEN excluded.mac != '' THEN excluded.mac ELSE wifi_devices.mac END,
                type = CASE WHEN excluded.type != 'Wireless Device' THEN excluded.type ELSE wifi_devices.type END,
                bytes_used = CASE WHEN excluded.bytes_used > 0 THEN wifi_devices.bytes_used + excluded.bytes_used ELSE wifi_devices.bytes_used END,
                last_seen = excluded.last_seen;
            """, (ip.strip(), config_id, mac.strip(), name.strip(), dev_type, port, initial_bytes, time.time()))
            conn.commit()

    def pause_device(self, ip: str, is_paused: bool) -> None:
        status = "PAUSED" if is_paused else "SHIELDED"
        clean_ip = ip.strip()
        base_ip = clean_ip.split("#")[0].split(" - ")[0] if ("#" in clean_ip or " - " in clean_ip) else clean_ip
        space_name = clean_ip.replace("-", " ")
        dash_name = clean_ip.replace(" ", "-")
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE wifi_devices 
                SET status = ? 
                WHERE ip = ? OR ip LIKE ? OR name = ? OR name = ? OR name = ? OR name LIKE ?;
            """, (status, clean_ip, f"{base_ip}%", clean_ip, space_name, dash_name, f"%{clean_ip}%"))
            conn.commit()

    def delete_wifi_device(self, ip: str) -> None:
        clean_ip = ip.strip()
        base_ip = clean_ip.split("#")[0] if "#" in clean_ip else clean_ip
        with self._get_conn() as conn:
            conn.execute("DELETE FROM wifi_devices WHERE ip = ? OR ip LIKE ?;", (clean_ip, f"{base_ip}%"))
            conn.commit()

    # ========== CUSTOM RULES (WHITELIST / BLACKLIST) API ==========
    def add_custom_rule(self, config_id: str, domain: str, action: str = "BLOCK") -> Dict[str, Any]:
        clean_domain = domain.strip().lower().rstrip(".")
        action = action.upper() if action.upper() in ("BLOCK", "ALLOW") else "BLOCK"
        if not config_id: config_id = "cfg_officialum1"
        with self._get_conn() as conn:
            conn.execute("DELETE FROM custom_rules WHERE config_id = ? AND domain = ?;", (config_id, clean_domain))
            cur = conn.execute("INSERT INTO custom_rules (config_id, domain, action, created_at) VALUES (?, ?, ?, ?);",
                               (config_id, clean_domain, action, time.time()))
            conn.commit()
            return {"id": cur.lastrowid, "config_id": config_id, "domain": clean_domain, "action": action}

    def remove_custom_rule(self, rule_id: int, config_id: str = "cfg_officialum1") -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM custom_rules WHERE id = ? AND config_id = ?;", (rule_id, config_id))
            conn.commit()
            return True

    def get_custom_rules(self, config_id: str = "cfg_officialum1") -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM custom_rules WHERE config_id = ? ORDER BY domain ASC;", (config_id,))
            return [dict(r) for r in cur.fetchall()]

    def check_custom_rule(self, config_id: str, domain: str) -> Optional[str]:
        if not domain: return None
        d = domain.lower().rstrip(".")
        with self._get_conn() as conn:
            cur = conn.execute("SELECT action FROM custom_rules WHERE config_id = ? AND domain = ?;", (config_id, d))
            row = cur.fetchone()
            if row:
                return row["action"]
            parts = d.split(".")
            for i in range(1, len(parts) - 1):
                parent = ".".join(parts[i:])
                cur2 = conn.execute("SELECT action FROM custom_rules WHERE config_id = ? AND domain = ?;", (config_id, parent))
                row2 = cur2.fetchone()
                if row2:
                    return row2["action"]
        return None

    # ========== BEDTIME & CURFEW SCHEDULER API ==========
    def add_bedtime_schedule(self, config_id: str, device_identifier: str, start_time: str, end_time: str, days: str = "0,1,2,3,4,5,6") -> Dict[str, Any]:
        if not config_id: config_id = "cfg_officialum1"
        clean_dev = device_identifier.strip()
        with self._get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO bedtime_schedules (config_id, device_identifier, start_time, end_time, days, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?);
            """, (config_id, clean_dev, start_time.strip(), end_time.strip(), days.strip(), time.time()))
            conn.commit()
            return {"id": cur.lastrowid, "config_id": config_id, "device_identifier": clean_dev, "start_time": start_time, "end_time": end_time, "days": days}

    def remove_bedtime_schedule(self, schedule_id: int, config_id: str = "cfg_officialum1") -> bool:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM bedtime_schedules WHERE id = ? AND config_id = ?;", (schedule_id, config_id))
            conn.commit()
            return True

    def get_bedtime_schedules(self, config_id: str = "cfg_officialum1", device_identifier: str = None) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            if device_identifier:
                cur = conn.execute("SELECT * FROM bedtime_schedules WHERE config_id = ? AND device_identifier = ? ORDER BY created_at DESC;", (config_id, device_identifier))
            else:
                cur = conn.execute("SELECT * FROM bedtime_schedules WHERE config_id = ? ORDER BY created_at DESC;", (config_id,))
            return [dict(r) for r in cur.fetchall()]

    def is_device_in_bedtime(self, config_id: str, device_identifier: str) -> bool:
        if not device_identifier: return False
        clean = device_identifier.strip()
        base = clean.split("#")[0].split(" - ")[0] if ("#" in clean or " - " in clean) else clean
        tag = clean.split("#")[-1].strip() if "#" in clean else ""
        space_name = clean.replace("-", " ")

        schedules = self.get_bedtime_schedules(config_id)
        if not schedules:
            return False

        try:
            from core.scheduler import is_curfew_active
        except ImportError:
            return False

        for sch in schedules:
            match_id = sch.get("device_identifier", "").strip()
            if match_id in (clean, base, tag, space_name, "all", "ALL", "*"):
                if is_curfew_active(sch):
                    return True
        return False

    # ========== NEXTDNS-STYLE MULTI-TENANT & LINKED IP API ==========
    def get_or_create_config(self, config_id: str = "cfg_officialum1", name: str = "OfficialUM1 Enterprise Shield") -> Dict[str, Any]:
        if not config_id or config_id == "default":
            config_id = "cfg_officialum1"
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM configurations WHERE id = ?;", (config_id,))
            row = cur.fetchone()
            if row:
                return dict(row)
            expires = time.time() + 30 * 86400
            conn.execute("""
                INSERT INTO configurations (id, name, owner_name, plan_tier, status, adblock_enabled, adult_block_enabled, smart_tv_shield, created_at, expires_at)
                VALUES (?, ?, 'New Customer', 'home_pro', 'active', 1, 1, 1, ?, ?);
            """, (config_id, name, time.time(), expires))
            conn.commit()
            return {"id": config_id, "name": name, "adblock_enabled": 1, "adult_block_enabled": 1, "status": "active", "expires_at": expires}

    def get_tenant(self, config_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM configurations WHERE id = ?;", (config_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_tenants(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT c.*,
                       COUNT(DISTINCT w.ip) as device_count,
                       COUNT(DISTINCT l.ip) as linked_ip_count,
                       COUNT(d.id) as query_count
                FROM configurations c
                LEFT JOIN wifi_devices w ON w.config_id = c.id
                LEFT JOIN linked_ips l ON l.config_id = c.id
                LEFT JOIN dns_logs d ON d.config_id = c.id
                GROUP BY c.id
                ORDER BY c.created_at DESC;
            """)
            tenants = [dict(r) for r in cur.fetchall()]
            now = time.time()
            for t in tenants:
                exp = t.get("expires_at", 0)
                t["is_active"] = (t.get("status") == "active") and (exp == 0 or exp > now)
                t["days_left"] = max(0, int((exp - now) / 86400)) if exp > now else 0
            return tenants

    def create_tenant(self, id: str, name: str, owner_name: str = "", owner_email: str = "", plan_tier: str = "home_pro", days_valid: int = 30) -> Dict[str, Any]:
        clean_id = id.strip().lower().replace(" ", "-")
        expires_at = time.time() + (days_valid * 86400)
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO configurations (id, name, owner_name, owner_email, plan_tier, status, adblock_enabled, adult_block_enabled, safesearch_enabled, smart_tv_shield, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 'active', 1, 1, 1, 1, ?, ?);
            """, (clean_id, name.strip(), owner_name.strip(), owner_email.strip(), plan_tier, time.time(), expires_at))
            conn.commit()
        return self.get_or_create_config(clean_id, name)

    def update_tenant_features(self, config_id: str, updates: Dict[str, Any]) -> None:
        allowed_keys = {
            "name", "owner_name", "owner_email", "owner_phone", "plan_tier", "status",
            "adblock_enabled", "adult_block_enabled", "safesearch_enabled", "smart_tv_shield",
            "block_tiktok", "block_gaming", "block_youtube", "block_roblox", "block_gambling", "proxy_tunnel_enabled", "speed_limit_mbps"
        }
        set_clauses = []
        vals = []
        for k, v in updates.items():
            if k in allowed_keys:
                set_clauses.append(f"{k} = ?")
                vals.append(v)
        if not set_clauses: return
        vals.append(config_id)
        with self._get_conn() as conn:
            conn.execute(f"UPDATE configurations SET {', '.join(set_clauses)} WHERE id = ?;", vals)
            conn.commit()

    def renew_tenant(self, config_id: str, days: int = 30) -> Dict[str, Any]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT expires_at FROM configurations WHERE id = ?;", (config_id,))
            row = cur.fetchone()
            curr_exp = row["expires_at"] if row else time.time()
            base = max(time.time(), curr_exp or time.time())
            new_exp = base + (days * 86400)
            conn.execute("UPDATE configurations SET expires_at = ?, status = 'active' WHERE id = ?;", (new_exp, config_id))
            conn.commit()
            return {"config_id": config_id, "status": "active", "expires_at": new_exp}

    def suspend_tenant(self, config_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute("UPDATE configurations SET status = 'suspended' WHERE id = ?;", (config_id,))
            conn.commit()

    def delete_tenant(self, config_id: str) -> None:
        if config_id == "cfg_officialum1": return
        with self._get_conn() as conn:
            conn.execute("DELETE FROM configurations WHERE id = ?;", (config_id,))
            conn.execute("DELETE FROM linked_ips WHERE config_id = ?;", (config_id,))
            conn.execute("DELETE FROM dns_logs WHERE config_id = ?;", (config_id,))
            conn.execute("DELETE FROM wifi_devices WHERE config_id = ?;", (config_id,))
            conn.commit()

    def is_config_active(self, config_id: str) -> bool:
        if not config_id: return True
        with self._get_conn() as conn:
            cur = conn.execute("SELECT status, expires_at FROM configurations WHERE id = ?;", (config_id,))
            row = cur.fetchone()
            if not row: return True
            st = row["status"]
            exp = row["expires_at"]
            if st != "active": return False
            if exp and exp > 0 and time.time() > exp: return False
            return True

    def get_global_analytics(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            tenants_cnt = conn.execute("SELECT COUNT(*) FROM configurations;").fetchone()[0]
            active_cnt = conn.execute("SELECT COUNT(*) FROM configurations WHERE status = 'active';").fetchone()[0]
            dev_cnt = conn.execute("SELECT COUNT(*) FROM wifi_devices;").fetchone()[0]
            queries_cnt = conn.execute("SELECT COUNT(*) FROM dns_logs;").fetchone()[0]
            blocked_ads = conn.execute("SELECT COUNT(*) FROM dns_logs WHERE status = 'BLOCKED_AD';").fetchone()[0]
            blocked_adult = conn.execute("SELECT COUNT(*) FROM dns_logs WHERE status = 'BLOCKED_ADULT';").fetchone()[0]
            total_bytes = conn.execute("SELECT COALESCE(SUM(bytes_used), 0) FROM wifi_devices;").fetchone()[0]

            from core.store import traffic_tracker
            live_bytes = sum(traffic_tracker._total_bytes.values())
            grand_total = total_bytes + live_bytes

            return {
                "total_tenants": tenants_cnt,
                "active_tenants": active_cnt,
                "total_devices": dev_cnt,
                "total_queries": queries_cnt,
                "blocked_ads": blocked_ads,
                "blocked_adult": blocked_adult,
                "total_bytes": grand_total,
                "total_mb": round(grand_total / (1024.0 * 1024.0), 2),
                "total_gb": round(grand_total / (1024.0 * 1024.0 * 1024.0), 3)
            }

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
                conn.execute("""
                    DELETE FROM dns_logs WHERE id NOT IN (
                        SELECT id FROM dns_logs ORDER BY id DESC LIMIT 1000
                    );
                """)
                conn.commit()
        except Exception:
            pass

    def get_dns_logs(self, config_id: str = "cfg_officialum1", limit: int = 100) -> List[Dict[str, Any]]:
        if config_id == "default":
            config_id = "cfg_officialum1"

        with self._get_conn() as conn:
            if config_id and config_id != "all":
                cur = conn.execute("""
                    SELECT id, config_id, client_ip, device_name, domain, qtype, status, timestamp
                    FROM dns_logs
                    WHERE config_id = ? OR (config_id = 'default' AND ? = 'cfg_officialum1')
                    ORDER BY timestamp DESC
                    LIMIT ?;
                """, (config_id, config_id, limit))
            else:
                cur = conn.execute("""
                    SELECT id, config_id, client_ip, device_name, domain, qtype, status, timestamp
                    FROM dns_logs
                    ORDER BY timestamp DESC
                    LIMIT ?;
                """, (limit,))
            return [dict(r) for r in cur.fetchall()]

    def clear_dns_logs(self, config_id: str = "default") -> None:
        with self._get_conn() as conn:
            if config_id and config_id != "all":
                conn.execute("DELETE FROM dns_logs WHERE config_id = ?;", (config_id,))
            else:
                conn.execute("DELETE FROM dns_logs;")
            conn.commit()

    # --- SaaS Customer Accounts & Authentication Management ---
    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
        salt_val = salt or secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_val.encode("utf-8"), 100000).hex()
        return pwd_hash, salt_val

    def create_user(self, username: str, email: str, password: str, full_name: str = "", plan_tier: str = "home_pro", role: str = "customer") -> Dict[str, Any]:
        username = username.strip().lower()
        email = email.strip().lower()
        if not username or not email or not password:
            raise ValueError("Username, email, and password are required.")

        import re
        clean_name = re.sub(r'[^a-z0-9_]', '', username)
        config_id = f"cfg_{clean_name}" if clean_name else f"cfg_{secrets.token_hex(4)}"

        pwd_hash, salt = self.hash_password(password)
        now = time.time()
        expires = now + (30 * 86400) # 30 days subscription

        with self._get_conn() as conn:
            # Check existing
            exist = conn.execute("SELECT id FROM users WHERE username = ? OR email = ?;", (username, email)).fetchone()
            if exist:
                raise ValueError("An account with this username or email already exists.")

            cur = conn.execute("""
                INSERT INTO users (username, email, password_hash, salt, full_name, role, config_id, plan_tier, status, created_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, 0);
            """, (username, email, pwd_hash, salt, full_name or username.title(), role, config_id, plan_tier, now))
            user_id = cur.lastrowid

            # Also provision dedicated tenant configuration profile
            conn.execute("""
                INSERT OR IGNORE INTO configurations (id, name, owner_name, owner_email, plan_tier, status, adblock_enabled, adult_block_enabled, smart_tv_shield, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, 'active', 1, 1, 1, ?, ?);
            """, (config_id, f"{full_name or username.title()}'s Shield", full_name or username.title(), email, plan_tier, now, expires))
            conn.commit()

        token = secrets.token_hex(24)
        return {
            "id": user_id,
            "username": username,
            "email": email,
            "full_name": full_name or username.title(),
            "role": role,
            "config_id": config_id,
            "plan_tier": plan_tier,
            "status": "active",
            "token": token
        }

    def authenticate_user(self, username_or_email: str, password: str) -> Optional[Dict[str, Any]]:
        target = username_or_email.strip().lower()
        if not target or not password:
            return None

        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT id, username, email, password_hash, salt, full_name, role, config_id, plan_tier, status, created_at
                FROM users
                WHERE lower(username) = ? OR lower(email) = ?;
            """, (target, target)).fetchone()

            if not row:
                return None

            user = dict(row)
            check_hash, _ = self.hash_password(password, user["salt"])
            if check_hash != user["password_hash"]:
                return None

            # Update last login
            conn.execute("UPDATE users SET last_login = ? WHERE id = ?;", (time.time(), user["id"]))
            conn.commit()

        token = secrets.token_hex(24)
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "config_id": user["config_id"],
            "plan_tier": user["plan_tier"],
            "status": user["status"],
            "token": token
        }

    def get_all_users(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cur = conn.execute("""
                SELECT u.id, u.username, u.email, u.full_name, u.role, u.config_id, u.plan_tier, u.status, u.created_at, u.last_login,
                       c.expires_at, c.status as config_status
                FROM users u
                LEFT JOIN configurations c ON u.config_id = c.id
                ORDER BY u.id DESC;
            """)
            return [dict(r) for r in cur.fetchall()]

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT id, username, email, full_name, role, config_id, plan_tier, status, created_at, last_login
                FROM users WHERE id = ?;
            """, (user_id,)).fetchone()
            return dict(row) if row else None

    def admin_reset_user_password(self, user_id: int, new_password: str) -> bool:
        if not new_password or len(new_password) < 4:
            raise ValueError("New password must be at least 4 characters.")
        new_hash, new_salt = self.hash_password(new_password)
        with self._get_conn() as conn:
            cur = conn.execute("""
                UPDATE users
                SET password_hash = ?, salt = ?
                WHERE id = ?;
            """, (new_hash, new_salt, user_id))
            conn.commit()
            return cur.rowcount > 0

    def admin_upgrade_user(self, user_id: int, new_plan_tier: str, extend_days: int = 30) -> bool:
        with self._get_conn() as conn:
            user_row = conn.execute("SELECT config_id FROM users WHERE id = ?;", (user_id,)).fetchone()
            if not user_row:
                return False
            config_id = user_row["config_id"]

            now = time.time()
            if extend_days < 0:
                new_expiry = 9999999999.0 # Lifetime
            else:
                # Extend from max of now or existing expiry
                cur_exp = conn.execute("SELECT expires_at FROM configurations WHERE id = ?;", (config_id,)).fetchone()
                base_time = max(now, cur_exp["expires_at"]) if cur_exp and cur_exp["expires_at"] else now
                new_expiry = base_time + (extend_days * 86400)

            conn.execute("""
                UPDATE users
                SET plan_tier = ?, status = 'active'
                WHERE id = ?;
            """, (new_plan_tier, user_id))

            conn.execute("""
                UPDATE configurations
                SET plan_tier = ?, status = 'active', expires_at = ?
                WHERE id = ?;
            """, (new_plan_tier, new_expiry, config_id))
            conn.commit()
            return True

class TrafficTracker:
    """Real-time throughput and persistent data usage meter per IP & Port."""
    def __init__(self):
        self._lock = threading.Lock()
        self._total_bytes: Dict[str, int] = {}
        self._window_bytes: Dict[str, int] = {}
        self._rates: Dict[str, float] = {}
        self._last_tick = time.time()
        self._last_seen: Dict[str, float] = {}

    def record(self, key: str, byte_count: int):
        if not key: return
        now = time.time()
        with self._lock:
            self._total_bytes[key] = self._total_bytes.get(key, 0) + byte_count
            self._window_bytes[key] = self._window_bytes.get(key, 0) + byte_count
            self._last_seen[key] = now
            if "#" in key:
                base = key.split("#")[0]
                self._total_bytes[base] = self._total_bytes.get(base, 0) + byte_count
                self._window_bytes[base] = self._window_bytes.get(base, 0) + byte_count
                self._last_seen[base] = now

    def tick(self):
        now = time.time()
        elapsed = now - self._last_tick
        if elapsed < 0.5:
            return
        with self._lock:
            for k, b in self._window_bytes.items():
                self._rates[k] = round((b / elapsed) / 1024.0, 1)
            self._window_bytes.clear()
            self._last_tick = now

    def get_stats(self, key: str, db_bytes: int = 0) -> Dict[str, Any]:
        self.tick()
        now = time.time()
        with self._lock:
            ram_bytes = self._total_bytes.get(key, 0)
            if ram_bytes == 0 and "#" in key:
                ram_bytes = self._total_bytes.get(key.split("#")[0], 0)
            total = ram_bytes + db_bytes
            rate = self._rates.get(key, 0.0)
            if rate == 0.0 and "#" in key:
                rate = self._rates.get(key.split("#")[0], 0.0)
                
            last_active = self._last_seen.get(key, 0) or (self._last_seen.get(key.split("#")[0], 0) if "#" in key else 0)
            is_active_recently = (now - last_active < 45.0) if last_active > 0 else False



            mb_val = round(total / (1024.0 * 1024.0), 2)
            gb_val = round(total / (1024.0 * 1024.0 * 1024.0), 3)

            return {
                "speed_kbps": rate,
                "speed_mbps": round((rate * 8) / 1024.0, 2),
                "total_bytes": total,
                "total_mb": mb_val,
                "total_gb": gb_val,
                "is_active": is_active_recently or (rate > 0)
            }

traffic_tracker = TrafficTracker()
