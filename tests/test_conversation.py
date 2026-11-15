"""Regression tests for natural dialogue, missing quantities and original document assets."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tosbot_ai.config import Settings
from tosbot_ai.engine import Engine
from tosbot_ai.storage import Store
from fixtures import create_test_assets

class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        fake_logo, fake_signature=create_test_assets(self.tmp.name)
        overrides={
            'TELEGRAM_BOT_TOKEN':'test', 'TELEGRAM_OWNER_ID':'123456',
            'GROQ_API_KEY':'test', 'AI_PRIMARY':'groq',
            'TOSBOT_DB_PATH':str(Path(self.tmp.name)/'test.sqlite'),
            'TOSBOT_OUTPUT_DIR':str(Path(self.tmp.name)/'out'),
            'COMPANY_ACCOUNT':'0000000000',
            'COMPANY_NAME':'Perusahaan Uji',
            'TOSBOT_LOGO_PATH':str(fake_logo),
            'TOSBOT_OFFER_SIGNATURE_PATH':str(fake_signature),
        }
        self.env=patch.dict(os.environ,overrides)
        self.env.start()
        self.settings=Settings.load()
        self.store=Store(self.settings.db_path)
        self.engine=Engine(self.settings,self.store)
        # Network AI is never invoked in tests.
        self.engine.flow=None

    def tearDown(self):
        self.store.db.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_separate_pic_from_item_note_and_no_guessed_qty(self):
        self.engine._create_draft({'doc_type':'offer','customer':'PT CONTOH'})
        text='nama barangnya service JK-1900A harga satuan 1,5jt PIC bu Nurul'
        parsed={'action':'document_update','data':{'patch':{'items':[
            {'name':'service JK-1900A','qty':1,'price':1500000,'note':'PIC bu Nurul'}]}}}
        corrected=self.engine._fix_recipient(text,parsed,self.store.get_draft(self.settings.owner_id))
        self.assertEqual(corrected['data']['patch']['attention'],'bu Nurul')
        self.assertNotIn('qty',corrected['data']['patch']['items'][0])
        self.assertEqual(corrected['data']['patch']['items'][0]['note'],'')
        out=self.engine._patch_draft(corrected['data']['patch'])
        self.assertIn('Berapa unit',out)
        draft=self.store.get_draft(self.settings.owner_id)
        self.assertEqual(draft['attention'],'bu Nurul')
        self.assertFalse(draft['items'])
        self.assertEqual(draft['pending_item']['price'],1500000)
        # The next Telegram reply only contains the pending quantity.
        response=self.engine._patch_draft({'items':[{'qty':1}]})
        self.assertIn('TOTAL: Rp1.500.000',response)
        self.assertNotIn('pending_item',self.store.get_draft(self.settings.owner_id))
        self.assertIn('Garansi 1 bulan',response)

    def test_invoice_no_handwritten_signature_offer_has_signature(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('PyMuPDF optional visual-verification dependency is not installed')
        from tosbot_ai.documents import make_pdf
        from datetime import datetime
        offer={'type':'offer','customer':'PT ABC',
               'items':[{'name':'Service mesin','qty':1,'unit':'UNIT','price':500000,'note':''}]}
        invoice={'type':'invoice','customer':'PT ABC',
                 'items':[{'name':'Service mesin','qty':1,'unit':'UNIT','price':500000,'note':''}]}
        for kind, payload, image_count in [('offer',offer,2),('invoice',invoice,1)]:
            path=Path(self.tmp.name)/f'{kind}.pdf'
            make_pdf(payload,'INV-TEST',path,self.settings,datetime.now(self.settings.tz))
            doc=fitz.open(path)
            self.assertEqual(len(doc[0].get_images(full=True)),image_count)
            contents=doc[0].get_text()
            self.assertIn('Perusahaan Uji',contents)
            if kind=='offer':
                self.assertIn('Workshop',contents)
                self.assertIn('DISCOUNT',contents)
            else:
                self.assertIn('Nomor rekening',contents)
                self.assertIn('Telp/Whatsapp',contents)

    def test_quantity_guard_accepts_explicit_unit(self):
        text='2 unit service JK-1900A harga 1,5jt'
        parsed={'action':'document_create','data':{'doc_type':'offer','items':[{'name':'service JK-1900A','qty':2,'price':1500000}]}}
        self.engine._fix_recipient(text,parsed,None)
        self.assertEqual(parsed['data']['items'][0]['qty'],2)

if __name__=='__main__':unittest.main()
