import socket
import threading
import time
from update_page import socks5_probe

def run_server(handler):
    ready = threading.Event()
    result = {}
    def serve():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            result["port"] = s.getsockname()[1]
            ready.set()
            conn, _ = s.accept()
            with conn:
                conn.settimeout(2)
                handler(conn)
    th = threading.Thread(target=serve, daemon=True)
    th.start()
    ready.wait(2)
    return result["port"], th

def recv_exact(conn, n):
    data = b""
    while len(data) < n:
        part = conn.recv(n - len(data))
        if not part:
            raise EOFError("closed")
        data += part
    return data

def success_handler(conn):
    assert recv_exact(conn, 3) == b"\x05\x01\x00"
    conn.sendall(b"\x05\x00")
    head = recv_exact(conn, 4)
    assert head[:3] == b"\x05\x01\x00"
    atyp = head[3]
    if atyp == 1:
        recv_exact(conn, 4)
    elif atyp == 3:
        ln = recv_exact(conn, 1)[0]
        recv_exact(conn, ln)
    else:
        raise AssertionError(f"unexpected ATYP {atyp}")
    recv_exact(conn, 2)
    conn.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")

def reject_method_handler(conn):
    recv_exact(conn, 3)
    conn.sendall(b"\x05\xff")

def reject_connect_handler(conn):
    recv_exact(conn, 3)
    conn.sendall(b"\x05\x00")
    head = recv_exact(conn, 4)
    atyp = head[3]
    if atyp == 1:
        recv_exact(conn, 4)
    elif atyp == 3:
        ln = recv_exact(conn, 1)[0]
        recv_exact(conn, ln)
    recv_exact(conn, 2)
    conn.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")

proxy = {"protocol":"socks5","server":"127.0.0.1","source":"test"}

port, th = run_server(success_handler)
p, ms = socks5_probe({**proxy, "port":port}, target_host="149.154.167.50", target_port=443, timeout=2)
assert p["server"] == "127.0.0.1"
assert isinstance(ms, int) and ms >= 0
th.join(2)

port, th = run_server(reject_method_handler)
p, ms = socks5_probe({**proxy, "port":port}, target_host="149.154.167.50", target_port=443, timeout=2)
assert p is not None and ms is None
th.join(2)

port, th = run_server(reject_connect_handler)
p, ms = socks5_probe({**proxy, "port":port}, target_host="149.154.167.50", target_port=443, timeout=2)
assert p is not None and ms is None
th.join(2)

print("SOCKS5 handshake/connect tests OK")
