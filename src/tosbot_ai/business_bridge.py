"""Live, deterministic dashboard data for TosBot Telegram queries.

Only exact, intentionally supported business questions use this bridge. The LLM
is not allowed to invent CRM/job/photo facts. No dashboard password or SQLite
access is granted to the bot; the API uses a private loopback bearer token.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
import httpx

LOG = logging.getLogger(__name__)

@dataclass
class BusinessAnswer:
    text: str
    photos: tuple[tuple[int, str], ...] = ()


class BusinessBridge:
    def __init__(self, token=None, url=None, client=None):
        self.token = token if token is not None else os.environ.get('TOSBOT_DASHBOARD_BRIDGE_TOKEN','')
        self.base = (url or os.environ.get('TOSBOT_DASHBOARD_URL','http://127.0.0.1:8765')).rstrip('/')
        self.http = client or httpx.Client(timeout=httpx.Timeout(9.0,connect=2.0),trust_env=False)
        # Do not permit a config mistake to exfiltrate a shared token off the VPS.
        if not re.fullmatch(r'https?://(?:127\.0\.0\.1|localhost):[0-9]{2,5}',self.base):
            self.base='http://127.0.0.1:8765'

    def get(self, path, params=None):
        if len(self.token)<32:
            raise ConnectionError('Dashboard bridge is not configured')
        response=self.http.get(self.base+'/api/bridge/'+path,params=params or {},
                               headers={'X-Tosbot-Bridge-Key':self.token})
        response.raise_for_status()
        return response.json()

    def photo_bytes(self, pid):
        if len(self.token)<32:
            raise ConnectionError('Bridge not configured')
        response=self.http.get(self.base+f'/api/bridge/photos/{int(pid)}',
                               headers={'X-Tosbot-Bridge-Key':self.token})
        response.raise_for_status()
        if len(response.content)>5*1024*1024 or response.headers.get('content-type','').split(';')[0]!='image/jpeg':
            raise ValueError('Unexpected image response')
        return response.content

    @staticmethod
    def rupiah(value):
        return 'Rp'+f'{int(value or 0):,}'.replace(',','.')

    @staticmethod
    def extract_job_id(text):
        m=re.search(r'(?<!\w)#\s*(\d{1,9})(?!\d)',text)
        if m:return int(m.group(1))
        m=re.search(r'(?i)\b(?:order|tiket|servis|service|pekerjaan)\s+(?:no\.?\s*)?(\d{1,9})\b',text)
        return int(m.group(1)) if m else None

    @staticmethod
    def clean_query(text):
        # Strip verbs and common filler, but preserve customer/machine names.
        text=re.sub(r'(?i)\b(?:tolong|coba|bisa|dong|saya|kamu|anda|minta|ingin|tunjukkan|tampilkan|kirimkan|kirim|lihat|carikan|cari|cek|daftar|list|ada|bagaimana|kondisi|total|jumlah|foto|gambar|barang|pekerjaan|servis|service|order|tiket|nomor|no|mesin|pelanggan|customer|klien|yang|untuk|milik|punya|dari|di|ke|pada|tercatat|berapa|detail|status|data|ini|itu|nya|sekarang|saat)\b',' ',text)
        return re.sub(r'\s+',' ',text).strip(' ?.!,#')[:120]

    @staticmethod
    def fmt_job(j):
        return (f"#{j['id']} — {j['customer']} | {j['machine']}\n"
                f"   Status: {j['status'].replace('_',' ')} | Teknisi: {j.get('technician') or '-'}\n"
                f"   Keluhan: {(j.get('problem') or '-')[:200]} | Foto: {j.get('photo_count',0)}")

    def answer(self,text):
        text=(text or '').strip()
        low=text.casefold()
        if not text:return None
        # Ignore writes, administrative commands, and normal document creation.
        if re.match(r'(?i)^\s*(?:/sh|/sudo|/auth|sudo|apt|bash|sh|systemctl|rm|dd|chmod|chown|reboot|shutdown|buat(?:kan)?|tambah|catat|ubah|edit|hapus|restart)\b',text):
            return None
        if re.search(r'\bdata\s+(?:tadi\s+)?dari\s+mana\b|\bsumber\s+data\b',low):
            return BusinessAnswer('Data pelanggan, pekerjaan servis, dan foto saya ambil langsung dari Dashboard TosBot. Keuangan menggabungkan catatan dashboard dengan salinan transaksi TosBot yang disinkronkan berkala. Saya tidak mengarang jumlah dari percakapan.')
        wants_photo=bool(re.search(r'\b(foto|photo|gambar)\b',low))
        jobs_word=bool(re.search(r'\b(servis|service|pekerjaan|job|order|tiket)\b',low))
        customers_word=bool(re.search(r'\b(pelanggan|customer|klien)\b',low))
        finance_word=bool(re.search(r'\b(keuangan|pemasukan|pengeluaran|arus kas|saldo)\b',low)) or low in {'/keuangan','/finance'}
        docs_word=bool(re.search(r'\b(invoice|penawaran|quotation|kwitansi)\b',low))
        # For a photo query, photo of a repair ticket is always intended.
        if not (wants_photo or jobs_word or customers_word or finance_word or docs_word):
            return None
        # Standalone vague mentions should still go through ordinary AI chat.
        if not (wants_photo or low.startswith('/') or re.search(r'\b(berapa|jumlah|daftar|list|lihat|cek|cari|carikan|status|detail|siapa|bagaimana|kondisi|apa\s+saja|tampilkan|tunjukkan|rekap|laporan|kirim|ada|minta)\b',low)):
            return None
        try:
            if wants_photo:
                return self._photo_answer(text)
            if customers_word:
                return self._customers_answer(text)
            if jobs_word:
                return self._jobs_answer(text)
            if finance_word:
                return self._finance_answer(low)
            if docs_word:
                return self._documents_answer()
        except (httpx.HTTPError,ValueError,ConnectionError,OSError):
            LOG.warning('Dashboard query failed (request details redacted)')
            return BusinessAnswer('⚠️ Data dashboard belum dapat dibaca saat ini. Periksa service tosbot-dashboard dan koneksi integrasi; saya tidak akan menebak angka atau status.')
        return None

    def _customers_answer(self,text):
        low=text.casefold()
        result=self.get('summary')
        count=result['customers']
        if re.search(r'\b(berapa|jumlah|total|ada berapa)\b',low):
            return BusinessAnswer(f'👥 Pelanggan aktif di dashboard: {count} perusahaan.\nSumber: Database Dashboard TosBot (langsung).')
        q=self.clean_query(text)
        rows=self.get('customers',{'q':q,'limit':20})['results']
        if not rows:
            return BusinessAnswer(f'Tidak ada pelanggan dashboard yang cocok dengan "{q}".')
        lines=[f'👥 Pelanggan dashboard ({count} total; {len(rows)} ditampilkan):']
        lines.extend(f"#{x['id']} {x['name']} — PIC: {x.get('pic') or '-'}" for x in rows)
        return BusinessAnswer('\n'.join(lines))

    def _jobs_answer(self,text):
        low=text.casefold()
        jid=self.extract_job_id(text)
        if jid:
            try:job=self.get(f'jobs/{jid}')
            except httpx.HTTPStatusError as err:
                if err.response.status_code==404:
                    return BusinessAnswer(f'Tiket pekerjaan #{jid} tidak ditemukan di dashboard.')
                raise
            return BusinessAnswer('🔧 Detail pekerjaan servis dari dashboard:\n'+self.fmt_job(job)+
                f"\n   Jadwal: {job.get('scheduled_date') or '-'} | Estimasi: {self.rupiah(job.get('estimate'))}")
        summary=self.get('summary')
        if re.search(r'\b(berapa|jumlah|total|ada berapa)\b',low):
            return BusinessAnswer(f"🔧 Pekerjaan servis di dashboard:\nTotal: {summary['jobs']}\nBerjalan: {summary['active_jobs']}\nSelesai: {summary['completed_jobs']}\nSumber: Dashboard TosBot (langsung).")
        q=self.clean_query(text)
        rows=self.get('jobs',{'q':q,'limit':15})['results']
        if not rows:return BusinessAnswer(f'Tidak ditemukan pekerjaan servis yang cocok dengan "{q}" di dashboard.')
        return BusinessAnswer('🔧 Pekerjaan servis:\n'+'\n'.join(self.fmt_job(x) for x in rows[:12])+'\nUntuk detail: status servis #nomor.')

    def _photo_answer(self,text):
        jid=self.extract_job_id(text)
        if jid is not None:
            try:job=self.get(f'jobs/{jid}')
            except httpx.HTTPStatusError as err:
                if err.response.status_code==404:
                    return BusinessAnswer(f'Pekerjaan #{jid} tidak ditemukan.')
                raise
        else:
            q=self.clean_query(text)
            rows=self.get('jobs',{'q':q,'limit':15})['results']
            if not rows:return BusinessAnswer('Belum ditemukan pekerjaan yang sesuai. Cari dengan "foto servis #2" atau sebutkan nama pelanggan/mesin.')
            if len(rows)>1:
                lines=['Ada beberapa pekerjaan yang cocok. Pilih ID agar foto tidak tertukar:']
                lines.extend(f"#{j['id']} — {j['customer']} / {j['machine']} ({j['photo_count']} foto)" for j in rows[:10])
                return BusinessAnswer('\n'.join(lines)+'\nContoh: foto servis #2')
            job=rows[0]
            jid=job['id']
        photos=self.get('photos',{'job_id':jid})['photos']
        if not photos:
            return BusinessAnswer(f"📷 Belum ada foto yang diunggah untuk pekerjaan #{jid} ({job['customer']} — {job['machine']}). Silakan unggah lewat dashboard > Pekerjaan servis > Foto barang.")
        # Max 3 images per request to avoid flooding Telegram.
        selected=photos[:3]
        return BusinessAnswer(f"📷 Foto pekerjaan #{jid}: {job['customer']} — {job['machine']}\nMengirim {len(selected)} dari {len(photos)} foto tersimpan.",
            tuple((int(p['id']),f"Servis #{jid} — {job['machine']}: {p.get('caption') or 'Foto barang'}") for p in selected))

    def _finance_answer(self,low):
        scope='today' if re.search(r'\b(hari ini|today)\b',low) else ('month' if re.search(r'\b(bulan ini|bulan sekarang)\b',low) else 'all')
        r=self.get('finance',{'scope':scope})
        name={'today':'hari ini','month':'bulan ini','all':'seluruh data yang ditampilkan di dashboard'}[scope]
        sync=r.get('snapshot') or {}
        stale='\n⚠️ Data transaksi Telegram belum disinkronkan.' if not sync.get('available') else ''
        return BusinessAnswer(f"💰 Keuangan {name}:\nPemasukan: {self.rupiah(r['income'])}\nPengeluaran: {self.rupiah(r['expense'])}\nSelisih: {self.rupiah(r['difference'])}\nJumlah transaksi: {r['count']}\nSumber: Dashboard + salinan TosBot (bukan saldo rekening)."+stale)

    def _documents_answer(self):
        r=self.get('documents')
        return BusinessAnswer(f"📄 Dokumen terdaftar di dashboard: {r['count']}\nPenawaran: {r['offers']}\nInvoice: {r['invoices']}\nSumber: Dashboard + salinan TosBot.")
