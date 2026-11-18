#!/usr/bin/env python3
from __future__ import annotations
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import storage

if __name__=='__main__':
    if os.geteuid()==0:
        sys.exit('Jalankan sebagai user tosbot-dashboard, bukan root.')
    username='admin'
    print('Atur password untuk pengguna admin dashboard (minimal 10 karakter).')
    a=getpass.getpass('Password baru: ')
    b=getpass.getpass('Ulangi password: ')
    if a!=b:sys.exit('Password berbeda; tidak ada perubahan.')
    storage.initialize()
    storage.set_password(username,a)
    print('Password admin disimpan sebagai hash scrypt; sesi lama dicabut.')
