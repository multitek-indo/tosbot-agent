"""Bounded private-network diagnostic. Never invokes a shell or arbitrary hostnames."""
from __future__ import annotations
import ipaddress
import re
import subprocess

PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10'
))


def valid_ip(value: str) -> str | None:
    try:
        ip=ipaddress.IPv4Address(str(value or '').strip())
    except (ipaddress.AddressValueError,ValueError,TypeError):
        return None
    if ip.is_multicast or ip.is_unspecified or ip.is_loopback:
        return None
    return str(ip) if any(ip in net for net in PRIVATE_NETWORKS) else None


def parse_ping(text: str) -> tuple[str, int] | None:
    low=str(text or '').lower().strip()
    if not re.search(r'\b(ping|tes koneksi|cek koneksi|uji koneksi)\b',low):
        return None
    found=re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',low)
    if not found:
        return '',4
    count=4
    number=re.search(r'\b(?:sebanyak|sebnyak|ulangi|ulang|kirim|count|-c)\s*(\d+)\s*(?:kali|x|paket)?\b',low)
    if not number:
        number=re.search(r'\b(\d+)\s*(?:kali|x)\b',low)
    if number:
        count=max(1,min(4,int(number.group(1))))
    return found.group(),count


def ping_private(address: str, count: int = 4, runner=None) -> str:
    ip=valid_ip(address)
    if not ip:
        return '⛔ Ping dibatasi untuk alamat IPv4 privat (LAN atau Tailscale), misalnya 192.168.0.1.'
    try:
        n=int(count)
    except (TypeError,ValueError):
        n=4
    n=max(1,min(n,4))
    command=['ping','-n','-c',str(n),'-W','2','-w','12',ip]
    try:
        done=(runner or subprocess.run)(command,capture_output=True,text=True,timeout=16,check=False)
    except FileNotFoundError:
        return '❌ Program ping belum terpasang. Admin perlu memasang paket iputils-ping.'
    except subprocess.TimeoutExpired:
        return f'⚠️ Ping ke {ip} mencapai batas waktu (12 detik).'
    except OSError:
        return '❌ Gagal menjalankan tool ping di VPS.'
    body='\n'.join((done.stdout or done.stderr or '').splitlines()[-7:])[:1200]
    if done.returncode==0:
        return f'✅ Ping {ip}, {n} paket:\n{body}'
    return f'⚠️ Ping {ip} selesai dengan exit {done.returncode} (host mungkin tidak merespons):\n{body}'
