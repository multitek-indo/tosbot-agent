from __future__ import annotations
import base64
import binascii
import hashlib
import io
import warnings
import hmac
import json
import os
import tempfile
import re
import secrets
import subprocess
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import psutil
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from PIL import Image, UnidentifiedImageError, ImageOps

from . import storage as st
from vendor.tosbot_documents import make_pdf, valid_item, total

BASE = Path(__file__).resolve().parent
STATIC = BASE / 'static'
TIMEZONE = ZoneInfo('Asia/Jakarta')
@asynccontextmanager
async def lifespan(app):
    st.initialize()
    yield

app = FastAPI(title='TosBot Dashboard', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount('/static', StaticFiles(directory=str(STATIC)), name='static')
ATTEMPTS = defaultdict(deque)


@app.middleware('http')
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; connect-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'private, no-store'
    return response


def require_session(request: Request):
    session = st.session_for(request.cookies.get('tosbot_session'))
    if not session:
        raise HTTPException(401, 'Silakan masuk kembali')
    return session


def csrf(request: Request, session=Depends(require_session)):
    posted = request.headers.get('X-CSRF-Token', '')
    if not posted or not hmac.compare_digest(posted, session['csrf']):
        raise HTTPException(403, 'Token keamanan tidak cocok')
    if request.headers.get('content-type','').split(';')[0] != 'application/json':
        raise HTTPException(415, 'Gunakan Content-Type application/json')
    return session


class Login(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=256)


class Customer(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    pic: str = Field(default='', max_length=120)
    phone: str = Field(default='', max_length=60)
    email: str = Field(default='', max_length=160)
    address: str = Field(default='', max_length=500)
    note: str = Field(default='', max_length=1000)


STATUSES = ('baru', 'dijadwalkan', 'proses', 'menunggu_sparepart', 'selesai', 'dibatalkan')
class Job(BaseModel):
    customer_id: int = Field(gt=0)
    machine: str = Field(min_length=2, max_length=220)
    problem: str = Field(default='', max_length=1000)
    technician: str = Field(default='', max_length=120)
    status: str = 'baru'
    scheduled_date: str = Field(default='', max_length=30)
    estimate: int = Field(default=0, ge=0, le=10**13)
    notes: str = Field(default='', max_length=1500)
    @field_validator('status')
    @classmethod
    def known_status(cls, v):
        if v not in STATUSES: raise ValueError('status tidak dikenal')
        return v


class JobUpdate(BaseModel):
    status: str
    @field_validator('status')
    @classmethod
    def known_status(cls, v):
        if v not in STATUSES: raise ValueError('status tidak dikenal')
        return v


class Money(BaseModel):
    kind: str
    amount: int = Field(gt=0, le=10**13)
    category: str = Field(min_length=2, max_length=100)
    note: str = Field(default='', max_length=500)
    @field_validator('kind')
    @classmethod
    def valid_kind(cls, v):
        if v not in ('income','expense'): raise ValueError('hanya income/expense')
        return v


class DocumentItem(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    qty: int = Field(ge=1, le=100000)
    unit: str = Field(default='UNIT', max_length=12)
    price: int = Field(ge=0, le=10**12)
    note: str = Field(default='', max_length=400)

class DocumentCreate(BaseModel):
    kind: str
    customer: str = Field(min_length=2, max_length=160)
    attention: str = Field(default='', max_length=120)
    terms: str = Field(default='', max_length=1600)
    payment_type: str = Field(default='Transfer', max_length=60)
    po_number: str = Field(default='', max_length=80)
    discount: int = Field(default=0, ge=0, le=10**13)
    items: list[DocumentItem] = Field(min_length=1, max_length=30)
    @field_validator('kind')
    @classmethod
    def valid_kind(cls,v):
        if v not in ('invoice','offer'): raise ValueError('jenis dokumen tidak dikenal')
        return v


@app.get('/healthz')
def health():
    return {'status':'ok','app':'tosbot-dashboard','version':'0.3.0'}


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    if st.session_for(request.cookies.get('tosbot_session')):
        return (STATIC/'index.html').read_text(encoding='utf8')
    return (STATIC/'login.html').read_text(encoding='utf8')


@app.post('/api/login')
def login(data:Login, request:Request, response:Response):
    # Do not trust X-Forwarded-For from the public internet; only socket peer.
    username=data.username.strip().lower()
    key = (str(request.client.host if request.client else 'unknown'),username)
    q=ATTEMPTS[key];now=time.monotonic()
    while q and now-q[0]>900: q.popleft()
    if len(q)>=8:
        raise HTTPException(429,'Terlalu banyak percobaan masuk. Coba 15 menit lagi.')
    if not st.validate_password(username,data.password):
        q.append(now)
        raise HTTPException(401,'Nama pengguna atau password salah')
    q.clear()
    sid=st.new_session(username)
    response.set_cookie('tosbot_session',sid,httponly=True,secure=os.environ.get('DASHBOARD_COOKIE_SECURE','true').lower()=='true',samesite='strict',max_age=8*3600,path='/')
    return {'ok':True}


@app.post('/api/logout')
def logout(request:Request, response:Response, session=Depends(csrf)):
    st.logout(request.cookies.get('tosbot_session'))
    response.delete_cookie('tosbot_session',path='/')
    return {'ok':True}


@app.get('/api/me')
def me(session=Depends(require_session)):
    return {'username':session['name'],'csrf':session['csrf'],'app_version':'0.3.0'}


def data_rows(query, args=()):
    with st.db() as con:
        return [dict(r) for r in con.execute(query,args).fetchall()]


def imported_rows(table, limit=100):
    if table not in ('documents','finance','reminders'):
        return []
    con=st.imported()
    if con is None:return []
    try:
        return [dict(r) for r in con.execute(f'SELECT * FROM {table} ORDER BY id DESC LIMIT ?', (limit,))]
    except Exception:
        return []
    finally:
        con.close()


def month_trend():
    now=datetime.now(TIMEZONE)
    base_year,base_month=now.year,now.month
    months=[]
    for delta in range(5,-1,-1):
        y=base_year; m=base_month-delta
        while m<=0:m+=12;y-=1
        months.append((y,m))
    by_month={(y,m): {'month':f'{m:02d}/{str(y)[-2:]}','income':0,'expense':0} for y,m in months}
    sources=[]
    sources+=data_rows('SELECT ts,kind,amount FROM finances')
    sources+=imported_rows('finance',10000)
    for row in sources:
        dt=datetime.fromtimestamp(int(row['ts']),TIMEZONE)
        key=(dt.year,dt.month)
        if key in by_month:
            kind=str(row['kind']).lower()
            # TosBot uses income/expense; keep unknown kinds out of the totals.
            if kind in ('income','expense'):
                by_month[key][kind]+=int(row['amount'])
    return [by_month[k] for k in months]


@app.get('/api/overview')
def overview(session=Depends(require_session)):
    with st.db() as con:
        c=con.execute('SELECT COUNT(*) n FROM customers WHERE archived=0').fetchone()['n']
        j=con.execute("SELECT COUNT(*) n FROM jobs WHERE status NOT IN ('selesai','dibatalkan')").fetchone()['n']
        completed=con.execute("SELECT COUNT(*) n FROM jobs WHERE status='selesai'").fetchone()['n']
        recent=[dict(x) for x in con.execute('SELECT j.*,c.name customer FROM jobs j JOIN customers c ON c.id=j.customer_id ORDER BY j.created_at DESC LIMIT 6')]
        docsum=con.execute('SELECT COALESCE(SUM(total),0) n FROM web_documents WHERE kind=?',('invoice',)).fetchone()['n']
    impdocs=imported_rows('documents',10000)
    docsum+=sum(int(d['total']) for d in impdocs if d['kind']=='invoice')
    trend=month_trend()
    return {'customers':c,'active_jobs':j,'completed_jobs':completed,'invoice_total':docsum,
            'trend':trend,'recent_jobs':recent,'recent_documents':all_documents()[:6],
            'snapshot':snapshot_status()}


def snapshot_status():
    path=st.DATA_DIR/'import'/'tosbot_snapshot.sqlite3'
    if not path.exists():return {'available':False,'age_seconds':None}
    return {'available':True,'age_seconds':max(0,round(time.time()-path.stat().st_mtime))}


@app.get('/api/customers')
def customers(session=Depends(require_session)):
    return data_rows('SELECT * FROM customers WHERE archived=0 ORDER BY name COLLATE NOCASE LIMIT 1000')


@app.post('/api/customers')
def create_customer(data:Customer, session=Depends(csrf)):
    with st.db() as con:
        now=int(time.time())
        cur=con.execute('INSERT INTO customers(name,pic,phone,email,address,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                        (data.name,data.pic,data.phone,data.email,data.address,data.note,now,now))
        st.event(con,'customer_created',cur.lastrowid)
    return {'id':cur.lastrowid}


@app.put('/api/customers/{cid}')
def update_customer(cid:int,data:Customer,session=Depends(csrf)):
    with st.db() as con:
        cur=con.execute('UPDATE customers SET name=?,pic=?,phone=?,email=?,address=?,note=?,updated_at=? WHERE id=? AND archived=0',
                        (data.name,data.pic,data.phone,data.email,data.address,data.note,int(time.time()),cid))
        if not cur.rowcount:raise HTTPException(404,'Pelanggan tidak ditemukan')
        st.event(con,'customer_updated',cid)
    return {'ok':True}


@app.get('/api/jobs')
def jobs(session=Depends(require_session)):
    return data_rows('SELECT j.*,c.name customer,c.pic pic,(SELECT COUNT(*) FROM job_photos p WHERE p.job_id=j.id) photo_count FROM jobs j JOIN customers c ON c.id=j.customer_id ORDER BY j.created_at DESC LIMIT 1000')


@app.post('/api/jobs')
def create_job(data:Job,session=Depends(csrf)):
    with st.db() as con:
        if not con.execute('SELECT 1 FROM customers WHERE id=? AND archived=0',(data.customer_id,)).fetchone():
            raise HTTPException(400,'Pelanggan tidak tersedia')
        now=int(time.time())
        cur=con.execute('INSERT INTO jobs(customer_id,machine,problem,technician,status,scheduled_date,estimate,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (data.customer_id,data.machine,data.problem,data.technician,data.status,data.scheduled_date,data.estimate,data.notes,now,now))
        st.event(con,'job_created',cur.lastrowid)
    return {'id':cur.lastrowid}


@app.patch('/api/jobs/{jid}/status')
def update_job(jid:int,data:JobUpdate,session=Depends(csrf)):
    with st.db() as con:
        cur=con.execute('UPDATE jobs SET status=?,updated_at=? WHERE id=?',(data.status,int(time.time()),jid))
        if not cur.rowcount:raise HTTPException(404,'Pekerjaan tidak ditemukan')
        st.event(con,'job_status',jid)
    return {'ok':True}


@app.get('/api/finance')
def finances(session=Depends(require_session)):
    own=data_rows('SELECT *,? source FROM finances ORDER BY ts DESC LIMIT 500',('dashboard',))
    imported=imported_rows('finance',500)
    for r in imported:r['source']='telegram'
    return sorted(own+imported,key=lambda x:int(x['ts']),reverse=True)[:500]


@app.post('/api/finance')
def add_money(data:Money,session=Depends(csrf)):
    with st.db() as con:
        now=int(time.time())
        cur=con.execute('INSERT INTO finances(kind,amount,category,note,ts,created_at) VALUES(?,?,?,?,?,?)',
                        (data.kind,data.amount,data.category,data.note,now,now))
        st.event(con,'finance_created',cur.lastrowid)
    return {'id':cur.lastrowid}


def all_documents():
    own=data_rows('SELECT id,kind,number,customer,attention,total,filename,created_at FROM web_documents ORDER BY created_at DESC LIMIT 400')
    for r in own:r['source']='dashboard';r['download']=f'/api/documents/web/{r["id"]}/download'
    imported=imported_rows('documents',400)
    for r in imported:
        r['source']='telegram';r.pop('path',None);r['download']=f'/api/documents/bot/{r["id"]}/download'
    return sorted(own+imported,key=lambda x:int(x['created_at']),reverse=True)


@app.get('/api/documents')
def documents(session=Depends(require_session)):
    return all_documents()


def company_config():
    def env(k,d=''):return os.environ.get(k,d)
    return SimpleNamespace(name=st.get_setting('company_name',env('COMPANY_NAME','PT IMA MULTITEK INDONESIA')),
        address=env('COMPANY_ADDRESS',''),phone=env('COMPANY_PHONE',''),email=env('COMPANY_EMAIL',''),
        bank=env('COMPANY_BANK',''),account=env('COMPANY_ACCOUNT',''),
        account_name=env('COMPANY_ACCOUNT_NAME',''),signer=env('COMPANY_SIGNER',''),
        city=env('COMPANY_CITY','Salatiga'),
        logo_path=Path(env('COMPANY_LOGO_PATH','/opt/tosbot-ai/assets/logo.png')),
        offer_signature_path=Path(env('COMPANY_SIGNATURE_PATH','/opt/tosbot-ai/assets/offer-signature.png')))


@app.get('/api/document-settings')
def document_settings(session=Depends(require_session)):
    cfg=company_config()
    fields={'nama perusahaan':cfg.name,'alamat workshop':cfg.address,'telepon':cfg.phone,
            'email':cfg.email,'bank':cfg.bank,'nomor rekening':cfg.account,
            'nama pemilik rekening':cfg.account_name,'penandatangan':cfg.signer}
    missing=[label for label,value in fields.items() if not value or (label=='nama perusahaan' and value=='Perusahaan Anda')]
    if not cfg.logo_path.is_file(): missing.append('logo perusahaan')
    if not cfg.offer_signature_path.is_file(): missing.append('tanda tangan penawaran')
    return {'missing':missing,'company':cfg.name,'invoice_ready':not any(x!='tanda tangan penawaran' for x in missing), 'offer_ready':not missing}


@app.post('/api/documents')
def create_document(data:DocumentCreate,session=Depends(csrf)):
    items=[valid_item(x.model_dump()) for x in data.items]
    if any(i is None for i in items):raise HTTPException(400,'Item tidak valid')
    profile=document_settings(session)
    required_missing=[x for x in profile['missing'] if data.kind=='offer' or x!='tanda tangan penawaran']
    if required_missing:
        raise HTTPException(409,'Profil dokumen belum lengkap: '+', '.join(required_missing)+'. Lengkapi dashboard.env dan aset privat lebih dahulu.')
    raw={'type':data.kind,'customer':data.customer,'attention':data.attention,
         'terms':data.terms,'discount':data.discount,'payment_type':data.payment_type,
         'po_number':data.po_number,'items':items}
    if data.discount>sum(i['qty']*i['price'] for i in items):raise HTTPException(400,'Diskon lebih besar dari subtotal')
    now=datetime.now(TIMEZONE)
    with st.db() as con:
        # Serial reservation is atomic across concurrent dashboard requests.
        con.execute('BEGIN IMMEDIATE')
        # Reserve sequential number in our own namespace, never collide with bot numbers.
        prefix='WEB-INV' if data.kind=='invoice' else 'WEB-PEN'
        seq=con.execute('SELECT COUNT(*) n FROM web_documents WHERE kind=? AND created_at>=?',(data.kind,int(datetime(now.year,1,1,tzinfo=TIMEZONE).timestamp()))).fetchone()['n']+1
        number=f'{prefix}/{now.year}/{seq:04d}'
        filename=f'{data.kind}-{secrets.token_hex(15)}.pdf'
        out=st.DATA_DIR/'pdf'/filename
        out.parent.mkdir(parents=True,exist_ok=True)
        try:
            make_pdf(raw,number,out,company_config(),now)
            os.chmod(out,0o600)
            cur=con.execute('INSERT INTO web_documents(kind,number,customer,attention,total,items_json,filename,created_at) VALUES(?,?,?,?,?,?,?,?)',
                            (data.kind,number,data.customer,data.attention,total(raw),json.dumps(items,ensure_ascii=False),filename,int(time.time())))
            st.event(con,'document_created',cur.lastrowid)
        except FileNotFoundError as exc:
            out.unlink(missing_ok=True)
            raise HTTPException(409,'Aset privat logo/tanda tangan belum lengkap untuk template PDF. Periksa konfigurasi dashboard.') from exc
        except Exception:
            out.unlink(missing_ok=True)
            raise
    return {'id':cur.lastrowid,'number':number,'total':total(raw),'download':f'/api/documents/web/{cur.lastrowid}/download'}


@app.get('/api/documents/{source}/{docid}/download')
def download_document(source:str,docid:int,session=Depends(require_session)):
    if source=='web':
        with st.db() as con:
            row=con.execute('SELECT filename FROM web_documents WHERE id=?',(docid,)).fetchone()
        if not row:raise HTTPException(404,'Dokumen tidak tersedia')
        safe=row['filename']
        if not re.fullmatch(r'(invoice|offer)-[0-9a-f]{30}\.pdf',safe):raise HTTPException(404)
        path=st.DATA_DIR/'pdf'/safe
    elif source=='bot':
        imported=imported_rows('documents',10000)
        if docid not in [r['id'] for r in imported]:raise HTTPException(404)
        path=st.DATA_DIR/'import'/'pdf'/f'bot-{docid}.pdf'
    else: raise HTTPException(404)
    if not path.is_file():raise HTTPException(404,'Salinan PDF belum tersedia, periksa sinkronisasi')
    return FileResponse(path,media_type='application/pdf',filename=f'tosbot-{source}-{docid}.pdf',headers={'Cache-Control':'no-store','Content-Disposition':f'attachment; filename="tosbot-{source}-{docid}.pdf"'})


@app.get('/api/reminders')
def reminders(session=Depends(require_session)):
    return imported_rows('reminders',100)


@app.get('/api/server')
def server_metrics(session=Depends(require_session)):
    mem=psutil.virtual_memory();disk=psutil.disk_usage('/');boot=psutil.boot_time()
    try:
        p=subprocess.run(['systemctl','is-active','tosbot-ai'],text=True,capture_output=True,timeout=2)
        service=p.stdout.strip() or 'unknown'
    except Exception:
        service='unknown'
    return {'hostname':os.uname().nodename, 'cpu_percent':psutil.cpu_percent(interval=0.1),
      'ram_percent':mem.percent,'ram_total':mem.total,'ram_used':mem.used,
      'disk_percent':disk.percent,'disk_total':disk.total,'disk_used':disk.used,
      'uptime_seconds':round(time.time()-boot),'service':service,'snapshot':snapshot_status()}


@app.exception_handler(HTTPException)
async def readable_error(request:Request,exc:HTTPException):
    return JSONResponse({'detail':exc.detail},status_code=exc.status_code)


# --- v0.2.0 dashboard branding and multiple administrators. ---
# The dashboard's uploaded logo is NEVER a PDF/document asset.
class CompanyUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)

class LogoPayload(BaseModel):
    image: str = Field(min_length=35, max_length=3_000_000)

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)

class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=10, max_length=256)
    current_password: str = Field(min_length=1, max_length=256)

class UserDelete(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)

class UserReset(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)

def branding():
    filename=st.DATA_DIR/'branding'/'dashboard-logo.png'
    return {'company_name':st.get_setting('company_name',os.getenv('COMPANY_NAME','PT IMA MULTITEK INDONESIA')),
            'has_logo':filename.is_file(), 'logo_url':'/api/branding/logo' if filename.is_file() else None}

@app.get('/api/branding')
def public_branding():
    # Branding is intentionally public on the login screen; no private company metadata.
    return branding()

@app.get('/api/branding/logo')
def public_logo():
    # Only generated, server-side PNG filename is allowed; never serve paths supplied by users.
    filename=st.DATA_DIR/'branding'/'dashboard-logo.png'
    if not filename.is_file():
        raise HTTPException(404,'Logo belum diunggah')
    return FileResponse(filename,media_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@app.get('/api/settings/company')
def company_settings(session=Depends(require_session)):
    return branding()

@app.put('/api/settings/company')
def update_company(data:CompanyUpdate,session=Depends(csrf)):
    name=data.name.strip()
    if len(name)<2:
        raise HTTPException(400,'Nama perusahaan minimal 2 karakter')
    st.put_setting('company_name',name,session['name'])
    return branding()

@app.post('/api/settings/company/logo')
def upload_company_logo(data:LogoPayload,session=Depends(csrf)):
    # JSON base64 lets us reuse CSRF middleware, with strict file-type/size checks.
    match=re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=]+)',data.image)
    if not match:
        raise HTTPException(400,'Unggah gambar PNG atau JPEG')
    try:
        raw=base64.b64decode(match.group(2),validate=True)
    except (binascii.Error,ValueError):
        raise HTTPException(400,'Isi gambar tidak valid')
    if len(raw)>2_000_000:
        raise HTTPException(413,'Ukuran logo maksimal 2 MB')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG') or image.width>2500 or image.height>2500:
                raise ValueError('Format atau dimensi logo tidak didukung (maksimal 2500px)')
            image.load()
            clean=image.convert('RGBA' if ('A' in image.getbands() or 'transparency' in image.info) else 'RGB')
            clean.thumbnail((1200,1200),Image.Resampling.LANCZOS)
            buff=io.BytesIO()
            clean.save(buff,format='PNG',optimize=True)
            payload=buff.getvalue()
    except (UnidentifiedImageError,Image.DecompressionBombError,OSError,ValueError) as exc:
        raise HTTPException(400,'Gambar tidak valid: '+str(exc)[:100])
    parent=st.DATA_DIR/'branding'
    parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tempfile_name=tempfile.mkstemp(prefix='.new-logo-',dir=str(parent))
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),0o600)
            f.write(payload);f.flush();os.fsync(f.fileno())
        os.replace(tempfile_name,parent/'dashboard-logo.png')
    finally:
        Path(tempfile_name).unlink(missing_ok=True)
    with st.db() as con:
        st.event(con,'dashboard_logo_updated','dashboard-logo',session['name'])
    return branding()

@app.post('/api/settings/password')
def change_password(data:PasswordChange,request:Request,response:Response,session=Depends(csrf)):
    if not st.validate_password(session['name'],data.current_password):
        raise HTTPException(403,'Password sekarang salah')
    try:
        st.set_password(session['name'],data.new_password)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    with st.db() as con:
        st.event(con,'password_changed','self',session['name'])
    response.delete_cookie('tosbot_session',path='/')
    return {'ok':True,'reauth':True}

@app.get('/api/settings/users')
def list_users(session=Depends(require_session)):
    return {'users':st.user_rows(),'current':session['name'],'role':'admin'}

def check_user_proof(session,current_password):
    if not st.validate_password(session['name'],current_password):
        raise HTTPException(403,'Password administrator saat ini salah')

def clean_username(username):
    name=username.strip().lower()
    if not re.fullmatch(r'[a-z][a-z0-9._-]{2,31}',name):
        raise HTTPException(400,'Username: 3–32 karakter, huruf kecil, angka, titik, _ atau -; diawali huruf')
    return name

@app.post('/api/settings/users')
def create_admin(data:NewUser,session=Depends(csrf)):
    check_user_proof(session,data.current_password)
    name=clean_username(data.username)
    if not st.create_user(name,data.password,session['name']):
        raise HTTPException(409,'Username sudah digunakan')
    return {'ok':True,'username':name,'role':'admin'}

@app.post('/api/settings/users/{username}/password')
def reset_user_password(username:str,data:UserReset,session=Depends(csrf)):
    name=clean_username(username)
    check_user_proof(session,data.current_password)
    with st.db() as con:
        if not con.execute('SELECT 1 FROM admin WHERE name=?',(name,)).fetchone():
            raise HTTPException(404,'Pengguna tidak ditemukan')
    try:
        st.set_password(name,data.new_password)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    with st.db() as con:
        st.event(con,'user_password_reset',name,session['name'])
    return {'ok':True,'reauth':name==session['name']}

@app.post('/api/settings/users/{username}/delete')
def remove_user(username:str,data:UserDelete,session=Depends(csrf)):
    name=clean_username(username)
    if name==session['name']:
        raise HTTPException(400,'Akun Anda sendiri tidak dapat dihapus dari halaman ini')
    check_user_proof(session,data.current_password)
    if not st.delete_user(name,session['name']):
        raise HTTPException(409,'Tidak dapat menghapus pengguna terakhir atau pengguna tidak ditemukan')
    return {'ok':True}


# --- v0.3.0: Photos of specific repair tickets (not generic customer photos) ---
class PhotoUpload(BaseModel):
    image_base64: str = Field(min_length=20, max_length=8_000_000)
    caption: str = Field(default='', max_length=180)


def photo_metadata(job_id: int):
    return data_rows('SELECT id,job_id,caption,created_at FROM job_photos WHERE job_id=? ORDER BY id DESC',(job_id,))


def photo_disk_path(filename: str) -> Path:
    if not re.fullmatch(r'job-[0-9]+-[a-f0-9]{32}\.jpg', filename):
        raise HTTPException(404,'Foto tidak tersedia')
    return st.DATA_DIR / 'job_photos' / filename


@app.get('/api/jobs/{jid}/photos')
def get_job_photos(jid:int,session=Depends(require_session)):
    with st.db() as con:
        if not con.execute('SELECT 1 FROM jobs WHERE id=?',(jid,)).fetchone():
            raise HTTPException(404,'Pekerjaan tidak ditemukan')
    return photo_metadata(jid)


@app.post('/api/jobs/{jid}/photos')
def upload_job_photo(jid:int,data:PhotoUpload,session=Depends(csrf)):
    # JSON body is already CSRF-protected, unlike an uncontrolled multipart endpoint.
    with st.db() as con:
        if not con.execute('SELECT 1 FROM jobs WHERE id=?',(jid,)).fetchone():
            raise HTTPException(404,'Pekerjaan tidak ditemukan')
        if con.execute('SELECT COUNT(*) n FROM job_photos WHERE job_id=?',(jid,)).fetchone()['n']>=8:
            raise HTTPException(409,'Maksimal 8 foto per pekerjaan; hapus salah satu dahulu')
    image=data.image_base64.strip()
    if image.startswith('data:'):
        _,sep,image=image.partition(',')
        if not sep: raise HTTPException(400,'Format foto tidak didukung')
    try:
        raw=base64.b64decode(image,validate=True)
    except (binascii.Error,ValueError):
        raise HTTPException(400,'Data foto tidak valid')
    if len(raw)>5*1024*1024:
        raise HTTPException(413,'Foto maksimal 5 MB')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format not in ('JPEG','PNG','WEBP'):
                raise HTTPException(415,'Hanya JPG, PNG, atau WebP')
            if im.width*im.height>20_000_000:
                raise HTTPException(413,'Dimensi foto terlalu besar')
            im.load()
            normalized=ImageOps.exif_transpose(im).convert('RGB')
            normalized.thumbnail((2000,2000),Image.Resampling.LANCZOS)
            buf=io.BytesIO()
            normalized.save(buf,format='JPEG',quality=82,optimize=True)
            jpg=buf.getvalue()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
        raise HTTPException(400,'Foto rusak atau format gambar tidak didukung')
    if len(jpg)>4*1024*1024:
        raise HTTPException(413,'Hasil foto masih terlalu besar')
    folder=st.DATA_DIR/'job_photos'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    filename=f'job-{jid}-{secrets.token_hex(16)}.jpg'
    path=photo_disk_path(filename)
    try:
        with path.open('xb') as fp: fp.write(jpg)
        os.chmod(path,0o600)
        with st.db() as con:
            # A second concurrent upload could have changed the count.
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT COUNT(*) n FROM job_photos WHERE job_id=?',(jid,)).fetchone()['n']>=8:
                raise HTTPException(409,'Batas foto tercapai')
            cur=con.execute('INSERT INTO job_photos(job_id,filename,caption,created_at) VALUES(?,?,?,?)',
                            (jid,filename,data.caption,int(time.time())))
            st.event(con,'job_photo_uploaded',jid,session['name'])
        return {'id':cur.lastrowid,'job_id':jid,'caption':data.caption}
    except Exception:
        path.unlink(missing_ok=True)
        raise


def photo_record(pid:int):
    with st.db() as con:
        row=con.execute('SELECT p.*,j.machine,c.name customer FROM job_photos p JOIN jobs j ON j.id=p.job_id JOIN customers c ON c.id=j.customer_id WHERE p.id=?',(pid,)).fetchone()
    if row is None:raise HTTPException(404,'Foto tidak tersedia')
    return dict(row)


@app.get('/api/jobs/photos/{pid}')
def open_photo(pid:int,session=Depends(require_session)):
    row=photo_record(pid)
    path=photo_disk_path(row['filename'])
    if not path.is_file():raise HTTPException(404,'File foto tidak tersedia')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store', 'X-Content-Type-Options':'nosniff'})


@app.delete('/api/jobs/photos/{pid}')
def delete_photo(pid:int,session=Depends(csrf)):
    with st.db() as con:
        row=con.execute('SELECT filename,job_id FROM job_photos WHERE id=?',(pid,)).fetchone()
        if not row:raise HTTPException(404,'Foto tidak tersedia')
        con.execute('DELETE FROM job_photos WHERE id=?',(pid,))
        st.event(con,'job_photo_deleted',row['job_id'],session['name'])
    photo_disk_path(row['filename']).unlink(missing_ok=True)
    return {'ok':True}


# --- Shared source of truth for Telegram. Loopback-only + a high-entropy key. ---
def require_bridge(request:Request):
    expected=os.environ.get('DASHBOARD_BRIDGE_TOKEN','')
    supplied=request.headers.get('X-Tosbot-Bridge-Key','')
    if len(expected)<32:
        raise HTTPException(503,'Bridge belum diaktifkan di server')
    if not hmac.compare_digest(expected,supplied):
        raise HTTPException(401,'Tidak diizinkan')
    return True


def _search_rows(table:str,q:str,limit:int=20):
    if table=='customers':
        rows=data_rows('SELECT id,name,pic,phone,address,note FROM customers WHERE archived=0 ORDER BY name COLLATE NOCASE LIMIT 1500')
        return [r for r in rows if not q or q.casefold() in (' '.join(str(v) for v in r.values())).casefold()][:limit]
    rows=data_rows('SELECT j.id,j.customer_id,j.machine,j.problem,j.technician,j.status,j.scheduled_date,j.estimate,j.notes,j.created_at,j.updated_at,c.name customer,c.pic pic,(SELECT COUNT(*) FROM job_photos p WHERE p.job_id=j.id) photo_count FROM jobs j JOIN customers c ON c.id=j.customer_id ORDER BY j.id DESC LIMIT 1500')
    return [r for r in rows if not q or q.casefold() in (' '.join(str(v) for v in r.values())).casefold()][:limit]


@app.get('/api/bridge/summary')
def bridge_summary(_=Depends(require_bridge)):
    # Same rows/status definitions as the UI, not Groq's memory.
    with st.db() as con:
        customers=con.execute('SELECT COUNT(*) n FROM customers WHERE archived=0').fetchone()['n']
        jobs=con.execute('SELECT COUNT(*) n FROM jobs').fetchone()['n']
        active=con.execute("SELECT COUNT(*) n FROM jobs WHERE status NOT IN ('selesai','dibatalkan')").fetchone()['n']
        finished=con.execute("SELECT COUNT(*) n FROM jobs WHERE status='selesai'").fetchone()['n']
    return {'customers':customers,'jobs':jobs,'active_jobs':active,'completed_jobs':finished,'source':'dashboard-live'}


@app.get('/api/bridge/customers')
def bridge_customers(q:str='',limit:int=20,_=Depends(require_bridge)):
    return {'results':_search_rows('customers',q[:120],max(1,min(30,limit))),'source':'dashboard-live'}


@app.get('/api/bridge/jobs')
def bridge_jobs(q:str='',limit:int=20,_=Depends(require_bridge)):
    return {'results':_search_rows('jobs',q[:120],max(1,min(30,limit))),'source':'dashboard-live'}


@app.get('/api/bridge/photos')
def bridge_photos(job_id:int,_=Depends(require_bridge)):
    with st.db() as con:
        row=con.execute('SELECT j.id,j.machine,c.name customer FROM jobs j JOIN customers c ON c.id=j.customer_id WHERE j.id=?',(job_id,)).fetchone()
    if not row:raise HTTPException(404,'Tiket servis tidak ditemukan')
    return {'job':dict(row),'photos':photo_metadata(job_id)}


@app.get('/api/bridge/photos/{pid}')
def bridge_photo_bytes(pid:int,_=Depends(require_bridge)):
    row=photo_record(pid)
    path=photo_disk_path(row['filename'])
    if not path.is_file():raise HTTPException(404,'File foto tidak tersedia')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})


@app.get('/api/bridge/finance')
def bridge_finance(scope:str='all',_=Depends(require_bridge)):
    if scope not in ('all','month','today'):
        raise HTTPException(400,'Cakupan tidak valid')
    # Same 500+500 source rows used by Dashboard's Keuangan page.
    rows=finances(session={})
    now=datetime.now(TIMEZONE)
    filtered=[]
    for item in rows:
        try:dt=datetime.fromtimestamp(int(item['ts']),TIMEZONE)
        except (TypeError,ValueError,OverflowError):continue
        if scope=='today' and dt.date()!=now.date():continue
        if scope=='month' and (dt.year,dt.month)!=(now.year,now.month):continue
        filtered.append(item)
    income=sum(int(x['amount']) for x in filtered if x['kind']=='income')
    expense=sum(int(x['amount']) for x in filtered if x['kind']=='expense')
    return {'income':income,'expense':expense,'difference':income-expense,
            'count':len(filtered),'scope':scope,'snapshot':snapshot_status(),'source':'dashboard-and-telegram'}


@app.get('/api/bridge/documents')
def bridge_documents(_=Depends(require_bridge)):
    docs=all_documents()
    return {'count':len(docs),'offers':sum(d['kind']=='offer' for d in docs),
            'invoices':sum(d['kind']=='invoice' for d in docs),'source':'dashboard-and-telegram'}

@app.get('/api/bridge/jobs/{jid}')
def bridge_job(jid:int,_=Depends(require_bridge)):
    with st.db() as con:
        row=con.execute('SELECT j.id,j.customer_id,j.machine,j.problem,j.technician,j.status,j.scheduled_date,j.estimate,j.notes,j.updated_at,c.name customer,c.pic pic,(SELECT COUNT(*) FROM job_photos p WHERE p.job_id=j.id) photo_count FROM jobs j JOIN customers c ON c.id=j.customer_id WHERE j.id=?',(jid,)).fetchone()
    if row is None:raise HTTPException(404,'Tiket tidak ditemukan')
    return dict(row)
