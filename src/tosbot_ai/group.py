"""Mention-only, unprivileged Telegram group assistant.

This module intentionally never calls Engine.handle() or Terminal.handle().
It only exposes a small read-only subset and isolated Groq/Gemini chat.
"""
from __future__ import annotations

import re
import time
import ipaddress
import subprocess
from collections import defaultdict, deque

from .ai import AI
from .conversation import _safe_memory
from .server import disk, memory, uptime, status, service_status

GROUP_HELP = (
    '👥 TosBot di grup: mention @username_bot, atau Reply pesan TosBot.\n'
    'Contoh: @username_bot halo; @username_bot cek RAM; @username_bot cek disk.\n'
    'Chat biasa dapat dibantu Groq/Gemini.\n'
    'Perintah operasional read-only (jika diaktifkan untuk grup ini): ping, df -h, free -h, uptime, hostname, status layanan yang diizinkan.\n'
    'Terminal /sh, /sudo, apt, perubahan VPS, invoice, pengingat, dan data keuangan '
    'tidak tersedia untuk anggota grup. Gunakan chat pribadi pemilik.'
)

# Strictly deny privileged/personal workflows before invoking an LLM.
FORBIDDEN = re.compile(
    r'(?i)(?:^|\b)(?:/sh|/sudo|/auth|/job|/terminal|/root|/login|/reboot|'
    r'sudo|su\s+-?|bash|shell|terminal|apt(?:-get)?|dpkg|rm\b|chmod|chown|'
    r'mkdir|rmdir|reboot|shutdown|systemctl|restart|stop\s+service|'
    r'instal(?:l)?|hapus\s+(?:file|folder)|buat\s+(?:folder|direktori)|'
    r'file|folder|direktori|tree|/etc|/root|/home|\bcat\s+/|'
    r'invoice|penawaran|quotation|pdf|rekening|saldo|pemasukan|pengeluaran|'
    r'keuangan|tagihan|pengingat|ingatkan|reminder|jadwalkan)\b'
)


# The group can invoke only fixed, read-only subprocesses with argv lists.
# It never executes an arbitrary shell or invokes the root broker.
HOST_RE = re.compile(r"(?i)^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")


def _safe_ping_host(value: str) -> str | None:
    host = value.strip().rstrip('.').lower()
    if not host or host.startswith('-') or len(host) > 253 or '..' in host:
        return None
    try:
        addr = ipaddress.ip_address(host)
        if addr.version != 4 or addr.is_multicast or addr.is_unspecified or addr.is_loopback:
            return None
        return str(addr)
    except ValueError:
        pass
    if not HOST_RE.fullmatch(host):
        return None
    if any(not part or len(part) > 63 or part.startswith('-') or part.endswith('-') for part in host.split('.')):
        return None
    return host


def _ping_command(text: str) -> tuple[str, int] | None:
    # Exact shell syntax or predictable Indonesian forms; not an LLM interpretation.
    m = re.fullmatch(r'(?i)ping\s+(?:ke\s+)?(?P<host>[A-Za-z0-9.:-]+)(?:\s+sebanyak\s+(?P<count>[1-4])\s+kali)?', text.strip())
    if m:
        host = _safe_ping_host(m.group('host'))
        return (host, int(m.group('count') or 4)) if host else None
    m = re.fullmatch(r'(?i)ping\s+-c\s+(?P<count>[1-4])\s+(?P<host>[A-Za-z0-9.:-]+)', text.strip())
    if m:
        host = _safe_ping_host(m.group('host'))
        return (host, int(m.group('count'))) if host else None
    return None


def _run_group_ping(text: str) -> str | None:
    parsed = _ping_command(text)
    if not parsed:
        return None
    host, count = parsed
    try:
        result = subprocess.run(
            ['ping', '-n', '-c', str(count), '-W', '2', '-w', '12', host],
            capture_output=True, text=True, timeout=15, check=False)
        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()
        output = '\n'.join(x for x in (stdout,stderr) if x)
        return f'📡 Ping {host} ({count} paket; exit {result.returncode}):\n{output[:2100] or "Tidak ada output."}'
    except (OSError, subprocess.TimeoutExpired):
        return 'Ping gagal atau melewati batas waktu.'


def _group_ops(s, text: str) -> str | None:
    text = text.strip()
    t = text.casefold()
    if t.startswith('ping '):
        return _run_group_ping(text) or 'Format: ping google.com, ping -c 4 google.com, atau ping ke google.com sebanyak 4 kali.'
    if t in {'df -h', 'df', 'free -h', 'free', 'uptime', 'hostname', 'pwd'}:
        if t.startswith('df'): return disk()
        if t.startswith('free'): return memory()
        if t == 'uptime': return f'⏱️ Uptime VPS: {uptime()}'
        if t == 'hostname':
            import socket
            return f'🖥️ Hostname: {socket.gethostname()}'
        return 'Direktori kerja service: /opt/tosbot-ai (bukan terminal interaktif).'
    m = re.fullmatch(r'(?i)(?:systemctl\s+is-active|status(?:\s+layanan|\s+service)?)\s+([a-zA-Z0-9_.@-]{1,81})',text)
    if m:
        return service_status(s,m.group(1))
    return None

class GroupRateLimiter:
    """Small in-memory quota; prevents accidental group API-cost abuse."""
    def __init__(self):
        self.events: dict[tuple[int, int], deque[float]] = defaultdict(deque)
        self.group_events: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, group_id: int, user_id: int) -> bool:
        now = time.monotonic()
        user = self.events[(group_id, user_id)]
        group = self.group_events[group_id]
        while user and now - user[0] > 30:
            user.popleft()
        while group and now - group[0] > 60:
            group.popleft()
        if len(user) >= 5 or len(group) >= 30:
            return False
        user.append(now)
        group.append(now)
        # Reap stale buckets to bound key growth.
        if len(self.events) > 1000:
            self.events = defaultdict(deque, {k:v for k,v in self.events.items() if v and now-v[-1] < 60})
        if len(self.group_events) > 200:
            self.group_events = defaultdict(deque, {k:v for k,v in self.group_events.items() if v and now-v[-1] < 60})
        return True


class GroupAssistant:
    def __init__(self, settings, store, ai=None):
        self.settings = settings
        self.store = store
        self.ai = ai or AI(settings)
        self.limiter = GroupRateLimiter()

    def handle(self, text: str, chat_id: int, user_id: int, topic_id: int | None = None) -> str:
        if not self.limiter.allow(chat_id, user_id):
            return 'Terlalu banyak permintaan. Coba lagi sebentar.'
        text = (text or '').strip()
        if not text or text.lower() in {'halo', 'hai', 'pagi', 'hello', 'test', 'tes'}:
            return 'Halo! Ada yang ingin dibantu? 😊'
        if len(text) > 1500:
            return 'Pesan terlalu panjang (maksimal 1500 karakter di grup).'
        if text.lower() in {'help', '/help', 'bantuan', '/start', 'mulai'}:
            return GROUP_HELP
        if text.lower() in {'/groupid', 'groupid', 'id grup', 'id group'}:
            return f'ID grup ini: {chat_id} (bukan ID pribadi anggota).'
        # Explicit, group-scoped, read-only commands only. Group ID MUST be allowlisted.
        if (getattr(self.settings, 'group_ops_enabled', False) and
            self.settings.allowed_group_ids and chat_id in self.settings.allowed_group_ids):
            reply = _group_ops(self.settings, text)
            if reply is not None:
                return reply
        # Check BEFORE read-only diagnostic shortcuts: do not let privileged instructions
        # such as "sudo ... disk" be mistaken for a safe request.
        if FORBIDDEN.search(text) or text.startswith('/'):
            return ('⛔ Perintah administrasi, akses file, dokumen pribadi dan tugas yang '
                    'mengubah data tidak tersedia di grup. Hubungi pemilik melalui chat pribadi.')
        low = text.casefold()
        if re.search(r'\b(?:status|kondisi|info|cek)\b', low) and re.search(r'\b(?:server|vps)\b', low):
            return status()
        if re.search(r'\b(ram|memory|memori)\b',low) and re.search(r'\b(cek|status|berapa|kapasitas|lihat|info|kondisi|sisa|piro|saiki|sekarang)\b',low):
            return memory()
        if re.search(r'\b(disk|storage|penyimpanan|hardisk|ssd)\b',low) and re.search(r'\b(cek|status|berapa|kapasitas|lihat|info|kondisi|sisa|piro|saiki|sekarang)\b',low):
            return disk()
        if re.fullmatch(r'(?:cek\s+)?(?:uptime|lama\s+server\s+nyala)',low):
            return f'⏱️ Uptime VPS: {uptime()}'
        # History is per group + topic + sender, never owner/private memory.
        history_key = f'group_chat:{chat_id}:{topic_id or 0}:{user_id}'
        history = self.store.get_kv(history_key, [])[-12:]
        try:
            answer = self.ai.converse_group(text, [dict(turn) for turn in history])[:3300]
        except RuntimeError:
            return 'AI sedang tidak tersedia. Coba beberapa saat lagi.'
        safe_user = _safe_memory(text, 700)
        safe_answer = _safe_memory(answer, 1000)
        history.extend([{'role':'user','content':safe_user}, {'role':'assistant','content':safe_answer}])
        self.store.set_kv(history_key, history[-12:])
        return answer
