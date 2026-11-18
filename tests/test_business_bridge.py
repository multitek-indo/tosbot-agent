from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from tosbot_ai.business_bridge import BusinessBridge,BusinessAnswer
from tosbot_ai.bot import process_update

class SimulatedBridge(BusinessBridge):
    def __init__(self):
        super().__init__(token='x'*48)
        self.reads=[]
    def get(self,path,params=None):
        params=params or {};self.reads.append((path,params))
        if path=='summary':return {'customers':6,'jobs':2,'active_jobs':2,'completed_jobs':0}
        if path=='customers':
            rows=[{'id':1,'name':'PT ANUGERAH ALFA LESTARI','pic':'Mas Fahrul'}]
            return {'results':[r for r in rows if not params.get('q') or params['q'].casefold() in r['name'].casefold()]}
        if path=='jobs':
            rows=[{'id':2,'machine':'JUKI JK-1900','problem':'error 685','technician':'Imam','status':'baru','photo_count':2,'customer':'PT ANUGERAH ALFA LESTARI'},
                  {'id':1,'machine':'DDL 9000C','problem':'error 24v','technician':'Imam','status':'dijadwalkan','photo_count':0,'customer':'SUMBIRI'}]
            return {'results':[r for r in rows if not params.get('q') or params['q'].casefold() in ' '.join(map(str,r.values())).casefold()]}
        if path=='jobs/2':return {'id':2,'machine':'JUKI JK-1900','problem':'error 685','technician':'Imam','status':'baru','photo_count':2,'customer':'PT ANUGERAH ALFA LESTARI','estimate':0,'scheduled_date':'2026-11-18'}
        if path=='photos':return {'photos':[{'id':9,'caption':'Panel PCB'}, {'id':10,'caption':'Mesin JUKI'}]}
        if path=='finance':return {'income':0,'expense':200000,'difference':-200000,'count':1,'snapshot':{'available':True}}
        if path=='documents':return {'count':2,'offers':1,'invoices':1}
        raise AssertionError((path,params))
    def photo_bytes(self,pid):
        return b'jpegbytes_'+str(pid).encode()

class FakeTelegram:
    def __init__(self):self.replies=[];self.photos=[]
    def say(self,chat,body,**kwargs):self.replies.append((chat,body,kwargs))
    def photo(self,chat,data,caption='',**kwargs):self.photos.append((chat,data,caption,kwargs))

class ForbiddenEngine:
    def handle(self,txt):raise AssertionError('Business query unexpectedly went to Groq/Engine')


def test_deterministic_questions_and_photo_selection():
    bridge=SimulatedBridge()
    assert '6 perusahaan' in bridge.answer('ada berapa customer yang tercatat?').text
    assert 'Total: 2' in bridge.answer('ada berapa pekerjaan servis nya?').text
    assert '#2' in bridge.answer('lihat pekerjaan servis').text
    assert 'Status: baru' in bridge.answer('status servis #2').text
    answer=bridge.answer('kirim foto servis #2')
    assert len(answer.photos)==2 and answer.photos[0][0]==9
    choices=bridge.answer('tampilkan foto servis')
    assert 'Pilih ID' in choices.text and not choices.photos
    assert 'PT ANUGERAH' in bridge.answer('daftar pelanggan').text
    assert '200.000' in bridge.answer('cek keuangan hari ini').text
    assert '2' in bridge.answer('jumlah invoice').text
    assert bridge.answer('buat penawaran ke PT ABC') is None
    assert bridge.answer('sudo rm /tmp/data') is None
    assert 'Dashboard TosBot' in bridge.answer('data dari mana?').text


def test_private_bot_sends_real_photo_and_never_calls_engine():
    b=SimulatedBridge();tg=FakeTelegram();settings=SimpleNamespace(owner_id=55)
    upd={'message':{'message_id':23,'chat':{'type':'private','id':55},'from':{'id':55},'text':'foto servis #2'}}
    process_update(upd,tg,ForbiddenEngine(),settings,business_bridge=b)
    assert 'Foto pekerjaan #2' in tg.replies[0][1]
    assert [x[1] for x in tg.photos]==[b'jpegbytes_9',b'jpegbytes_10']


def test_trusted_group_reply_sends_photo_but_other_group_denied():
    b=SimulatedBridge();tg=FakeTelegram()
    settings=SimpleNamespace(owner_id=55,groups_enabled=True,allowed_group_ids=(-10099,),trusted_group_admin=True)
    msg={'message_id':12,'chat':{'type':'supergroup','id':-10099},'from':{'id':21,'is_bot':False},
         'text':'@mustikasaribot foto servis #2','entities':[]}
    upd={'message':msg}
    process_update(upd,tg,ForbiddenEngine(),settings,group_assistant=object(),bot_username='mustikasaribot',bot_user_id=99,business_bridge=b)
    assert len(tg.photos)==2 and tg.photos[0][0]==-10099
    assert tg.replies[0][2]['reply_to_message_id']==12
    tg2=FakeTelegram()
    msg2={**msg,'chat':{'type':'supergroup','id':-999}}
    process_update({'message':msg2},tg2,ForbiddenEngine(),settings,group_assistant=object(),bot_username='mustikasaribot',bot_user_id=99,business_bridge=b)
    assert not tg2.replies and not tg2.photos


def test_bridge_unconfigured_returns_error_not_hallucinated_data():
    b=BusinessBridge(token='')
    answer=b.answer('berapa pelanggan?')
    assert 'belum dapat dibaca' in answer.text
