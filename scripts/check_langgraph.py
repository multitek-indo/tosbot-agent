#!/usr/bin/env python3
"""Local, offline LangGraph checkpoint health-check for TosBot service account.

Does not use Groq/Gemini/Telegram credentials or touch production DB.
Exit: 0 all checks pass, 2 missing runtime/dependencies, 3 failed persistence.
"""
from __future__ import annotations
import argparse
from importlib.metadata import version, PackageNotFoundError
import logging
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault('LANGGRAPH_STRICT_MSGPACK','true')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')

class ProbeAI:
    def understand(self,text,history,draft):
        return {'action':'chat', 'data':{}, 'history_len':len(history),
                'draft_seen':bool(draft), 'message':text}

def main() -> int:
    parser=argparse.ArgumentParser(description='TosBot LangGraph SQLite persistence health-check (offline)')
    parser.add_argument('--state-dir',default='/var/lib/tosbot-ai',help='Direktori data bot yang harus dapat ditulis oleh user service')
    args=parser.parse_args()
    if os.geteuid()==0:
        print('FAIL: Jangan jalankan sebagai root. Gunakan: sudo -u tosbot-ai -g tosbot-ai ...')
        return 2
    for pkg in ('langgraph','langgraph-checkpoint-sqlite','langgraph-checkpoint'):
        try: print(f'OK DEPENDENCY {pkg}=={version(pkg)}')
        except PackageNotFoundError:
            print(f'FAIL DEPENDENCY {pkg} tidak terpasang pada Python ini')
            return 2
    try:
        from tosbot_ai.conversation import ConversationGraph
    except Exception as e:
        print('FAIL IMPORT',type(e).__name__)
        return 2
    state=Path(args.state_dir)
    if not state.is_dir() or not os.access(state,os.R_OK|os.W_OK|os.X_OK):
        print('FAIL PERMISSIONS direktori data tidak dapat dibaca/ditulis user service:',str(state))
        return 2
    try:
        with tempfile.TemporaryDirectory(prefix='.langgraph-selftest-',dir=state) as temp:
            dbpath=Path(temp)/'checkpoints.sqlite3'
            ai=ProbeAI()
            owner=19740401  # independent temporary thread; real owner's checkpoints untouched
            flow=ConversationGraph(ai,owner,dbpath)
            first=flow.interpret('halo',None,[])
            if first['history_len'] != 0:
                raise AssertionError('Riwayat percakapan awal bukan kosong')
            flow.remember('halo','siap membantu')
            flow.close()
            revived=ConversationGraph(ai,owner,dbpath)
            turns=revived.recent()
            if len(turns)!=2:
                raise AssertionError(f'Checkpoint tidak persisten: {len(turns)} pesan, harus 2')
            second=revived.interpret('cek disk',None,[])
            if second['history_len']!=2:
                raise AssertionError('Context setelah reload tidak ditemukan')
            # Check that common secrets are not persisted in the graph input.
            secret='password=TESRAHASIA123'
            clean=revived.interpret(secret,None,[])
            if 'TESRAHASIA123' in clean.get('message',''):
                raise AssertionError('Sanitasi input checkpoint tidak aktif')
            revived.close()
            print('OK CHECKPOINT SQLite bisa menyimpan dan membaca ulang percakapan')
            print('OK REOPEN konteks bertahan setelah instance/connection dibuat ulang')
            print('OK SECRET_REDACTION kredensial sederhana tidak disimpan mentah sebagai input graph')
            print('OK PERMISSIONS write/read DB oleh akun service')
            print('OK RESULT LangGraph tersedia dan tes persistensi lulus')
            return 0
    except Exception as exc:
        print('FAIL LANGGRAPH',type(exc).__name__,str(exc)[:160])
        return 3

if __name__=='__main__':
    raise SystemExit(main())
