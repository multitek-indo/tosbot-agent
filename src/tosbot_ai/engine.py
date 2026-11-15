from __future__ import annotations
import logging
import re
import time
from datetime import datetime,timedelta
from pathlib import Path
from uuid import uuid4
from .ai import AI
from .config import Settings
from .documents import currency,make_pdf,total,valid_item
from .server import disk,memory,service_status,restart_service,status,validate_service
from .storage import Store
from .conversation import ConversationGraph, _safe_memory
from .directory_agent import DirectoryAgent, parse_directory_command, safe_path, CONFIRMATIONS, DIR_ROOT, HOME_ROOT
from .network_agent import parse_ping, ping_private

log=logging.getLogger(__name__)

HELP='''👋 Halo, saya TosBot. Bisa bantu mengelola VPS dan administrasi usaha.

🖥️ "Cek kapasitas disk sekarang", "RAM VPS piro?", "Status server", "Cek dir script", "Cek status nginx".
🧰 "Restart nginx" (hanya unit dalam allowlist, perlu konfirmasi khusus).
💰 "Catat pengeluaran bensin 50 ribu", "Laporan keuangan bulan ini".
⏰ "Ingatkan besok jam 9 bayar listrik", "Daftar pengingat".
📄 "Buat invoice untuk PT ABC", "Buat penawaran untuk PT ABC", lanjutkan percakapan sampai pratinjau dan setuju PDF.

Perintah cepat: /status, /disk, /ram, /keuangan, /pengingat, /batal, /myid, /help.
🗂️ "cd home", "ls", "cek dir script", "buat folder test di /home/tosbot" (konfirmasi).
🌐 "ping ke 192.168.0.1 sebanyak 4 kali".
Terminal tersedia dengan /terminal; eksekusi root memerlukan TOTP dan persetujuan terpisah.'''

class Engine:
    def __init__(self,s:Settings,store:Store):
        self.s=s;self.db=store;self.ai=AI(s)
        self.directory_agent=DirectoryAgent()
        self.flow = None
        try:
            checkpoint_file = self.s.db_path.with_name('tosbot-conversation.sqlite3')
            self.flow = ConversationGraph(self.ai, self.s.owner_id, checkpoint_file)
            log.info('LangGraph conversation checkpoint enabled')
        except ImportError:
            log.warning('LangGraph not installed. Install requirements.txt; legacy memory remains active.')
        except Exception:
            # Service remains available for emergency /disk and /ram diagnosis.
            log.exception('LangGraph checkpoint initialization failed; using legacy history')

    def _state_key(self, key):
        return key if self.s.owner_id >= 0 else f'group_{self.s.owner_id}_{key}'

    def _get_state(self, key, default=None):
        return self.db.get_kv(self._state_key(key), default)

    def _set_state(self, key, value):
        return self.db.set_kv(self._state_key(key), value)

    def _history_key(self):
        return 'history'

    def _history(self):
        if self.flow:
            try:
                turns = self.flow.recent()
                if turns: return turns
            except Exception: log.warning('LangGraph memory read failed')
        return self._get_state(self._history_key(),[])
    def _remember(self,user:str,response:str):
        history=self._history()
        history.extend([{'role':'user','content':_safe_memory(user,650)}, {'role':'assistant','content':_safe_memory(response,900)}])
        self._set_state(self._history_key(),history[-30:])
        if self.flow:
            try: self.flow.remember(user, response)
            except Exception: log.warning('LangGraph memory update failed; legacy history retained')

    def _local_date(self,dt:datetime)->str:
        return dt.astimezone(self.s.tz).strftime('%d/%m/%Y %H:%M WIB')

    def _document_preview(self,d:dict)->str:
        if not d: return 'Belum ada rancangan dokumen.'
        required=[]
        if not str(d.get('customer') or '').strip():
            required.append('customer')
        if not d.get('items') and not d.get('pending_item'):
            required.append('item')
        pending=d.get('pending_item') or {}
        if pending:
            for field in ('name','qty','price'):
                if pending.get(field) in (None, ''): required.append('item_'+field)
        dtype='PENAWARAN' if d['type']=='offer' else 'INVOICE'
        lines=[f'📄 Rancangan {dtype}',f'Pelanggan: {d.get("customer") or "[belum diisi]"}',
               f'PIC/penerima: {d.get("attention") or "[belum disebutkan]"}',
               'Nomor: '+(d.get('number') or '[otomatis setelah final]')]
        for idx,x in enumerate(d.get('items',[]),1):
            lines.append(f'{idx}. {x["name"]} — {x["qty"]} {x["unit"]} × {currency(x["price"])} = {currency(x["qty"]*x["price"])}')
            if x.get('note'): lines.append('   Keterangan barang: '+x['note'])
        if pending:
            lines.append('Item sedang dilengkapi: '+str(pending.get('name') or '[nama belum ada]')+
                         f' | Jumlah: {pending.get("qty") or "?"} | Harga/unit: '+
                         (currency(pending['price']) if isinstance(pending.get('price'),int) else '?'))
        lines.append('Diskon: '+currency(int(d.get('discount') or 0)))
        lines.append('TOTAL: '+currency(total(d)))
        if d.get('terms'):lines.append('Ketentuan:\n'+str(d['terms']))
        if d['type']=='invoice':
            lines.append('Pembayaran: '+str(d.get('payment_type') or 'belum diatur'))
            if d.get('po_number'):lines.append('PO Customer: '+str(d['po_number']))
        if required:
            d['status']='collecting'
            if 'customer' in required:
                question='Untuk perusahaan atau customer siapa dokumen ini dibuat?'
            elif 'item_name' in required:
                question='Nama barang atau jasanya apa?'
            elif 'item_qty' in required:
                question='Berapa unit/jumlah untuk item '+str(pending.get('name') or 'tersebut')+'?'
            elif 'item_price' in required:
                question='Harga per unitnya berapa rupiah?'
            else:
                question='Barang/jasa apa yang akan ditulis, berapa unit, dan berapa harga satuannya?'
            lines.append('\n'+question+' Boleh dijawab dengan bahasa biasa.')
        else:
            d['status']='awaiting_confirm'
            lines.append('\nJika ada PIC, ketentuan, atau PO yang ingin ditambah, sebutkan saja.')
            lines.append('Jika sudah tepat, balas "sudah sesuai, buat PDF". Koreksi kolom tertentu juga bisa.')
        self.db.save_draft(self.s.owner_id,d)
        return '\n'.join(lines)

    @staticmethod
    def _merge_partial_item(d: dict, incoming: dict) -> bool:
        if not isinstance(incoming,dict): return False
        allowed=('name','qty','unit','price','note')
        incoming={k:v for k,v in incoming.items() if k in allowed and v not in ('',None)}
        if not incoming: return False
        current={**(d.get('pending_item') or {}),**incoming}
        normalized=valid_item(current)
        if normalized:
            d.setdefault('items',[]).append(normalized)
            d.pop('pending_item',None)
        else:
            d['pending_item']=current
        return True

    def _default_offer_terms(self,d: dict) -> None:
        if d.get('type')!='offer' or d.get('terms'):return
        if not any('service' in (x.get('name') or '').lower() or 'servis' in (x.get('name') or '').lower()
                   or 'perbaikan' in (x.get('name') or '').lower() for x in d.get('items',[])):
            return
        selfbank=f'{self.s.bank} No.Rek {self.s.account} An. {self.s.account_name}'
        d['terms']=(
            'a. Garansi 1 bulan setelah barang diterima oleh customer\n'
            'b. Pembayaran melalui transfer '+selfbank+'\n'
            'c. Pembayaran dilakukan sejumlah unit mesin yang dinyatakan berhasil diperbaiki'
        )
        d['terms_source']='template_service_default'

    def _create_draft(self,data:dict)->str:
        dtype=str(data.get('doc_type') or '').lower()
        if dtype in ('quotation','quote','penawaran'):dtype='offer'
        if dtype not in ('offer','invoice'):
            return 'Mau membuat invoice atau surat penawaran?'
        d={'type':dtype,'customer':str(data.get('customer') or '').strip()[:150],
           'attention':str(data.get('attention') or '').strip()[:120],
           'items':[],'discount':0,'terms':'','number':'',
           'po_number':'','payment_type':'CASH PAYMENT','status':'collecting'}
        for x in (data.get('items') or [])[:40]:
            if not isinstance(x,dict): continue
            if valid_item(x) and not d.get('pending_item'):
                d['items'].append(valid_item(x))
            else:
                self._merge_partial_item(d,x)
        for key in ('terms','number','po_number','po_date','payment_type'):
            if data.get(key): d[key]=str(data[key])[:1600 if key=='terms' else 80]
        if data.get('discount') is not None:
            try: d['discount']=max(0,min(int(data['discount']),sum(x['qty']*x['price'] for x in d['items'])))
            except (TypeError,ValueError):pass
        self._default_offer_terms(d)
        self.db.save_draft(self.s.owner_id,d)
        return self._document_preview(d)

    def _patch_draft(self,patch:dict)->str:
        d=self.db.get_draft(self.s.owner_id)
        if not d:return 'Belum ada draft. Mulai dengan "buat invoice PT ABC" atau "buat penawaran PT ABC".'
        if not isinstance(patch,dict):return 'Bagian mana yang ingin diubah?'
        applied=[]
        for field in ('customer','attention','number','po_number','po_date','payment_type'):
            if field in patch and isinstance(patch[field],str):
                d[field]=patch[field].strip()[:150];applied.append(field)
        if 'discount' in patch:
            try:
                amount=int(patch['discount'])
                if 0<=amount<=sum(x['qty']*x['price'] for x in d['items']):
                    d['discount']=amount;applied.append('discount')
            except (TypeError,ValueError):pass
        if 'terms' in patch and isinstance(patch['terms'],str):
            d['terms']=patch['terms'].strip()[:1600];applied.append('terms')
        if 'terms_add' in patch and isinstance(patch['terms_add'],str):
            d['terms']=(d['terms']+'\n'+patch['terms_add'].strip()).strip()[:1600];applied.append('terms_add')
        if 'items' in patch and isinstance(patch['items'],list):
            if patch.get('item_mode')=='replace':
                d['items']=[];d.pop('pending_item',None)
            for item in patch['items'][:40]:
                if self._merge_partial_item(d,item):applied.append('items')
            d['items']=d['items'][:40]
        if 'item_changes' in patch and isinstance(patch['item_changes'],dict):
            try:idx=int(patch.get('target_index') or 1)-1
            except (ValueError,TypeError):idx=-1
            if not 0<=idx<len(d['items']):
                # Some models represent a reply to an unfinished item as item_changes.
                # Apply only when the single pending item is unambiguous.
                if d.get('pending_item') and idx in (-1,0,len(d['items'])):
                    if self._merge_partial_item(d,patch['item_changes']):
                        applied.append('item yang sedang dilengkapi')
                else:
                    return 'Item yang mau diubah tidak ditemukan. Sebutkan nomor item pada pratinjau.'
            else:
                old=d['items'][idx]
                changed={**old,**{k:v for k,v in patch['item_changes'].items() if k in ('name','qty','unit','price','note')}}
                new=valid_item(changed)
                if not new:return 'Perubahan item tidak valid. Pastikan jumlah dan harga berupa angka.'
                d['items'][idx]=new;applied.append(f'item {idx+1}')
        if not applied:return 'Bagian mana yang ingin dikoreksi? Misalnya "PIC Bu Nurul", "jumlah item 1 jadi 2", atau "keterangan biaya sparepart belum termasuk".'
        self._default_offer_terms(d)
        # Never silently confirm after an edit.
        d['status']='collecting'
        self.db.save_draft(self.s.owner_id,d)
        return '✅ Diperbarui: '+', '.join(applied)+'.\n\n'+self._document_preview(d)

    def _finalize(self)->tuple[str,Path|None]:
        d=self.db.get_draft(self.s.owner_id)
        if not d:return 'Tidak ada draft dokumen aktif.',None
        if d.get('status')!='awaiting_confirm':return 'Dokumen belum lengkap. Lengkapi detail lalu periksa pratinjau.',None
        if not d.get('items') or not d.get('customer') or d.get('pending_item'):
            return 'Dokumen masih belum lengkap.',None
        now=datetime.now(self.s.tz)
        number=d.get('number') or self.db.next_number(d['type'],now.year)
        if len(number)>80 or not re.fullmatch(r'[A-Za-z0-9/_.-]+',number):
            return 'Nomor dokumen hanya boleh huruf, angka, garis miring, titik, atau tanda hubung.',None
        safe_id=uuid4().hex[:10]
        path=self.s.out_dir/f'{d["type"]}-{now.strftime("%Y%m%d")}-{safe_id}.pdf'
        try:
            make_pdf(d,number,path,self.s,now)
            self.db.reserve_number(self.s.owner_id,d['type'],d['customer'],path,total(d),number)
        except Exception as exc:
            try:path.unlink(missing_ok=True)
            except OSError:pass
            log.exception('document save failed')
            return 'Gagal membuat PDF. Cek apakah nomor dokumen sudah dipakai atau folder penyimpanan tersedia.',None
        self.db.delete_draft(self.s.owner_id)
        self.db.audit(self.s.owner_id,'document_created',f'{d["type"]} {number}')
        return f'✅ PDF {d["type"]} {number} selesai. Total {currency(total(d))}.',path

    def _finance_add(self,d:dict)->str:
        kind=str(d.get('kind') or '').lower()
        amount=d.get('amount')
        if kind not in ('income','expense'):
            return 'Ini pemasukan atau pengeluaran?'
        try:amount=int(amount)
        except (TypeError,ValueError):return 'Nominalnya berapa rupiah? Contoh: 150000 atau 150 ribu.'
        if not 0<amount<=10**12:return 'Nominal harus lebih besar dari nol dan masuk akal.'
        category=str(d.get('category') or 'lainnya').strip()[:70]
        note=str(d.get('note') or category).strip()[:400]
        when=datetime.now(self.s.tz)
        if d.get('date'):
            try:
                parsed=datetime.strptime(str(d['date']),'%Y-%m-%d')
                when=parsed.replace(hour=12,tzinfo=self.s.tz)
            except ValueError:return 'Tanggal tidak valid. Gunakan YYYY-MM-DD.'
        id=self.db.add_finance(self.s.owner_id,kind,amount,category,note,int(when.timestamp()))
        self.db.audit(self.s.owner_id,'finance_add',f'id={id} {kind} {amount}')
        return f'✅ Tercatat #{id}: {"pemasukan" if kind=="income" else "pengeluaran"} {currency(amount)}\nKategori: {category}\nCatatan: {note}'

    def _finance_report(self,d:dict)->str:
        now=datetime.now(self.s.tz)
        period=str(d.get('period') or 'this_month')
        if period=='all':
            begin=0;end=2**31-1;label='Sepanjang waktu'
        else:
            try:
                if re.fullmatch(r'\d{4}-\d{2}',period):year,month=map(int,period.split('-'))
                else:year,month=now.year,now.month
                start=datetime(year,month,1,tzinfo=self.s.tz)
                after=datetime(year+(month==12),1 if month==12 else month+1,1,tzinfo=self.s.tz)
            except ValueError:return 'Format bulan tidak valid. Contoh 2026-11.'
            begin=int(start.timestamp());end=int(after.timestamp());label=start.strftime('%m/%Y')
        result=self.db.finance_report(self.s.owner_id,begin,end)
        inc,ni=result.get('income',(0,0));out,no=result.get('expense',(0,0))
        return (f'📊 Laporan keuangan {label}\nPemasukan ({ni}): {currency(inc)}\n'
                f'Pengeluaran ({no}): {currency(out)}\nSelisih arus kas tercatat: {currency(inc-out) if inc>=out else "-"+currency(out-inc)}\n'
                'Catatan: ini hanya transaksi yang dicatat di TosBot, bukan saldo rekening.')

    def _reminder_add(self,d:dict)->str:
        title=str(d.get('title') or '').strip()[:250]
        if not title:return 'Apa yang ingin saya ingatkan?'
        raw=str(d.get('due') or '').strip()
        if not raw:return 'Jam berapa pengingatnya? Contoh: besok jam 09.00.'
        try:
            due=datetime.fromisoformat(raw.replace('Z','+00:00'))
            if due.tzinfo is None:due=due.replace(tzinfo=self.s.tz)
            due=due.astimezone(self.s.tz)
        except ValueError:return 'Tanggal atau jam kurang jelas. Contoh: 16 November 2026 jam 09.00.'
        if due.timestamp()<time.time()+15:return 'Waktu pengingat sudah lewat. Pilih tanggal dan jam ke depan.'
        if due.timestamp()>time.time()+10*365*86400:return 'Tanggal pengingat terlalu jauh.'
        id=self.db.add_reminder(self.s.owner_id,title,int(due.timestamp()))
        return f'⏰ Pengingat #{id} tersimpan:\n{title}\n{self._local_date(due)}'

    def _reminder_list(self)->str:
        rows=self.db.list_reminders(self.s.owner_id)
        if not rows:return 'Belum ada pengingat aktif.'
        lines=['⏰ Pengingat aktif:']
        for r in rows:
            date=datetime.fromtimestamp(r['due'],self.s.tz)
            lines.append(f"#{r['id']} {self._local_date(date)} — {r['title']}")
        return '\n'.join(lines)

    @staticmethod
    def _fix_recipient(text: str, parsed: dict, draft: dict | None) -> dict:
        """PIC is a recipient, not an item remark. Never infer an unspecified PIC."""
        if not draft and parsed.get('action') not in ('document_create', 'document_update'):
            return parsed
        # Quantity guard: model IDs and monetary numerals are NOT proof of quantity.
        # A plain numeric answer is accepted only while waiting for a missing qty.
        explicit_quantity=bool(re.search(
            r'(?i)\b\d+\s*(?:unit|pcs|buah|biji|item|mesin)\b|'
            r'\b(?:qty|jumlah|sebanyak|kuantitas)\s*(?:=|:)?\s*\d+\b|'
            r'\b(?:satu|dua|tiga|empat|lima|siji|loro|telu|kalih|setunggal)\s*(?:unit|pcs|buah|mesin)?\b', text))
        if draft and (draft.get('pending_item') or {}).get('qty') in (None,''):
            if re.fullmatch(r'\s*\d{1,4}\s*',text): explicit_quantity=True
        action=parsed.get('action')
        if action in ('document_create','document_update') and not explicit_quantity:
            data=parsed.get('data') or {}
            items=data.get('items') if action=='document_create' else (data.get('patch') or {}).get('items')
            for item in (items or []):
                if isinstance(item,dict): item.pop('qty',None)
        match=re.search(r'(?i)\b(?:pic|attention|attn|u\.?p\.?)\s*(?:\:|adalah|nya)?\s*'
                        r'((?:bapak|pak|ibu|bu|mas|mbak|mr|mrs)\.?\s+[\w.-]+(?:\s+[\w.-]+)?)',text)
        if not match:return parsed
        pic=' '.join(match.group(1).split())[:120]
        action=parsed.get('action')
        if action=='document_create':
            parsed.setdefault('data',{})['attention']=pic
            items=parsed['data'].get('items') or []
        else:
            if action not in ('document_update', 'document_create'):
                parsed={'action':'document_update','data':{'patch':{}},'confidence':1.0}
            patch=parsed.setdefault('data',{}).setdefault('patch',{})
            patch['attention']=pic
            items=patch.get('items') or []
        # Never use PIC phrase as item KETERANGAN.
        for item in items:
            if isinstance(item,dict) and re.fullmatch(r'(?i)\s*(?:pic|attention|attn)\s*[:=]?\s*'+
                                                       re.escape(pic)+r'\s*',str(item.get('note') or '')):
                item['note']=''
        return parsed

    def _quick(self,text:str)->str|None:
        raw=text.strip().lower()
        if raw in ('/start','/help','/bantuan'):return HELP
        if raw in ('/status','/server'):return status()
        if raw in ('/disk','/storage'):return disk()
        if raw in ('/ram','/memori'):return memory()
        if raw in ('/keuangan','/finance'):return self._finance_report({})
        if raw in ('/pengingat','/reminders'):return self._reminder_list()
        if raw in ('/batal','/cancel'):
            self.db.delete_draft(self.s.owner_id)
            self._set_state('pending_admin',None)
            self._set_state('pending_directory',None)
            self._set_state('pending_mkdir',None)
            return 'Proses draft/konfirmasi admin dibatalkan.'
        return None

    def _maybe_cd(self, text: str) -> str | None:
        low=text.lower().strip().rstrip('!').strip()
        if low in ('pwd','/pwd','direktori sekarang','lagi di folder mana'):
            return '📍 Direktori aktif TosBot: '+str(self._get_state('current_dir') or HOME_ROOT)
        match=re.match(r'^cd(?:\s+(.+))?$', low)
        if not match:
            return None
        arg=(match.group(1) or '').strip()
        if not arg:
            return 'Gunakan `cd home`, `cd script`, atau `cd /home/tosbot/script/ai-agent`.'
        current=self._get_state('current_dir') or HOME_ROOT
        path=safe_path(arg,current)
        if not path:
            return ('⛔ Direktori di luar izin. `cd` di TosBot hanya mengubah konteks '
                    'dalam /home/tosbot, bukan menjalankan shell root.')
        result=self.directory_agent.run('list',path)
        if not result.startswith('📂 '):
            return result
        self._set_state('current_dir',path)
        return f'📍 Direktori aktif sekarang: {path}\nKetik `ls` untuk melihat isinya.'

    @staticmethod
    def _mkdir_parse(text: str) -> tuple[str|None,str|None] | None:
        t=str(text or '').strip()
        low=t.lower()
        if not (re.search(r'\bmkdir\b',low) or re.search(r'\b(?:buat|buatkan|bikin|gawekno|gawe)\s+(?:(?:sebuah|folder baru|direktori baru)\s+)?(?:folder|direktori|dir)\b',low)):
            return None
        if low.startswith('mkdir '):
            raw=t.split(maxsplit=1)[1].strip().strip('`"\'')
            return (raw, None) if raw.startswith('/') else (None,raw)
        explicit=re.search(r'(/(?:home|root|etc|var)(?:/[A-Za-z0-9_.-]+)*/?)',t)
        location=explicit.group(1).rstrip('/') if explicit else None
        by_name=re.search(r'\b(?:dengan nama|bernama|nama)\s+["`\']?([A-Za-z0-9][A-Za-z0-9_.-]{0,79})',t,re.I)
        name=by_name.group(1) if by_name else None
        if not name:
            m=re.search(r'\b(?:folder|direktori|dir)\s+([A-Za-z0-9][A-Za-z0-9_.-]{0,79})\b',t,re.I)
            if m and m.group(1).lower() not in {'di','dalam','pada','baru','dengan','bernama','yang'}:
                name=m.group(1)
        if not location:
            near=re.search(r'\b(?:di|dalam|pada)\s+(?:direktori|folder|dir)?\s*(home|script|skrip|ai-agent)\b',t,re.I)
            if near:
                location=near.group(1).lower()
        return location,name

    def _request_mkdir(self, parent: str, name: str) -> str:
        current=self._get_state('current_dir') or HOME_ROOT
        parent=safe_path(parent,current)
        if parent not in (HOME_ROOT, HOME_ROOT+'/script'):
            return ('⛔ Pembuatan folder hanya tersedia langsung di /home/tosbot '
                    'atau /home/tosbot/script. Tidak ada folder yang dibuat.')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',str(name or '')):
            return 'Nama folder tidak valid. Gunakan huruf, angka, tanda hubung atau underscore.'
        target=parent+'/'+name
        self._set_state('pending_mkdir',{'path':target,'created_at':int(time.time()),'state':'confirm'})
        return (f'📁 Akan membuat folder: {target}\n'
                'Konfirmasi dengan "ya buatkan" dalam 120 detik, atau balas "batal". '
                'Belum ada perubahan pada VPS.')

    def _maybe_mkdir(self,text:str) -> str|None:
        low=text.lower().strip().strip(' .!')
        pending=self._get_state('pending_mkdir')
        if pending and time.time()-pending.get('created_at',0)>120:
            self._set_state('pending_mkdir',None)
            pending=None
            if low in CONFIRMATIONS:
                return 'Konfirmasi pembuatan folder sudah kedaluwarsa. Kirim ulang perintah membuat folder.'
        if pending and low in ('batal','batal buat folder','ora dadi','mboten dados','cancel'):
            self._set_state('pending_mkdir',None)
            return 'Pembuatan folder dibatalkan. Tidak ada perubahan.'
        if pending and low in CONFIRMATIONS:
            if pending.get('state')=='confirm':
                self._set_state('pending_mkdir',None)
                result=self.directory_agent.mkdir(pending['path'])
                self.db.audit(self.s.owner_id,'mkdir',pending['path'])
                return result
            return 'Lokasi atau nama folder belum lengkap. Sebutkan path yang jelas.'
        parsed=self._mkdir_parse(text)
        if parsed:
            location,name=parsed
            if location and location.startswith('/') and not name and location.count('/')>=2:
                # Full target supplied, including a disallowed full path: validate below.
                parent, name=location.rsplit('/',1)
                location=parent
            if not name:
                self._set_state('pending_mkdir',{'state':'name','parent':location,'created_at':int(time.time())})
                return 'Nama folder yang ingin dibuat apa?'
            if not location:
                location=self._get_state('current_dir') or HOME_ROOT
            if location in ('/home','/root','/etc','/var'):
                self._set_state('pending_mkdir',{'state':'location','name':name,'created_at':int(time.time())})
                return (f'Folder bernama {name} belum dibuat. Untuk keamanan saya tidak dapat membuatnya '
                        f'langsung di {location}. Pilih `/home/tosbot` atau `/home/tosbot/script`.')
            return self._request_mkdir(location,name)
        if pending and pending.get('state')=='location':
            selected=safe_path(low, self._get_state('current_dir') or HOME_ROOT)
            if selected:
                self._set_state('pending_mkdir',None)
                return self._request_mkdir(selected,pending['name'])
        if pending and pending.get('state')=='name':
            if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',low):
                self._set_state('pending_mkdir',None)
                return self._request_mkdir(pending.get('parent') or (self._get_state('current_dir') or HOME_ROOT),low)
        return None

    def _maybe_directory(self, text: str) -> str | None:
        low=text.lower().strip().strip(' .!')
        pending=self._get_state('pending_directory')
        cwd=self._get_state('current_dir') or HOME_ROOT
        if pending and low in ('/batal','batal','ora dadi','mboten dados'):
            self._set_state('pending_directory',None)
            return 'Pemeriksaan direktori dibatalkan.'
        if pending and low in CONFIRMATIONS:
            self._set_state('pending_directory',None)
            return self.directory_agent.run(pending['operation'],pending.get('path') or cwd)
        if pending:
            selected=safe_path(low,cwd)
            if selected:
                self._set_state('pending_directory',None)
                return self.directory_agent.run(pending['operation'],selected)
        if not pending and low in CONFIRMATIONS:
            old=self._history()[-8:]
            if old and old[-1].get('role')=='assistant':
                previous=str(old[-1].get('content') or '').lower()
                if 'apakah' in previous and ('direktori' in previous or 'folder' in previous):
                    prior=next((parse_directory_command(str(h.get('content') or ''),cwd)
                                for h in reversed(old[:-1]) if h.get('role')=='user'
                                and parse_directory_command(str(h.get('content') or ''),cwd)),None)
                    op,path=prior if prior else ('list',cwd)
                    return self.directory_agent.run(op,path or cwd)
        command=parse_directory_command(text,cwd)
        if command:
            operation,path=command
            if path and safe_path(path):
                self._set_state('pending_directory',None)
                return self.directory_agent.run(operation,path)
            if re.search(r'\b(?:/root|root|/etc|/var)\b',low) or '/home/' in low:
                return ('⛔ Path di luar izin. Saya bisa melihat /home/tosbot '
                        'dan subfoldernya, bukan /root atau direktori sistem.')
            self._set_state('pending_directory',{'operation':operation,'path':None})
            return 'Direktori mana yang ingin dilihat? Contoh: home, script, atau ai-agent.'
        return None

    def handle(self,text:str)->tuple[str,Path|None]:
        text=text.strip()
        if not text:return 'Kirim pesan teks, ya.',None
        if len(text)>4000:return 'Pesan terlalu panjang (maksimal 4000 karakter).',None
        quick=self._quick(text)
        if quick is not None:return quick,None
        # Finite tools run locally; no model can fabricate tool success.
        create_reply=self._maybe_mkdir(text)
        if create_reply is not None:
            self._remember(text,create_reply)
            return create_reply,None
        cwd_reply=self._maybe_cd(text)
        if cwd_reply is not None:
            self._remember(text,cwd_reply)
            return cwd_reply,None
        parsed_ping=parse_ping(text)
        if parsed_ping is not None:
            address,count=parsed_ping
            answer=ping_private(address,count)
            self.db.audit(self.s.owner_id,'server_ping',address or 'missing-address')
            self._remember(text,answer)
            return answer,None
        # Upgrade old conversational follow-ups to actual read-only tools.
        if text.lower().strip() in CONFIRMATIONS:
            old=self._history()[-8:]
            if old and old[-1].get('role')=='assistant':
                previous=str(old[-1].get('content') or '').lower()
                if 'apakah' in previous and 'ping' in previous:
                    prior=next((parse_ping(str(h.get('content') or '')) for h in reversed(old[:-1])
                                if h.get('role')=='user' and parse_ping(str(h.get('content') or ''))),None)
                    if prior:
                        answer=ping_private(*prior)
                        self._remember(text,answer)
                        return answer,None
        # File listing/counting is read-only and uses an actual backend tool.
        # Parse common instructions before the LLM, preventing repetitive questions.
        filesystem_reply=self._maybe_directory(text)
        if filesystem_reply is not None:
            self._remember(text,filesystem_reply)
            return filesystem_reply,None
        draft=self.db.get_draft(self.s.owner_id)
        low=text.lower().strip().strip('.')
        pending=self._get_state('pending_admin')
        if pending:
            if time.time()-pending.get('created_at',0)>90:
                self._set_state('pending_admin',None)
                pending=None
            elif low in ('batalkan restart','batal restart','/batalrestart'):
                self._set_state('pending_admin',None)
                return 'Permintaan restart dibatalkan.',None
            elif low==f'konfirmasi restart {pending.get("service","").lower()}':
                self._set_state('pending_admin',None)
                self.db.audit(self.s.owner_id,'service_restart',pending['service'])
                return restart_service(self.s,pending['service']),None
        if draft and low in ('sudah sesuai','sudah sesuai buat pdf','sudah sesuai, buat pdf',
                            'setuju buat pdf','buat pdf','generate pdf','iya buat pdf',
                            'oke buat pdf','nggih leres buat pdf','konfirmasi dokumen'):
            return self._finalize()
        if draft and low in ('batal dokumen','batalkan invoice','batalkan penawaran'):
            self.db.delete_draft(self.s.owner_id)
            return 'Draft dokumen dibatalkan.',None
        history=self._history()
        try:
            if self.flow:
                parsed=self.flow.interpret(text,draft,history)
            else:
                parsed=self.ai.understand(text,history,draft)
            parsed=self._fix_recipient(text,parsed,draft)
        except RuntimeError as err:
            # Read-only metrics still available even if external AI is down.
            if re.search(r'\b(disk|storage|penyimpanan|kapasitas hardisk)\b',low):return disk(),None
            if re.search(r'\b(ram|memori|memory)\b',low):return memory(),None
            return str(err),None
        action=parsed.get('action');d=parsed.get('data',{})
        self.db.audit(self.s.owner_id,action)
        attachment=None
        if action=='server_status':answer=status()
        elif action=='server_disk':answer=disk()
        elif action=='server_memory':answer=memory()
        elif action in ('server_directory_list','server_directory_count','server_directory_tree'):
            op={'server_directory_list':'list','server_directory_count':'count','server_directory_tree':'tree'}[action]
            path=safe_path(d.get('path'),self._get_state('current_dir') or HOME_ROOT)
            if path: answer=self.directory_agent.run(op,path)
            else:
                self._set_state('pending_directory',{'operation':op,'path':None})
                answer='Direktori mana yang ingin dilihat? Anda bisa memilih home, script, atau ai-agent.'
        elif action=='server_ping':answer=ping_private(str(d.get('address') or d.get('ip') or ''), d.get('count',4))
        elif action=='server_directory_cd':
            answer=self._maybe_cd('cd '+str(d.get('path') or '')) or 'Sebutkan folder tujuan.'
        elif action=='server_directory_mkdir':
            pathname=str(d.get('path') or '').strip()
            answer=self._maybe_mkdir('mkdir '+pathname) or 'Sebutkan lokasi lengkap folder yang ingin dibuat.'
        elif action=='server_service_status':answer=service_status(self.s,str(d.get('service') or ''))
        elif action=='server_service_restart':
            name=validate_service(self.s,str(d.get('service') or ''))
            if not name:answer='Restart ditolak: unit belum diizinkan admin. Tambahkan melalui ADMIN_ALLOWED_SERVICES dan allowlist root.'
            else:
                self._set_state('pending_admin',{'service':name,'created_at':int(time.time())})
                answer=(f'⚠️ Restart {name} dapat mengganggu layanan.\n'
                        f'Jika yakin, balas persis: KONFIRMASI RESTART {name}\n'
                        'Berlaku selama 90 detik. Untuk batal, balas "batal restart".')
        elif action=='finance_add':answer=self._finance_add(d)
        elif action=='finance_report':answer=self._finance_report(d)
        elif action=='reminder_add':answer=self._reminder_add(d)
        elif action=='reminder_list':answer=self._reminder_list()
        elif action=='document_create':answer=self._create_draft(d)
        elif action=='document_update':answer=self._patch_draft(d.get('patch',{}))
        elif action=='document_preview':
            draft=self.db.get_draft(self.s.owner_id)
            answer=self._document_preview(draft) if draft else 'Tidak ada draft dokumen.'
        elif action=='document_confirm':
            if re.search(r'\b(setuju|konfirmasi|sesuai|buat(?:kan)?\s+pdf|generate\s+pdf|iya|nggih)\b',low):
                answer,attachment=self._finalize()
            else:
                answer='Untuk membuat PDF, balas secara eksplisit: sudah sesuai, buat PDF.'
        elif action=='document_cancel':
            self.db.delete_draft(self.s.owner_id);answer='Draft dokumen dibatalkan.'
        elif action=='help':answer=HELP
        elif action=='chat':
            try:answer=self.ai.converse(text,history,draft)
            except RuntimeError:answer='Maaf, AI sedang tidak tersedia. Coba lagi atau gunakan /help.'
        else:answer=str(parsed.get('ambiguity') or 'Bisa jelaskan maksudnya sedikit lebih spesifik?')[:500]
        self._remember(text,answer)
        return answer,attachment
