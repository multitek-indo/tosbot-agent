import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from tosbot_ai.config import Settings
from tosbot_ai.engine import Engine
from tosbot_ai.storage import Store
from tosbot_ai.document_memory import reuse_request, normalize_create

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'TOSBOT_DB_PATH':str(root/'db.sqlite3'),'TOSBOT_OUTPUT_DIR':str(root/'pdf'),'TELEGRAM_OWNER_ID':'123456','TOSBOT_LOGO_PATH':str(root/'missing.png')})
        self.env.start()
        self.cfg=Settings.load()
        self.db=Store(self.cfg.db_path)
        self.engine=self.make_engine(self.cfg)
    def make_engine(self,cfg):
        e=Engine(cfg,self.db)
        if e.flow: e.flow.close()
        e.flow=None
        return e
    def tearDown(self):
        self.db.db.close();self.env.stop();self.tmp.cleanup()
    def issue(self,customer='PT Contoh',items=None):
        self.engine._create_draft({'doc_type':'invoice','customer':customer,'attention':'Mr. Alex','customer_address':'Jl. Contoh 10','po_number':'PO-OLD-01','po_date':'01/01/2026','discount':10,'items':items or [{'name':'Mesin A','qty':1,'price':100000,'note':'Pekerjaan lama'}]})
        answer,pdf=self.engine.handle('sudah sesuai')
        self.assertIsNotNone(pdf,answer)
    def test_reuse_after_restart(self):
        self.issue();self.db.db.close();self.db=Store(self.cfg.db_path);self.engine=self.make_engine(self.cfg)
        with patch.object(self.engine.ai,'understand',side_effect=AssertionError('no LLM')):
            answer,pdf=self.engine.handle('Buatkan invoice untuk Pak Alex seperti kemarin, barangnya sama tapi jumlahnya 3 unit, PO baru PO-NEW-02')
        self.assertIsNone(pdf);self.assertIn('Rp300.000',answer)
        d=self.db.get_draft(self.cfg.owner_id)
        self.assertEqual(d['customer'],'PT Contoh');self.assertEqual(d['attention'],'Mr. Alex');self.assertEqual(d['customer_address'],'Jl. Contoh 10')
        self.assertEqual(d['po_number'],'PO-NEW-02');self.assertEqual(d['number'],'');self.assertFalse(d.get('po_date'));self.assertEqual(d['discount'],0);self.assertEqual(d['items'][0]['note'],'')
        self.assertIsNotNone(self.engine.handle('sudah sesuai')[1]);self.assertIsNone(self.engine.handle('sudah sesuai')[1]);self.assertEqual(len(self.db.recall_documents(self.cfg.owner_id,'invoice')),2)
    def test_scope_and_kind(self):
        self.issue()
        other=self.make_engine(replace(self.cfg,owner_id=-123))
        self.assertIn('Belum ada',other.handle('buat invoice terakhir')[0]);self.assertIsNone(self.db.get_draft(-123))
        self.assertIn('Belum ada',self.engine.handle('buat penawaran terakhir')[0])
    def test_ambiguous_pic_and_unknown(self):
        self.issue();self.issue('PT Lain')
        self.assertIn('beberapa pelanggan',self.engine.handle('buat invoice untuk Alex seperti kemarin')[0]);self.assertIsNone(self.db.get_draft(self.cfg.owner_id))
        self.assertIn('Belum ada',self.engine.handle('buat invoice untuk PT Tidak Ada seperti kemarin')[0])
        self.assertIn('PT Contoh',self.engine.handle('buat invoice untuk PT Contoh seperti kemarin')[0])
    def test_active_draft_preserved(self):
        self.issue();self.engine._create_draft({'doc_type':'invoice','customer':'PT Baru'})
        self.assertIn('draft aktif',self.engine.handle('buat invoice terakhir')[0]);self.assertEqual(self.db.get_draft(self.cfg.owner_id)['customer'],'PT Baru')
    def test_multi_items_and_unknown_edits(self):
        self.issue(items=[{'name':'A','qty':1,'price':100},{'name':'B','qty':1,'price':200}])
        self.assertIn('beberapa item',self.engine.handle('buat invoice terakhir, jumlah 3 unit')[0]);self.assertIsNone(self.db.get_draft(self.cfg.owner_id))
        self.assertIn('belum jelas',self.engine.handle('buat invoice terakhir, alamat baru Jl X')[0]);self.assertIsNone(self.db.get_draft(self.cfg.owner_id))
    def test_supported_indonesian_javanese_and_typo(self):
        self.assertEqual(normalize_create('gawekno invoce kanggo PT Contoh'),'buatkan invoice kanggo PT Contoh')
        self.assertEqual(normalize_create('bash buat invoice'),'bash buat invoice')
        self.assertEqual(reuse_request('gawekno invoice koyo wingi')['kind'],'invoice')
        self.assertIsNone(reuse_request('cek invoice terakhir'))
    def test_reuse_without_old_po(self):
        self.issue();self.engine.handle('buat invoice terakhir')
        self.assertEqual(self.db.get_draft(self.cfg.owner_id)['po_number'],'')
