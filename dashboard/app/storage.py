from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get('DASHBOARD_DATA_DIR', '/var/lib/tosbot-dashboard'))


def connect(path=None, read_only=False):
    p = Path(path or (DATA_DIR / 'dashboard.sqlite3'))
    if read_only:
        if not p.is_file():
            return None
        con = sqlite3.connect(f'file:{p}?mode=ro', uri=True, timeout=5)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(p, timeout=10)
        con.execute('PRAGMA journal_mode=WAL')
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=5000')
    return con


@contextmanager
def db():
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def initialize():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admin (
          name TEXT PRIMARY KEY, salt TEXT NOT NULL, passhash TEXT NOT NULL,
          updated INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          sid_hash TEXT PRIMARY KEY, name TEXT NOT NULL,
          csrf TEXT NOT NULL, expires INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS customers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL, pic TEXT NOT NULL DEFAULT '',
          phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
          address TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
          archived INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL,
          machine TEXT NOT NULL, problem TEXT NOT NULL DEFAULT '',
          technician TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'baru',
          scheduled_date TEXT NOT NULL DEFAULT '',
          estimate INTEGER NOT NULL DEFAULT 0,
          notes TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          FOREIGN KEY(customer_id) REFERENCES customers(id)
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE TABLE IF NOT EXISTS job_photos (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id INTEGER NOT NULL,
          filename TEXT NOT NULL UNIQUE,
          caption TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL,
          FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_job_photos_job ON job_photos(job_id);
        CREATE TABLE IF NOT EXISTS finances (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL, amount INTEGER NOT NULL,
          category TEXT NOT NULL, note TEXT NOT NULL,
          ts INTEGER NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS web_documents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL, number TEXT NOT NULL UNIQUE,
          customer TEXT NOT NULL, attention TEXT NOT NULL DEFAULT '',
          total INTEGER NOT NULL, items_json TEXT NOT NULL,
          filename TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL,
          action TEXT NOT NULL, object_id TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL
        );
        ''')


def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()


def set_password(name, password):
    if not (10 <= len(password) <= 256) or not password.strip():
        raise ValueError('Password minimal 10 karakter (maksimal 256)')
    salt = secrets.token_hex(16)
    now = int(time.time())
    with db() as con:
        con.execute('INSERT INTO admin(name,salt,passhash,updated) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET salt=excluded.salt, passhash=excluded.passhash, updated=excluded.updated',
                    (name, salt, password_hash(password,salt), now))
        con.execute('DELETE FROM sessions WHERE name=?', (name,))


def validate_password(name, password):
    with db() as con:
        row = con.execute('SELECT salt,passhash FROM admin WHERE name=?',(name,)).fetchone()
        if not row:
            # Equal-cost dummy computation so unknown-user probes still cost work.
            password_hash(password, '0'*32)
            return False
        return hmac.compare_digest(password_hash(password, row['salt']), row['passhash'])


def new_session(name):
    token, csrf = secrets.token_urlsafe(36), secrets.token_urlsafe(30)
    expires = int(time.time()) + 8*3600
    with db() as con:
        con.execute('DELETE FROM sessions WHERE expires<?',(int(time.time()),))
        con.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),name,csrf,expires))
    return token


def session_for(token):
    if not token or len(token) > 512:
        return None
    with db() as con:
        row = con.execute('SELECT name,csrf,expires FROM sessions WHERE sid_hash=?',
                          (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    return dict(row) if row and int(row['expires'])>time.time() else None


def logout(token):
    if token:
        with db() as con:
            con.execute('DELETE FROM sessions WHERE sid_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))


def event(con, action, object_id='', actor='admin'):
    con.execute('INSERT INTO events(actor,action,object_id,created_at) VALUES(?,?,?,?)',
                (actor,action,str(object_id)[:70],int(time.time())))


def imported():
    return connect(DATA_DIR/'import'/'tosbot_snapshot.sqlite3',read_only=True)


def get_setting(key, default=''):
    with db() as con:
        row=con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row is not None else default

def put_setting(key, value, actor):
    with db() as con:
        con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        event(con,'setting_changed',key,actor)

def user_rows():
    with db() as con:
        return [dict(row) for row in con.execute('SELECT name, updated FROM admin ORDER BY name COLLATE NOCASE')]

def create_user(name, password, actor):
    if not (10 <= len(password) <= 256) or not password.strip():
        raise ValueError('Password minimal 10 karakter (maksimal 256)')
    salt=secrets.token_hex(16)
    with db() as con:
        cur=con.execute('INSERT OR IGNORE INTO admin(name,salt,passhash,updated) VALUES(?,?,?,?)',
                        (name,salt,password_hash(password,salt),int(time.time())))
        if not cur.rowcount:
            return False
        event(con,'user_created',name,actor)
    return True

def delete_user(name, actor):
    with db() as con:
        if con.execute('SELECT COUNT(*) n FROM admin').fetchone()['n']<=1:
            return False
        cur=con.execute('DELETE FROM admin WHERE name=?',(name,))
        if cur.rowcount:
            con.execute('DELETE FROM sessions WHERE name=?',(name,))
            event(con,'user_deleted',name,actor)
        return bool(cur.rowcount)
