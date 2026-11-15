"""Offline tests. No API keys or Telegram token needed."""
import os
import tempfile
import unittest
from datetime import datetime,timedelta
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, MagicMock
from tosbot_ai.ai import extract_json, AI
from tosbot_ai.config import Settings
from tosbot_ai.documents import make_pdf,total,currency,valid_item
from tosbot_ai.engine import Engine
from tosbot_ai.server import disk,memory,validate_service
from tosbot_ai.storage import Store
from fixtures import create_test_assets

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        fake_logo, fake_signature=create_test_assets(root)
        env={
            'TOSBOT_DB_PATH':str(root/'data/db.sqlite3'),
            'TOSBOT_OUTPUT_DIR':str(root/'docs'),
            'TELEGRAM_OWNER_ID':'123456789',
            'ADMIN_ALLOWED_SERVICES':'nginx,cloudflared',
            'TOSBOT_LOGO_PATH':str(fake_logo),
            'TOSBOT_OFFER_SIGNATURE_PATH':str(fake_signature),
        }
        self.patcher=patch.dict(os.environ,env)
        self.patcher.start()
        self.cfg=Settings.load()
        self.db=Store(self.cfg.db_path)
        self.engine=Engine(self.cfg,self.db)

    def tearDown(self):
        self.db.db.close()
        self.patcher.stop()
        self.tmp.cleanup()

    def test_primary_groq_and_gemini_fallback(self):
        config=replace(self.cfg,groq_key='groq-test',gemini_key='gemini-test',ai_primary='groq')
        ai=AI(config)
        self.assertEqual([p[0] for p in ai._providers()], ['groq','gemini'])

        def run_fake(responses, expect_action=False):
            fake=MagicMock()
            fake.__enter__.return_value=fake
            fake.post.side_effect=responses
            with patch('tosbot_ai.ai.httpx.Client',return_value=fake):
                output=ai._complete([{'role':'user','content':'hello'}],expect_action=expect_action)
            return output,fake.post.call_args_list

        def answer(content):
            response=MagicMock()
            response.json.return_value={'choices':[{'message':{'content':content}}]}
            return response

        output,calls=run_fake([answer('Groq OK')])
        self.assertEqual(output,'Groq OK')
        self.assertEqual(len(calls),1)
        self.assertIn('api.groq.com',calls[0].args[0])
        self.assertEqual(calls[0].kwargs['json']['model'],'openai/gpt-oss-120b')

        output,calls=run_fake([__import__('httpx').RequestError('network down'),answer('Gemini fallback')])
        self.assertEqual(output,'Gemini fallback')
        self.assertEqual(len(calls),2)
        self.assertIn('generativelanguage.googleapis.com',calls[1].args[0])

        output,calls=run_fake([answer('invalid-json'),answer('{"action":"server_disk","data":{}}')],expect_action=True)
        self.assertIn('server_disk',output)
        self.assertEqual(len(calls),2)

    def test_xai_config_not_used(self):
        with patch.dict(os.environ, {'GROQ_API_KEY':'test','GEMINI_API_KEY':'backup','AI_PRIMARY':'groq','XAI_API_KEY':'legacy'}, clear=False):
            cfg=Settings.load()
        self.assertEqual(cfg.groq_key, 'test')
        self.assertEqual(cfg.groq_model, 'openai/gpt-oss-120b')
        self.assertFalse(hasattr(cfg,'xai_key'))
        self.assertEqual([n for n, *_ in AI(cfg)._providers()], ['groq','gemini'])
        with patch.dict(os.environ, {'AI_PRIMARY':'xai', 'TELEGRAM_BOT_TOKEN':'test-token'}, clear=False):
            with self.assertRaisesRegex(ValueError,'AI_PRIMARY harus groq'):
                Settings.load().validate()

    def test_numbers_and_json(self):
        self.assertEqual(currency(1500000),'Rp1.500.000')
        self.assertEqual(extract_json('```json\n{"action":"server_disk"}\n```')['action'],'server_disk')
        self.assertEqual(total({'items':[{'qty':2,'price':1000000}],'discount':50000}),1950000)
        self.assertIsNone(valid_item({'name':'Juki LK-1900B','qty':None,'price':1300000}))

    def test_config_and_safety(self):
        self.assertEqual(validate_service(self.cfg,'nginx'),'nginx')
        self.assertIsNone(validate_service(self.cfg,'nginx;rm -rf /'))
        self.assertIsNone(validate_service(self.cfg,'ssh'))
        self.assertIn('Penyimpanan',disk())
        self.assertIn('RAM',memory())

    def test_invoice_change_only_one_field_and_confirm(self):
        result=self.engine._create_draft({'doc_type':'invoice','customer':'PT ABC',
             'items':[{'name':'Mesin Jahit','qty':2,'price':1500000,'note':'Pembelian mesin'}]})
        self.assertIn('TOTAL: Rp3.000.000',result)
        response=self.engine._patch_draft({'target_index':1,'item_changes':{'note':'Harga belum termasuk sparepart'}})
        self.assertIn('Harga belum termasuk sparepart',response)
        draft=self.db.get_draft(self.cfg.owner_id)
        self.assertEqual(draft['items'][0]['price'],1500000)
        self.assertEqual(draft['items'][0]['qty'],2)
        self.assertEqual(draft['items'][0]['note'],'Harga belum termasuk sparepart')
        self.assertEqual(draft['status'],'awaiting_confirm')
        response,path=self.engine.handle('sudah sesuai, buat pdf')
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size,2000)
        self.assertIsNone(self.db.get_draft(self.cfg.owner_id))

    def test_offer_pdf_terms_and_multiple_items(self):
        d={'type':'offer','customer':'PT ABC','attention':'Bpk. Agus',
           'items':[{'name':'Service Power PCB Juki LK-1900B','qty':1,'unit':'UNIT','price':1300000,'note':'service'},
                    {'name':'Sensor jarum','qty':3,'unit':'PCS','price':100000,'note':''}],
           'discount':50000,'terms':'a. Garansi 1 bulan\nb. Biaya sparepart terpisah'}
        pdf=Path(self.tmp.name)/'offer.pdf'
        make_pdf(d,'PEN/2026/0001',pdf,self.cfg)
        self.assertTrue(pdf.is_file())
        self.assertGreater(pdf.stat().st_size,2000)

    def test_finance_and_reminder(self):
        self.assertIn('Tercatat',self.engine._finance_add({'kind':'income','amount':100000,'category':'Servis','note':'PCB'}))
        self.assertIn('Tercatat',self.engine._finance_add({'kind':'expense','amount':20000,'category':'Ongkos','note':'Bensin'}))
        self.assertIn('Rp80.000',self.engine._finance_report({}))
        due=(datetime.now(self.cfg.tz)+timedelta(hours=3)).replace(microsecond=0)
        self.assertIn('tersimpan',self.engine._reminder_add({'title':'Telepon customer','due':due.isoformat()}))
        self.assertIn('Telepon customer',self.engine._reminder_list())

if __name__=='__main__':unittest.main()
