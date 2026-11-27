import os
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tosbot_ai.config import Settings
from tosbot_ai.engine import Engine
from tosbot_ai.storage import Store
from tosbot_ai.document_intent import fallback_simple_document, improve_document_nlu, invoice_header_patch

ADDR = ('Jl. Contoh KM 1, Dsn. Fiktif RT 001/RW 001, '
        'Ds. Contoh, Kec. Contoh, Kab. Contoh, Jawa Tengah 50000')
PO = 'PO-TEST-001'
MESSAGES = [f'buatkan invoice untuk Mr Alex PT Contoh Abadi alamat {ADDR}. 1unit mesin JUKI DDL-9000C seharga 1.150.000 dengan nomor PO {PO}',
            f'buatkan invoice kepad Mr.Alex di PT Contoh Abadi alamat {ADDR}. 1unit mesin JUKI DDL-9000C seharga 1.150.000 dengan nomor PO customer {PO}']

class InvoicePOTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'TOSBOT_DB_PATH':str(root/'db.sqlite3'), 'TOSBOT_OUTPUT_DIR':str(root/'pdf'), 'TELEGRAM_OWNER_ID':'123456', 'TOSBOT_LOGO_PATH':str(root/'missing.png')})
        self.env.start()
        self.cfg = Settings.load()
        self.db = Store(self.cfg.db_path)
        self.engine = Engine(self.cfg, self.db)
        self.engine.flow = None
    def tearDown(self):
        self.db.db.close()
        self.env.stop()
        self.tmp.cleanup()
    def test_actual_messages_and_wrong_model(self):
        for message in MESSAGES:
            bad = {'action':'document_create','data':{'doc_type':'invoice','customer':'Mr.Alex','number':PO,'items':[{'name':'mesin JUKI DDL-9000C','qty':1,'price':1150000}]}}
            fixed = improve_document_nlu(message,deepcopy(bad),None)['data']
            self.assertEqual(fixed['customer'],'PT Contoh Abadi')
            self.assertEqual(fixed['attention'],'Mr. Alex')
            self.assertEqual(fixed['po_number'],PO)
            self.assertNotIn('number',fixed)
            with patch.object(self.engine.ai,'understand',return_value=bad):
                preview, pdf = self.engine.handle(message)
            self.assertIsNone(pdf)
            self.assertIn('PO Customer: '+PO,preview)
            self.assertIn('Nomor invoice: [otomatis setelah final]',preview)
            self.assertIn('TOTAL: Rp1.150.000',preview)
            self.assertEqual(self.db.get_draft(self.cfg.owner_id)['customer_address'],ADDR)
    def test_model_error_fallback(self):
        for message in MESSAGES:
            data = fallback_simple_document(message)['data']
            self.assertEqual(data['attention'],'Mr. Alex')
            self.assertEqual(data['po_number'],PO)
            with patch.object(self.engine.ai,'understand',side_effect=RuntimeError('offline')):
                preview,_ = self.engine.handle(message)
            self.assertIn('PO Customer: '+PO,preview)
    def test_po_correction_and_final_pdf(self):
        self.engine._create_draft({'doc_type':'invoice','customer':'PT Contoh Abadi','attention':'Mr. Alex','number':PO,'items':[{'name':'mesin JUKI DDL-9000C','qty':1,'price':1150000}]})
        with patch.object(self.engine.ai,'understand',side_effect=AssertionError('must not use model')):
            preview,_ = self.engine.handle('koreksi nomor PO customer '+PO)
        self.assertIn('Nomor invoice: [otomatis setelah final]',preview)
        self.assertIn('PO Customer: '+PO,preview)
        answer,pdf = self.engine.handle('sudah sesuai')
        self.assertIsNotNone(pdf,answer)
        self.assertTrue(pdf.is_file())
        self.assertIn('INV/',answer)
        self.assertNotIn(PO,answer)
        # Repeat PO is allowed; invoice numbers remain distinct.
        self.engine._create_draft(fallback_simple_document(MESSAGES[0])['data'])
        answer2,pdf2 = self.engine.handle('sudah sesuai')
        self.assertIsNotNone(pdf2,answer2)
        self.assertNotEqual(answer,answer2)
    def test_preserve_existing_invoice_number_and_other_fields(self):
        self.engine._create_draft({'doc_type':'invoice','customer':'PT Contoh Abadi','number':'INV/2026/0099','items':[{'name':'mesin','qty':1,'price':1150000}]})
        self.engine.handle('no. PO: '+PO)
        draft = self.db.get_draft(self.cfg.owner_id)
        self.assertEqual(draft['number'],'INV/2026/0099')
        self.assertEqual(draft['po_number'],PO)
        self.assertEqual(draft['items'][0]['price'],1150000)
        self.engine.handle('nomor invoice otomatis')
        self.assertEqual(self.db.get_draft(self.cfg.owner_id)['number'],'')
    def test_explicit_numbers_and_date(self):
        self.assertEqual(invoice_header_patch('nomor invoice INV/2026/0999 dan PO customer '+PO),{'number':'INV/2026/0999','po_number':PO})
        self.assertEqual(invoice_header_patch('tanggal PO 27/11/2026'),{})
        self.assertEqual(invoice_header_patch('PO: 001234'),{'po_number':'001234'})
    def test_unrequested_model_number_dropped_on_update(self):
        old={'type':'invoice','number':'INV/2026/0001','po_number':PO}
        parsed={'action':'document_update','data':{'patch':{'attention':'Mr. Alex','number':PO,'po_number':'fake123'}}}
        fixed=improve_document_nlu('PIC Mr. Alex',parsed,old)['data']['patch']
        self.assertEqual(fixed,{'attention':'Mr. Alex'})
