"""
OFFICIALUM1 — Multi-Port Proxy Routing Engine
Listens on dedicated ports (8101-8110) and tunnels client traffic through assigned upstream proxies.
Supports HTTP CONNECT (HTTPS), Plain HTTP, and SOCKS5 upstreams.
"""

import socket
import select
import threading
import time
import base64
from typing import Optional, Dict, Any, Tuple
from core.store import HubStore

BUFFER_SIZE = 65536

_dns_host_cache: Dict[str, Tuple[str, float]] = {}
_dns_host_lock = threading.Lock()

def _resolve_host_cached(host: str) -> Optional[str]:
    now = time.time()
    with _dns_host_lock:
        if host in _dns_host_cache:
            ip, exp = _dns_host_cache[host]
            if now < exp:
                return ip
            del _dns_host_cache[host]

    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        if infos:
            ip = infos[0][4][0]
            with _dns_host_lock:
                _dns_host_cache[host] = (ip, now + 300)
            return ip
    except Exception:
        pass
    return None

class TokenBucket:
    """
    Token-bucket rate limiter to protect the shared 10 Mbps Wi-Fi connection.
    1 Mbps = 125,000 bytes/sec.
    """
    def __init__(self, rate_mbps: float):
        self.rate = max(0.0, rate_mbps) * 125000.0  # bytes/sec
        self.capacity = max(self.rate * 1.5, 65536.0) # allow small burst
        self.tokens = self.capacity
        self.last_update = time.perf_counter()

    def consume(self, amount: int):
        if self.rate <= 0:
            return
        now = time.perf_counter()
        elapsed = now - self.last_update
        self.last_update = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        if self.tokens < amount:
            needed = amount - self.tokens
            sleep_time = needed / self.rate
            if 0 < sleep_time < 2.0:
                time.sleep(sleep_time)
            self.tokens = 0
        else:
            self.tokens -= amount

class PortProxyServer:
    def __init__(self, port: int, store: HubStore, dns_firewall: Optional[Any] = None):
        self.port = port
        self.store = store
        self.dns_firewall = dns_firewall
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.running = True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", self.port))
            self.sock.listen(128)
            self.thread = threading.Thread(target=self._listen_loop, daemon=True, name=f"ProxyPort-{self.port}")
            self.thread.start()
        except Exception as e:
            print(f"[WARN] Proxy port {self.port} could not be bound (may already be in use): {e}")

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def _listen_loop(self):
        while self.running:
            try:
                client_sock, client_addr = self.sock.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr),
                    daemon=True
                ).start()
            except Exception:
                if not self.running:
                    break

    def _handle_client(self, client_sock: socket.socket, client_addr: Tuple[str, int]):
        upstream_sock = None
        try:
            try:
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass
            client_sock.settimeout(10.0)
            initial_data = client_sock.recv(BUFFER_SIZE)
            if not initial_data:
                client_sock.close()
                return

            # Check if this client IP is blocked / kicked
            if client_addr and client_addr[0] and self.store.is_client_blocked(client_addr[0]):
                client_sock.close()
                return

            # Check global proxy gateway toggle
            if self.store.get_settings().get("proxy_gateway_enabled", "1") != "1":
                if initial_data.startswith(b"CONNECT "):
                    client_sock.sendall(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n\r\nProxy Gateway is OFF\r\n")
                else:
                    client_sock.sendall(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Type: text/plain\r\n\r\nProxy Gateway is turned OFF in Dashboard.\r\n")
                client_sock.close()
                return

            # Check assigned proxy for this port (Auto resolve if universal port 8100)
            active_port = self.store.get_port_for_client_ip(client_addr[0]) if self.port == 8100 else self.port
            proxy_cfg = self.store.get_port_proxy_config(active_port)
            rate_limit_mbps = float(proxy_cfg.get("rate_limit_mbps", 0.0)) if proxy_cfg else 0.0
            self.store.set_port_status(active_port, "ACTIVE")

            # Check if HTTP CONNECT (HTTPS Tunnel)
            if initial_data.startswith(b"CONNECT "):
                target_host, target_port = self._parse_connect(initial_data)
                if not target_host or not target_port:
                    client_sock.close()
                    return

                # Ad / Tracker Shield Block
                if self.dns_firewall and self.store.get_settings().get("dns_adblock_enabled") == "1":
                    if self.dns_firewall._is_blocked(target_host):
                        client_sock.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nBlocked by OFFICIALUM1 Ad Shield\r\n")
                        client_sock.close()
                        return

                if proxy_cfg and proxy_cfg.get("host"):
                    upstream_sock = self._connect_via_proxy(proxy_cfg, target_host, target_port)
                    if not upstream_sock:
                        # Auto-failover to direct connection so client internet is never stranded
                        upstream_sock = self._connect_direct(target_host, target_port)
                else:
                    upstream_sock = self._connect_direct(target_host, target_port)

                if upstream_sock:
                    client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    self._splice_sockets(client_sock, upstream_sock, rate_limit_mbps, active_port=active_port)
                else:
                    client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")

            # Plain HTTP request
            elif any(initial_data.startswith(m) for m in (b"GET ", b"POST ", b"HEAD ", b"PUT ", b"DELETE ", b"OPTIONS ")):
                target_host, target_port = self._parse_http_host(initial_data)
                if not target_host:
                    client_sock.close()
                    return

                # Ad / Tracker Shield Block
                if self.dns_firewall and self.store.get_settings().get("dns_adblock_enabled") == "1":
                    if self.dns_firewall._is_blocked(target_host):
                        client_sock.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nBlocked by OFFICIALUM1 Ad Shield\r\n")
                        client_sock.close()
                        return

                if proxy_cfg and proxy_cfg.get("host") and proxy_cfg.get("protocol", "socks5").lower() == "http":
                    upstream_sock = self._connect_via_proxy(proxy_cfg, target_host, target_port)
                    payload = initial_data
                else:
                    if proxy_cfg and proxy_cfg.get("host"):
                        upstream_sock = self._connect_via_proxy(proxy_cfg, target_host, target_port)
                    else:
                        upstream_sock = self._connect_direct(target_host, target_port)
                    payload = self._strip_absolute_uri(initial_data)

                if not upstream_sock:
                    upstream_sock = self._connect_direct(target_host, target_port)

                if upstream_sock:
                    upstream_sock.sendall(payload)
                    self._splice_sockets(client_sock, upstream_sock, rate_limit_mbps, active_port=active_port)
                else:
                    client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")


            else:
                client_sock.close()

        except Exception:
            pass
        finally:
            if client_sock:
                try: client_sock.close()
                except Exception: pass
            if upstream_sock:
                try: upstream_sock.close()
                except Exception: pass

    def _parse_connect(self, data: bytes) -> Tuple[Optional[str], Optional[int]]:
        try:
            line = data.split(b"\r\n")[0].decode("utf-8", errors="ignore")
            target = line.split(" ")[1]
            if ":" in target:
                host, port_str = target.split(":")
                return host, int(port_str)
            return target, 443
        except Exception:
            return None, None

    def _parse_http_host(self, data: bytes) -> Tuple[Optional[str], int]:
        try:
            lines = data.split(b"\r\n")
            for line in lines:
                if line.lower().startswith(b"host:"):
                    host_val = line.split(b":", 1)[1].strip().decode("utf-8", errors="ignore")
                    if ":" in host_val:
                        h, p = host_val.split(":")
                        return h, int(p)
                    return host_val, 80
        except Exception:
            pass
        return None, 80

    def _strip_absolute_uri(self, data: bytes) -> bytes:
        from urllib.parse import urlsplit
        try:
            first_line_end = data.find(b"\r\n")
            if first_line_end != -1:
                first_line = data[:first_line_end]
                parts = first_line.split(b" ")
                if len(parts) >= 3 and parts[1].lower().startswith((b"http://", b"https://")):
                    url_str = parts[1].decode("utf-8", errors="ignore")
                    u = urlsplit(url_str)
                    path = u.path or "/"
                    if u.query:
                        path += "?" + u.query
                    new_first = parts[0] + b" " + path.encode("utf-8") + b" " + parts[2]
                    return new_first + data[first_line_end:]
        except Exception:
            pass
        return data


    def _connect_direct(self, host: str, port: int) -> Optional[socket.socket]:
        ip = _resolve_host_cached(host) or host
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            try:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
            except Exception:
                pass
            s.connect((ip, port))
            s.setblocking(True)
            return s
        except Exception:
            pass

        try:
            s = socket.create_connection((host, port), timeout=6.0)
            try:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
            except Exception:
                pass
            s.setblocking(True)
            return s
        except Exception:
            return None

    def _connect_via_proxy(self, proxy_cfg: Dict[str, Any], target_host: str, target_port: int) -> Optional[socket.socket]:
        proto = proxy_cfg.get("protocol", "socks5").lower()
        phost = proxy_cfg["host"]
        pport = int(proxy_cfg["port"])
        puser = proxy_cfg.get("username", "")
        ppass = proxy_cfg.get("password", "")

        if proto in ("socks5", "socks5h"):
            return self._connect_via_socks5(phost, pport, puser, ppass, target_host, target_port)
        else:
            return self._connect_via_http_proxy(phost, pport, puser, ppass, target_host, target_port)

    def _connect_via_socks5(self, phost: str, pport: int, puser: str, ppass: str, target_host: str, target_port: int) -> Optional[socket.socket]:
        try:
            s = socket.create_connection((phost, pport), timeout=8.0)
            
            # SOCKS5 Greeting
            if puser and ppass:
                s.sendall(b"\x05\x02\x00\x02") # supports NO_AUTH and USER_PASS
            else:
                s.sendall(b"\x05\x01\x00")     # NO_AUTH

            resp = s.recv(2)
            if len(resp) < 2 or resp[0] != 5:
                s.close()
                return None

            auth_method = resp[1]
            if auth_method == 2: # Username/Password auth
                u_bytes = puser.encode("utf-8")
                p_bytes = ppass.encode("utf-8")
                auth_req = b"\x01" + bytes([len(u_bytes)]) + u_bytes + bytes([len(p_bytes)]) + p_bytes
                s.sendall(auth_req)
                auth_resp = s.recv(2)
                if len(auth_resp) < 2 or auth_resp[1] != 0:
                    s.close()
                    return None
            elif auth_method != 0:
                s.close()
                return None

            # SOCKS5 Connect Request (Domain name format)
            host_bytes = target_host.encode("utf-8")
            port_bytes = target_port.to_bytes(2, "big")
            req = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + port_bytes
            s.sendall(req)

            conn_resp = s.recv(4)
            if len(conn_resp) < 4 or conn_resp[1] != 0: # 0 = succeeded
                s.close()
                return None

            # Drain remainder of bind response
            addr_type = conn_resp[3]
            if addr_type == 1: s.recv(6) # IPv4 + port
            elif addr_type == 3:
                dlen = s.recv(1)[0]
                s.recv(dlen + 2)
            elif addr_type == 4: s.recv(18) # IPv6 + port

            return s
        except Exception:
            return None

    def _connect_via_http_proxy(self, phost: str, pport: int, puser: str, ppass: str, target_host: str, target_port: int) -> Optional[socket.socket]:
        try:
            s = socket.create_connection((phost, pport), timeout=8.0)
            connect_req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n"
            if puser and ppass:
                creds = base64.b64encode(f"{puser}:{ppass}".encode()).decode()
                connect_req += f"Proxy-Authorization: Basic {creds}\r\n"
            connect_req += "\r\n"

            s.sendall(connect_req.encode())
            resp = s.recv(4096)
            if b"200 " in resp or b"200\r\n" in resp:
                return s
            s.close()
            return None
        except Exception:
            return None

    def _splice_sockets(self, s1: socket.socket, s2: socket.socket, rate_limit_mbps: float = 0.0, active_port: Optional[int] = None):
        try:
            s1.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s2.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s1.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
            s1.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
            s2.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
            s2.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
        except Exception:
            pass
        limiter = TokenBucket(rate_limit_mbps) if rate_limit_mbps > 0 else None
        sockets = [s1, s2]
        s1.settimeout(60.0)
        s2.settimeout(60.0)
        effective_port = str(active_port if active_port else self.port)

        while True:
            rlist, _, xlist = select.select(sockets, [], sockets, 60.0)
            if xlist or not rlist:
                break

            for s in rlist:
                other = s2 if s is s1 else s1
                try:
                    data = s.recv(BUFFER_SIZE)
                    if not data:
                        return
                    from core.store import traffic_tracker
                    traffic_tracker.record(effective_port, len(data))
                    if limiter and s is s2:  # Remote to client downstream
                        limiter.consume(len(data))
                    other.sendall(data)
                except Exception:
                    return

class MultiPortManager:
    def __init__(self, store: HubStore, dns_firewall: Optional[Any] = None):
        self.store = store
        self.dns_firewall = dns_firewall
        self.servers: Dict[int, PortProxyServer] = {}

    def start_all(self):
        # 1. Universal Auto-Port 8100 (Auto resolves any laptop's dedicated proxy by IP)
        try:
            universal_server = PortProxyServer(8100, self.store, self.dns_firewall)
            universal_server.start()
            self.servers[8100] = universal_server
        except Exception as e:
            print(f"[OFFICIALUM1] Warning: Port 8100 Auto-Port failed to bind: {e}")

        # 2. Dedicated Ports 8101 - 8110
        ports_data = self.store.get_ports()
        for p in ports_data:
            port = p["port"]
            server = PortProxyServer(port, self.store, self.dns_firewall)
            server.start()
            self.servers[port] = server
        print(f"[OFFICIALUM1] Active Multi-Port Proxy Gateway running on Universal Port 8100 & Ports 8101 - 8110")

    def stop_all(self):
        for port, server in self.servers.items():
            server.stop()
        self.servers.clear()
        print("[OFFICIALUM1] Multi-Port Proxy Gateway stopped.")
