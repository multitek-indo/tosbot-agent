from __future__ import annotations
import importlib
import os
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv('DASHBOARD_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('DASHBOARD_COOKIE_SECURE','false')
    from app import storage as st
    st.DATA_DIR=tmp_path
    st.initialize()
    st.set_password('admin','test-password-long-001')
    from app.main import app
    client=TestClient(app)
    return client


def login(client):
    res=client.post('/api/login',json={'username':'admin','password':'test-password-long-001'})
    assert res.status_code==200, res.text
    me=client.get('/api/me')
    assert me.status_code==200
    return {'X-CSRF-Token':me.json()['csrf'],'Content-Type':'application/json'}


def test_auth_and_crud(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch)
    assert c.get('/api/customers').status_code==401
    assert c.post('/api/login',json={'username':'admin','password':'wrong'}).status_code==401
    h=login(c)
    assert c.post('/api/customers',json={'name':'PT Contoh'}).status_code==403
    res=c.post('/api/customers',json={'name':'PT SAMKYUNG','pic':'Bu Nurul','phone':'0812'},headers=h)
    assert res.status_code==200,res.text
    cid=res.json()['id']
    assert c.get('/api/customers').json()[0]['pic']=='Bu Nurul'
    r=c.post('/api/jobs',json={'customer_id':cid,'machine':'Juki LK-1900A','problem':'Power PCB','estimate':1500000},headers=h)
    assert r.status_code==200,r.text
    jid=r.json()['id']
    assert c.patch(f'/api/jobs/{jid}/status',json={'status':'selesai'},headers=h).status_code==200
    assert c.patch(f'/api/jobs/{jid}/status',json={'status':'not_status'},headers=h).status_code==422
    assert c.get('/api/overview').json()['completed_jobs']==1
    assert c.post('/api/finance',json={'kind':'expense','amount':250000,'category':'Sparepart','note':'PCB'},headers=h).status_code==200
    assert c.get('/api/finance').json()[0]['source']=='dashboard'
    assert c.get('/api/server').status_code==200
    assert c.post('/api/logout',json={},headers=h).status_code==200
    assert c.get('/api/customers').status_code==401


def test_document_pdf_and_import(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch);h=login(c)
    from app import main
    monkeypatch.setattr(main,'company_config',lambda:good_company(tmp_path))
    invoice={'kind':'invoice','customer':'PT ABC','attention':'Bu Tari','items':[{'name':'Service PCB','qty':2,'price':450000,'unit':'UNIT','note':'Sparepart tidak termasuk'}]}
    r=c.post('/api/documents',json=invoice,headers=h)
    assert r.status_code==200,r.text
    assert r.json()['total']==900000
    pdf=c.get(r.json()['download'])
    assert pdf.status_code==200 and pdf.content[:4]==b'%PDF'
    bad=c.post('/api/documents',json={**invoice,'discount':1000000},headers=h)
    assert bad.status_code==400
    # Fake imported sanitized snapshot from bot, without exposing KV/audit/tokens.
    d=tmp_path/'import';d.mkdir()
    con=sqlite3.connect(d/'tosbot_snapshot.sqlite3')
    con.execute('CREATE TABLE documents(id INTEGER,owner INTEGER,kind TEXT,number TEXT,customer TEXT,total INTEGER,created_at INTEGER)')
    con.execute('CREATE TABLE finance(id INTEGER,owner INTEGER,kind TEXT,amount INTEGER,category TEXT,note TEXT,ts INTEGER,created_at INTEGER)')
    con.execute('CREATE TABLE reminders(id INTEGER,owner INTEGER,title TEXT,due INTEGER,state TEXT,created_at INTEGER)')
    con.execute("INSERT INTO documents VALUES(1,2,'offer','PEN/2026/0001','PT Sumbiri',1300000,2000000000)")
    con.execute("INSERT INTO finance VALUES(1,2,'income',100000,'Service','Penerimaan',2000000000,2000000000)")
    con.commit();con.close()
    docs=c.get('/api/documents').json()
    assert any(x['source']=='telegram' for x in docs)
    assert all('path' not in x for x in docs)
    assert c.get('/api/reminders').status_code==200


def test_page_and_headers(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch)
    r=c.get('/')
    assert r.status_code==200 and 'Selamat datang kembali' in r.text
    assert r.headers['X-Frame-Options']=='DENY'
    assert 'script-src' in r.headers['Content-Security-Policy']
    assert c.get('/healthz').json()['status']=='ok'
    h=login(c)
    assert 'MULTITEK' in c.get('/').text


def test_sync_sanitized(tmp_path,monkeypatch):
    from scripts.sync_tosbot import sync
    bot=tmp_path/'live.sqlite3';dst=tmp_path/'sanitized';docs=tmp_path/'documents';docs.mkdir()
    pdf=docs/'sampel.pdf';pdf.write_bytes(b'%PDF sample')
    conn=sqlite3.connect(bot)
    conn.execute('CREATE TABLE kv(k TEXT,v TEXT)')
    conn.execute("INSERT INTO kv VALUES('telegram_secret','TOP_SECRET')")
    conn.execute('CREATE TABLE finance(id INTEGER,owner INTEGER,kind TEXT,amount INTEGER,category TEXT,note TEXT,ts INTEGER,created_at INTEGER)')
    conn.execute('CREATE TABLE reminders(id INTEGER,owner INTEGER,title TEXT,due INTEGER,state TEXT,created_at INTEGER)')
    conn.execute('CREATE TABLE documents(id INTEGER,owner INTEGER,kind TEXT,number TEXT,customer TEXT,path TEXT,total INTEGER,created_at INTEGER)')
    conn.execute('INSERT INTO documents VALUES(1,1,\'invoice\',\'I/001\',\'PT ABC\',?,1000,123)',(str(pdf),))
    conn.commit();conn.close()
    res=sync(bot,dst,docs,change_owner=False)
    assert res['ok'] is True
    copy=sqlite3.connect(dst/'tosbot_snapshot.sqlite3')
    tables=[x[0] for x in copy.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert 'kv' not in tables
    assert copy.execute('SELECT customer FROM documents').fetchone()[0]=='PT ABC'
    assert (dst/'pdf'/'bot-1.pdf').read_bytes()==b'%PDF sample'
    copy.close()


def test_offer_uses_real_renderer_with_provided_signature(tmp_path,monkeypatch):
    from PIL import Image
    from types import SimpleNamespace
    c=make_client(tmp_path,monkeypatch)
    h=login(c)
    fake_sign=tmp_path/'fixture-sign.png'
    fake_logo=tmp_path/'fixture-logo.png'
    Image.new('RGBA',(240,60),(245,245,245,255)).save(fake_sign)
    Image.new('RGBA',(120,120),(245,245,245,255)).save(fake_logo)
    from app import main
    cfg=SimpleNamespace(name='PT CONTOH',address='Workshop simulasi',phone='0800',email='demo@example.invalid',
        bank='BANK',account='000',account_name='PT CONTOH',signer='Penanda tangan contoh',city='Salatiga',
        logo_path=fake_logo,offer_signature_path=fake_sign)
    monkeypatch.setattr(main,'company_config',lambda:cfg)
    offer={'kind':'offer','customer':'PT Contoh Dua','attention':'Ibu Test','items':[{'name':'Perbaikan mesin JUKI','qty':1,'unit':'UNIT','price':850000,'note':'Biaya belum termasuk sparepart'}],
           'terms':'Garansi 1 bulan, setelah berhasil diperbaiki'}
    result=c.post('/api/documents',json=offer,headers=h)
    assert result.status_code==200,result.text
    assert result.json()['number'].startswith('WEB-PEN/')
    pdf=c.get(result.json()['download'])
    assert pdf.status_code==200 and len(pdf.content)>4000


def good_company(tmp_path):
    from PIL import Image
    from types import SimpleNamespace
    sign=tmp_path/'test-sign.png'
    logo=tmp_path/'test-logo.png'
    if not sign.exists():Image.new('RGBA',(240,60),(245,245,245,255)).save(sign)
    if not logo.exists():Image.new('RGBA',(120,120),(245,245,245,255)).save(logo)
    return SimpleNamespace(name='PT CONTOH',address='Workshop Salatiga',phone='0800',email='admin@example.invalid',
        bank='BANK',account='000',account_name='PT CONTOH',signer='Tanda tangan contoh',city='Salatiga',
        logo_path=logo,offer_signature_path=sign)

def test_pdf_requires_complete_company_metadata(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch);h=login(c)
    invoice={'kind':'invoice','customer':'PT ABC','items':[{'name':'Service mesin','qty':1,'price':450000}]}
    result=c.post('/api/documents',json=invoice,headers=h)
    assert result.status_code==409
    assert 'Profil dokumen belum lengkap' in result.json()['detail']
    cfg=c.get('/api/document-settings').json()
    assert not cfg['invoice_ready']
