from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path

class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db=sqlite3.connect(str(path), timeout=20)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA busy_timeout=20000')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS drafts (owner INTEGER PRIMARY KEY, payload TEXT NOT NULL, updated_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS finance (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER NOT NULL, kind TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK(amount>0), category TEXT NOT NULL, note TEXT NOT NULL,
            ts INTEGER NOT NULL, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_finance_owner_ts ON finance(owner, ts);
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER NOT NULL, title TEXT NOT NULL,
            due INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_reminders_state_due ON reminders(state,due);
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner INTEGER NOT NULL, kind TEXT NOT NULL,
            number TEXT NOT NULL UNIQUE, customer TEXT NOT NULL,
            path TEXT NOT NULL, total INTEGER NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, actor INTEGER NOT NULL, action TEXT NOT NULL,
            detail TEXT NOT NULL, ts INTEGER NOT NULL);
        ''')
        self.db.commit()

    def get_kv(self,k,default=None):
        row=self.db.execute('SELECT v FROM kv WHERE k=?',(k,)).fetchone()
        return json.loads(row['v']) if row else default

    def set_kv(self,k,value):
        with self.db:
            self.db.execute('INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v',
                            (k,json.dumps(value,ensure_ascii=False)))

    def get_draft(self,owner):
        row=self.db.execute('SELECT payload FROM drafts WHERE owner=?',(owner,)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_draft(self,owner,payload):
        with self.db:
            self.db.execute('INSERT INTO drafts VALUES(?,?,?) ON CONFLICT(owner) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at',
                            (owner,json.dumps(payload,ensure_ascii=False),int(time.time())))

    def delete_draft(self,owner):
        with self.db: self.db.execute('DELETE FROM drafts WHERE owner=?',(owner,))

    def add_finance(self,owner,kind,amount,category,note,ts):
        with self.db:
            cur=self.db.execute('INSERT INTO finance(owner,kind,amount,category,note,ts,created_at) VALUES(?,?,?,?,?,?,?)',
                                (owner,kind,amount,category,note,ts,int(time.time())))
            return cur.lastrowid

    def finance_report(self,owner,begin,end):
        rows=self.db.execute('SELECT kind,COALESCE(SUM(amount),0) total,COUNT(*) n FROM finance WHERE owner=? AND ts>=? AND ts<? GROUP BY kind',
                             (owner,begin,end)).fetchall()
        return {r['kind']:(r['total'],r['n']) for r in rows}

    def add_reminder(self,owner,title,due):
        with self.db:
            cur=self.db.execute('INSERT INTO reminders(owner,title,due,created_at) VALUES(?,?,?,?)',
                                (owner,title,due,int(time.time())))
            return cur.lastrowid

    def list_reminders(self,owner):
        return self.db.execute('SELECT * FROM reminders WHERE owner=? AND state=? ORDER BY due LIMIT 15',
                               (owner,'pending')).fetchall()

    def due_reminders(self):
        return self.db.execute('SELECT * FROM reminders WHERE state=? AND due<=? ORDER BY due LIMIT 30',
                               ('pending',int(time.time()))).fetchall()

    def mark_sent(self,id):
        with self.db: self.db.execute('UPDATE reminders SET state=? WHERE id=?',('sent',id))

    def reserve_number(self,owner,kind,customer,path,total,number):
        with self.db:
            self.db.execute('INSERT INTO documents(owner,kind,number,customer,path,total,created_at) VALUES(?,?,?,?,?,?,?)',
                            (owner,kind,number,customer,str(path),total,int(time.time())))

    def next_number(self,kind,year):
        prefix='INV' if kind=='invoice' else 'PEN'
        pattern=f'{prefix}/{year}/%'
        row=self.db.execute('SELECT COUNT(*) n FROM documents WHERE number LIKE ?',(pattern,)).fetchone()
        # Prevent collision with deleted/corrupted sequence; select max serial.
        rows=self.db.execute('SELECT number FROM documents WHERE number LIKE ?',(pattern,)).fetchall()
        seq=max([int(r['number'].split('/')[-1]) for r in rows if r['number'].split('/')[-1].isdigit()] or [0])+1
        return f'{prefix}/{year}/{seq:04d}'

    def audit(self,owner,action,detail=''):
        with self.db:
            self.db.execute('INSERT INTO audit(actor,action,detail,ts) VALUES(?,?,?,?)',
                            (owner,action,str(detail)[:300],int(time.time())))
