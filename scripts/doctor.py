#!/usr/bin/env python3
"""TosBot offline config audit and optional live provider tests. Never prints secrets."""
import argparse
import os
import re
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print('httpx belum ada; jalankan dokter dengan Python virtualenv /opt/tosbot-ai/venv/bin/python')
    sys.exit(2)

CONF=Path('/etc/tosbot-ai/tosbot.env')


def load_config():
    cfg={}
    duplicates=[]
    if not CONF.is_file():
        print('ERROR: Konfigurasi tidak ditemukan:', CONF)
        sys.exit(2)
    # Read simple EnvironmentFile key=value format; do not execute as shell script.
    for line in CONF.read_text(encoding='utf-8').splitlines():
        found=re.match(r'^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*$', line)
        if not found: continue
        k,v=found.groups()
        if k in cfg: duplicates.append(k)
        if len(v)>=2 and v[0]==v[-1] and v[0] in (chr(34),chr(39)):
            v=v[1:-1]
        cfg[k]=v
    return cfg,duplicates


def verdict(status):
    if status in (401,403): return 'autentikasi atau izin API key ditolak'
    if status==400: return 'parameter atau model tidak diterima'
    if status==404: return 'model atau endpoint tidak ditemukan / tidak tersedia'
    if status==429: return 'rate limit atau kuota habis'
    if 500<=status<600: return 'gangguan provider (HTTP 5xx)'
    return 'HTTP error'


def test_provider(name, key, url, model):
    try:
        if name=='groq':
            payload={'model':model,'messages':[{'role':'user','content':'Balas satu kata: OK'}],
                     'max_completion_tokens':96}
            if model in ('openai/gpt-oss-20b','openai/gpt-oss-120b'):
                payload.update(reasoning_effort='low',include_reasoning=False)
        else:
            payload={'model':model,'messages':[{'role':'user','content':'Balas satu kata: OK'}], 'max_tokens':100}
        with httpx.Client(timeout=20.0) as client:
            response=client.post(url.rstrip('/')+'/chat/completions',
                 headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json=payload)
        if response.status_code!=200:
            print(f'  {name.upper()}: HTTP {response.status_code} - {verdict(response.status_code)}')
            return False
        data=response.json()
        content=data['choices'][0]['message']['content']
        if isinstance(content,str) and content.strip():
            print(f'  {name.upper()}: OK (HTTP 200, ada respons teks)')
            return True
        print(f'  {name.upper()}: HTTP 200, respons kosong')
        return False
    except httpx.TimeoutException:
        print(f'  {name.upper()}: timeout (periksa internet keluar/DNS/provider)')
    except httpx.RequestError:
        print(f'  {name.upper()}: gagal tersambung (periksa DNS/TLS/proxy)')
    except (ValueError, KeyError, IndexError, TypeError):
        print(f'  {name.upper()}: format respons tidak sesuai')
    return False


def main():
    ap=argparse.ArgumentParser(description='Pemeriksa TosBot AI: tidak mencetak token atau API key')
    ap.add_argument('--test-api',action='store_true',help='Lakukan panggilan kecil ke Groq dan Gemini (dapat dikenai biaya)')
    args=ap.parse_args()
    if os.geteuid()!=0:
        print('Jalankan dengan sudo agar dapat membaca file konfigurasi root-owned.')
        return 2
    cfg,dup=load_config()
    print('TosBot diagnostic v1.2 - token dan API key TIDAK akan ditampilkan')
    print('Konfigurasi:',CONF)
    print('AI_PRIMARY:',cfg.get('AI_PRIMARY','[default groq]'))
    if dup:print('WARNING: Variabel duplikat:',','.join(sorted(set(dup))))
    for k in ('TELEGRAM_BOT_TOKEN','TELEGRAM_OWNER_ID','GROQ_API_KEY','GEMINI_API_KEY'):
        val=cfg.get(k,'')
        ok=bool(val) and not val.startswith('ISI_') and val!='ISI_TOKEN_BOTFATHER'
        if k=='TELEGRAM_OWNER_ID':ok=bool(val) and val!='0' and val.isdigit()
        print(k+':', 'ADA' if ok else 'BELUM DIISI/INVALID')
    for name, keyvar, modelvar, urlvar, default_model, default_url in (
        ('groq','GROQ_API_KEY','GROQ_MODEL','GROQ_BASE_URL','openai/gpt-oss-120b','https://api.groq.com/openai/v1'),
        ('gemini','GEMINI_API_KEY','GEMINI_MODEL','GEMINI_BASE_URL','gemini-3.1-flash-lite','https://generativelanguage.googleapis.com/v1beta/openai')):
        model=cfg.get(modelvar,default_model)
        url=cfg.get(urlvar,default_url)
        print(name.upper()+'_MODEL:',model)
        allowed_url=(url.startswith('https://api.groq.com/openai/v1') if name=='groq'
                     else url.startswith('https://generativelanguage.googleapis.com/v1beta/openai'))
        print(name.upper()+'_ENDPOINT:', 'OK' if allowed_url else 'PERIKSA URL (nonstandar)')
        if args.test_api:
            key=cfg.get(keyvar,'')
            if key and not key.startswith('ISI_') and allowed_url:
                test_provider(name,key,url,model)
            else:
                print('  '+name.upper()+': DILEWATI (key belum diisi/URL tidak valid)')
    if not args.test_api:
        print('Untuk menguji koneksi API, jalankan ulang dengan --test-api')
    return 0

if __name__=='__main__':sys.exit(main())
