#!/usr/bin/env python3
"""Root-only, one-way, sanitized snapshot of TosBot business tables.

Never copies bot KV, conversation checkpoints, drafts, API tokens, or audit text.
Never writes to the source bot database. PDFs only from configured documents dir.
"""
from __future__ import annotations
import os
import pwd
import shutil
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

SRC=Path('/var/lib/tosbot-ai/tosbot.sqlite3')
DOCS_ROOT=Path('/var/lib/tosbot-ai/documents')
DEST=Path('/var/lib/tosbot-dashboard/import')
TABLES={
 'finance': ('id','owner','kind','amount','category','note','ts','created_at'),
 'reminders': ('id','owner','title','due','state','created_at'),
 'documents': ('id','owner','kind','number','customer','total','created_at'),
}


def sync(source=SRC, destination=DEST, docs_root=DOCS_ROOT, change_owner=True):
    if os.geteuid()!=0 and change_owner:
        raise PermissionError('Jalankan sync via systemd root')
    if not source.exists():
        return {'ok':False,'reason':'Database TosBot belum ditemukan'}
    destination.mkdir(parents=True,exist_ok=True)
    pdf_dest=destination/'pdf';pdf_dest.mkdir(exist_ok=True)
    if change_owner:
        uid=pwd.getpwnam('tosbot-dashboard').pw_uid
        gid=pwd.getpwnam('tosbot-dashboard').pw_gid
        for p in (destination,pdf_dest):os.chown(p,uid,gid);os.chmod(p,0o700)
    else:uid=gid=os.geteuid()
    fd,name=tempfile.mkstemp(prefix='.snapshot-',suffix='.sqlite3',dir=destination)
    os.close(fd)
    temp=Path(name)
    processed={}
    try:
        source_con=sqlite3.connect(f'file:{source}?mode=ro',uri=True,timeout=10)
        source_con.row_factory=sqlite3.Row
        output=sqlite3.connect(temp)
        source_con.execute('BEGIN')
        try:
            for table,fields in TABLES.items():
                # No dynamic user input in table/column names.
                cols=', '.join(fields)
                spec=', '.join(f'"{c}" '+('INTEGER' if c in ('id','owner','amount','total','ts','created_at','due') else 'TEXT') for c in fields)
                output.execute(f'CREATE TABLE {table} ({spec})')
                rows=source_con.execute(f'SELECT {cols} FROM {table}').fetchall()
                output.executemany(f'INSERT INTO {table} ({cols}) VALUES ({",".join("?" for _ in fields)})',
                    ([r[c] for c in fields] for r in rows))
                processed[table]=len(rows)
            for row in source_con.execute('SELECT id,path FROM documents'):
                path=Path(row['path'])
                try:
                    candidate=path.resolve(strict=True)
                    root=docs_root.resolve(strict=True)
                    if candidate.parent!=root or candidate.suffix.lower()!='.pdf' or not candidate.is_file():continue
                    if candidate.stat().st_size>25*1024*1024:continue
                    target=pdf_dest/f'bot-{int(row["id"])}.pdf'
                    # Copy through a temporary file and atomic rename.
                    fd_pdf,tmp_pdf=tempfile.mkstemp(dir=pdf_dest,prefix='.pdf-')
                    try:
                        with os.fdopen(fd_pdf,'wb') as out:
                            source_fd=os.open(candidate,os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
                            with os.fdopen(source_fd,'rb') as inp:
                                if not stat.S_ISREG(os.fstat(inp.fileno()).st_mode):
                                    raise OSError('PDF source bukan file biasa')
                                shutil.copyfileobj(inp,out)
                        os.chown(tmp_pdf,uid,gid);os.chmod(tmp_pdf,0o600)
                        os.replace(tmp_pdf,target)
                    finally:
                        if os.path.exists(tmp_pdf):os.unlink(tmp_pdf)
                except (OSError,ValueError,TypeError):continue
            source_con.commit()
        finally:
            source_con.close()
            output.commit();output.close()
        os.chown(temp,uid,gid);os.chmod(temp,0o600)
        os.replace(temp,destination/'tosbot_snapshot.sqlite3')
        return {'ok':True,'counts':processed}
    finally:
        temp.unlink(missing_ok=True)


if __name__=='__main__':
    result=sync()
    print(result)
    sys.exit(0 if result['ok'] or result.get('reason') else 1)
