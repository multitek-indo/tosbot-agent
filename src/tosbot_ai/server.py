from __future__ import annotations
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from .config import Settings

RE_SERVICE=re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.@-]{0,80}$')

def meminfo():
    values={}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if ':' in line:
                key,val=line.split(':',1)
                values[key]=int(val.strip().split()[0])*1024
    except (OSError,ValueError): pass
    return values

def size(n:int)->str:
    for u in ('B','KiB','MiB','GiB','TiB'):
        if n<1024 or u=='TiB':return f'{n:.1f} {u}' if isinstance(n,float) else f'{n} {u}'
        n=n/1024
    return str(n)

def disk()->str:
    d=shutil.disk_usage('/')
    return (f'💽 Penyimpanan VPS (/):\nTotal: {size(d.total)}\n'
            f'Terpakai: {size(d.used)}\nTersisa: {size(d.free)}\n'
            f'Pemakaian: {d.used/d.total*100:.1f}%')

def memory()->str:
    m=meminfo()
    total=m.get('MemTotal',0); avail=m.get('MemAvailable',0)
    swap=m.get('SwapTotal',0); swapfree=m.get('SwapFree',0)
    if not total: return 'Informasi RAM tidak tersedia.'
    return (f'🧠 RAM VPS:\nTotal: {size(total)}\nTerpakai (estimasi): {size(total-avail)}\n'
            f'Tersedia: {size(avail)}\nSwap: {size(swap-swapfree)} / {size(swap)}')

def uptime()->str:
    try:
        sec=float(Path('/proc/uptime').read_text().split()[0]);days=int(sec//86400);hrs=int(sec%86400//3600)
        return f'{days} hari {hrs} jam'
    except (OSError,ValueError,IndexError):return 'tidak tersedia'

def status()->str:
    return f'🖥️ Server: {socket.gethostname()}\nUptime: {uptime()}\n\n{disk()}\n\n{memory()}'

def validate_service(s:Settings,requested:str)->str|None:
    requested=str(requested or '').strip()
    # Python allowlist is AND-ed with the immutable root-owned wrapper allowlist.
    if RE_SERVICE.fullmatch(requested) and requested in s.allowed_services:return requested
    return None

def service_status(s:Settings,requested:str)->str:
    name=validate_service(s,requested)
    if not name:return 'Layanan tidak ada dalam ADMIN_ALLOWED_SERVICES. Hubungi admin VPS untuk menambah izin.'
    try:
        p=subprocess.run(['systemctl','is-active','--',name],capture_output=True,text=True,timeout=8,check=False)
        return f'Status {name}: {p.stdout.strip() or p.stderr.strip() or "tidak diketahui"}'
    except (OSError,subprocess.TimeoutExpired):return 'Tidak bisa membaca status layanan.'

def restart_service(s:Settings,requested:str)->str:
    name=validate_service(s,requested)
    if not name:return 'Restart DITOLAK: layanan tidak termasuk allowlist.'
    try:
        p=subprocess.run(['sudo','-n','/usr/local/sbin/tosbot-ai-service-ctl','restart',name],
                         capture_output=True,text=True,timeout=35,check=False)
        return f'✅ {name}: restart berhasil.' if p.returncode==0 else f'❌ Restart {name} gagal (exit {p.returncode}). Periksa journalctl/sudoers.'
    except (OSError,subprocess.TimeoutExpired):return f'❌ Restart {name} gagal atau timeout.'
