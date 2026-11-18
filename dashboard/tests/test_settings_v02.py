from __future__ import annotations
import base64
import io
from PIL import Image

from test_app import make_client, login
from app import storage as st


def photo_data(format='PNG'):
    image=Image.new('RGB',(170,80),'#42a5ef')
    buf=io.BytesIO();image.save(buf,format=format)
    media='jpeg' if format=='JPEG' else 'png'
    return f'data:image/{media};base64,'+base64.b64encode(buf.getvalue()).decode('ascii')


def test_branding_upload_and_pdf_profile(tmp_path, monkeypatch):
    original_logo=tmp_path/'official-pdf-logo.png'
    Image.new('RGB',(180,90),(192,20,40)).save(original_logo)
    original_logo_bytes=original_logo.read_bytes()
    monkeypatch.setenv('COMPANY_LOGO_PATH',str(original_logo))
    c=make_client(tmp_path,monkeypatch);h=login(c)
    assert c.get('/api/branding').json()['has_logo'] is False
    assert c.put('/api/settings/company',json={'name':'PT MULTITEK UJI'},headers={}).status_code==403
    r=c.put('/api/settings/company',json={'name':'PT MULTITEK UJI'},headers=h)
    assert r.status_code==200,r.text
    r=c.post('/api/settings/company/logo',json={'image':photo_data()},headers=h)
    assert r.status_code==200,r.text
    info=c.get('/api/branding').json()
    assert info['company_name']=='PT MULTITEK UJI' and info['has_logo']
    logo=c.get('/api/branding/logo');assert logo.status_code==200
    assert logo.headers['content-type']=='image/png'
    from app.main import company_config
    assert company_config().name=='PT MULTITEK UJI'
    assert company_config().logo_path==original_logo
    assert company_config().logo_path.read_bytes()==original_logo_bytes
    dashboard_logo=st.DATA_DIR/'branding'/'dashboard-logo.png'
    assert dashboard_logo.is_file()
    assert dashboard_logo.read_bytes()[:8]==b'\x89PNG\r\n\x1a\n'
    assert dashboard_logo!=company_config().logo_path
    assert c.post('/api/settings/company/logo',json={'image':'data:image/svg+xml;base64,AAA='},headers=h).status_code in (400,422)
    assert c.put('/api/settings/company',json={'name':'   '},headers=h).status_code==400
    # Idempotent schema initialization must preserve brand settings and the logo.
    st.initialize()
    assert c.get('/api/branding').json()['company_name']=='PT MULTITEK UJI'


def test_multi_admin_and_password_policy(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch);h=login(c)
    bad={'username':'staf01','password':'short999','current_password':'test-password-long-001'}
    assert c.post('/api/settings/users',json=bad,headers=h).status_code==422
    payload={**bad,'password':'sepuluh123'}
    assert c.post('/api/settings/users',json=payload,headers=h).status_code==200
    assert c.post('/api/settings/users',json=payload,headers=h).status_code==409
    assert c.post('/api/settings/users',json={**payload,'username':'other01','current_password':'wrong'},headers=h).status_code==403
    users=c.get('/api/settings/users').json()['users']
    assert sorted(u['name'] for u in users)==['admin','staf01']
    from fastapi.testclient import TestClient
    from app.main import app
    staff=TestClient(app)
    assert staff.post('/api/login',json={'username':'staf01','password':'sepuluh123'}).status_code==200
    me=staff.get('/api/me').json();hh={'X-CSRF-Token':me['csrf'],'Content-Type':'application/json'}
    assert staff.post('/api/customers',json={'name':'PT Staf Bisa'},headers=hh).status_code==200
    assert c.post('/api/settings/users/staf01/delete',json={'current_password':'wrong'},headers=h).status_code==403
    assert c.post('/api/settings/users/staf01/delete',json={'current_password':'test-password-long-001'},headers=h).status_code==200
    assert staff.get('/api/me').status_code==401
    assert staff.post('/api/login',json={'username':'staf01','password':'sepuluh123'}).status_code==401
    assert c.get('/api/settings/users').json()['users'][0]['name']=='admin'


def test_change_password_10_char_and_reauth(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch);h=login(c)
    assert c.post('/api/settings/password',json={'current_password':'wrong','new_password':'sepuluh123'},headers=h).status_code==403
    assert c.post('/api/settings/password',json={'current_password':'test-password-long-001','new_password':'123456789'},headers=h).status_code==422
    r=c.post('/api/settings/password',json={'current_password':'test-password-long-001','new_password':'sepuluh123'},headers=h)
    assert r.status_code==200,r.text
    assert c.get('/api/me').status_code==401
    assert c.post('/api/login',json={'username':'admin','password':'test-password-long-001'}).status_code==401
    assert c.post('/api/login',json={'username':'admin','password':'sepuluh123'}).status_code==200
    assert st.validate_password('admin','sepuluh123')
    assert not st.validate_password('admin','test-password-long-001')


def test_reset_user_password(tmp_path,monkeypatch):
    c=make_client(tmp_path,monkeypatch);h=login(c)
    p={'username':'staf02','password':'sepuluh123','current_password':'test-password-long-001'}
    assert c.post('/api/settings/users',json=p,headers=h).status_code==200
    reset={'current_password':'test-password-long-001','new_password':'password-baru10'}
    assert c.post('/api/settings/users/staf02/password',json=reset,headers=h).status_code==200
    assert st.validate_password('staf02','password-baru10')
    assert not st.validate_password('staf02','sepuluh123')
    # No role restrictions: new users are allowed on every dashboard API.
    assert c.get('/api/settings/users').status_code==200


def test_uploaded_dashboard_logo_never_replaces_generated_pdf_logo(tmp_path, monkeypatch):
    """Real renderer receives the configured original PNG, not UI branding PNG."""
    official_logo=tmp_path/'official-document-logo.png'
    Image.new('RGB',(180,100),(240,22,40)).save(official_logo)
    original_logo=official_logo.read_bytes()
    signature=tmp_path/'offer-signature.png'
    Image.new('RGB',(180,80),(250,250,250)).save(signature)
    vals={'COMPANY_LOGO_PATH':str(official_logo), 'COMPANY_SIGNATURE_PATH':str(signature),
      'COMPANY_NAME':'PT IMA MULTITEK INDONESIA','COMPANY_ADDRESS':'Salatiga',
      'COMPANY_PHONE':'0271-111111','COMPANY_EMAIL':'billing@example.invalid',
      'COMPANY_BANK':'BANK UJI','COMPANY_ACCOUNT':'111111',
      'COMPANY_ACCOUNT_NAME':'PT IMA MULTITEK INDONESIA','COMPANY_SIGNER':'Direktur'}
    for k,v in vals.items():monkeypatch.setenv(k,v)
    c=make_client(tmp_path,monkeypatch);h=login(c)
    assert c.post('/api/settings/company/logo',json={'image':photo_data()},headers=h).status_code==200
    from app import main
    real_make_pdf=main.make_pdf
    observed=[]
    def capture(*args):
        cfg=args[3]
        observed.append(cfg.logo_path)
        assert cfg.logo_path==official_logo
        assert cfg.logo_path.read_bytes()==original_logo
        return real_make_pdf(*args)
    monkeypatch.setattr(main,'make_pdf',capture)
    payload={'kind':'invoice','customer':'PT Contoh','items':[{'name':'Service PCB Juki','qty':1,'price':450000}]}
    res=c.post('/api/documents',json=payload,headers=h)
    assert res.status_code==200,res.text
    pdf=c.get(res.json()['download'])
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    assert observed==[official_logo]
    assert official_logo.read_bytes()==original_logo
    assert (tmp_path/'branding'/'dashboard-logo.png').is_file()
