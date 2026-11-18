import base64
import io
import os
import sys
from pathlib import Path

from PIL import Image

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE/"tests"))
from test_app import make_client,login


def photo_data():
    image=Image.new('RGB',(150,100),(30,100,190))
    buf=io.BytesIO();image.save(buf,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode('ascii')


def test_photo_crud_and_bridge_live_consistency(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch)
    h=login(c)
    customer=c.post('/api/customers',json={'name':'PT ANUGERAH ALFA LESTARI','pic':'Mas Fahrul'},headers=h).json()['id']
    job=c.post('/api/jobs',json={'customer_id':customer,'machine':'JUKI JK-1900','problem':'error 685', 'technician':'Imam'},headers=h).json()['id']
    assert c.get('/api/jobs').json()[0]['photo_count']==0
    # No auth or CSRF must be rejected.
    assert c.post(f'/api/jobs/{job}/photos',json={'image_base64':photo_data()}).status_code==403
    r=c.post(f'/api/jobs/{job}/photos',headers=h,json={'image_base64':photo_data(),'caption':'PCB sebelum perbaikan'})
    assert r.status_code==200,r.text
    pid=r.json()['id']
    assert c.get('/api/jobs').json()[0]['photo_count']==1
    meta=c.get(f'/api/jobs/{job}/photos').json()
    assert len(meta)==1 and meta[0]['caption']=='PCB sebelum perbaikan'
    raw=c.get(f'/api/jobs/photos/{pid}')
    assert raw.status_code==200 and raw.content[:3]==b'\xff\xd8\xff'
    assert raw.headers['Content-Type'].startswith('image/jpeg')
    assert c.get('/api/bridge/summary').status_code==503
    monkeypatch.setenv('DASHBOARD_BRIDGE_TOKEN','x'*48)
    assert c.get('/api/bridge/summary').status_code==401
    secret={'X-Tosbot-Bridge-Key':'x'*48}
    assert c.get('/api/bridge/summary',headers=secret).json()['customers']==c.get('/api/overview').json()['customers']==1
    assert c.get('/api/bridge/summary',headers=secret).json()['jobs']==1
    assert c.get('/api/bridge/customers',headers=secret).json()['results'][0]['name']=='PT ANUGERAH ALFA LESTARI'
    assert c.get('/api/bridge/jobs',headers=secret).json()['results'][0]['photo_count']==1
    assert c.get(f'/api/bridge/photos?job_id={job}',headers=secret).json()['photos'][0]['id']==pid
    assert c.get(f'/api/bridge/photos/{pid}',headers=secret).content==raw.content
    assert c.get(f'/api/bridge/photos/{pid}').status_code==401
    assert c.post(f'/api/jobs/{job}/photos',headers=h,json={'image_base64':'garbage'}).status_code==422
    assert c.request('DELETE',f'/api/jobs/photos/{pid}',headers=h,json={}).status_code==200
    assert c.get(f'/api/jobs/photos/{pid}').status_code==404
    assert c.get(f'/api/bridge/photos/{pid}',headers=secret).status_code==404


def test_upload_rejects_wrong_type_and_no_accidental_pdf_logo_change(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch);h=login(c)
    cid=c.post('/api/customers',json={'name':'PT CONTOH'},headers=h).json()['id']
    jid=c.post('/api/jobs',json={'customer_id':cid,'machine':'JUKI DDL'},headers=h).json()['id']
    bad=base64.b64encode(b'%PDF fake payload').decode()
    assert c.post(f'/api/jobs/{jid}/photos',headers=h,json={'image_base64':bad}).status_code==400
    assert c.post('/api/jobs/99999/photos',headers=h,json={'image_base64':photo_data()}).status_code==404
    assert c.get('/api/settings/branding').status_code in (200,404)  # Settings endpoint remains available.


def test_finance_bridge_same_as_dashboard(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch);h=login(c)
    assert c.post('/api/finance',json={'kind':'expense','amount':200000,'category':'Ongkos','note':'Transport'},headers=h).status_code==200
    monkeypatch.setenv('DASHBOARD_BRIDGE_TOKEN','y'*48)
    secret={'X-Tosbot-Bridge-Key':'y'*48}
    web=c.get('/api/finance').json()
    bridge=c.get('/api/bridge/finance',headers=secret).json()
    assert bridge['expense']==sum(x['amount'] for x in web if x['kind']=='expense')
    assert bridge['difference']==-200000
