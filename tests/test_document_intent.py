import unittest
from tosbot_ai.document_intent import (is_new_document_request, single_quantity,
    customer_address, requested_item_note, improve_document_nlu, scrub_address_from_items)

ADDR = ('Jl. Raya Mayjen Sungkono, Dusun 1, Kalimanah Wetan, Kec. Kalimanah, '
        'Kabupaten Purbalingga, Jawa Tengah 53371')
FULL = ('buatkan penawaran kepada pak Aming PT Serasi Gaya Busana alamat '
        + ADDR + '. dengan rincian biaya service 1 unit control box Jack '
        'harga 2 juta.kasih keterangan selesai service.')

class DocumentIntentTests(unittest.TestCase):
    def test_full_new_request(self):
        self.assertTrue(is_new_document_request(FULL))
        self.assertEqual(customer_address(FULL), ADDR)
        self.assertEqual(requested_item_note(FULL), 'selesai service')

    def test_address_below_customer(self):
        msg='tambahkan alamat di bawah PT SGB.\n' + ADDR
        self.assertEqual(customer_address(msg), ADDR)
        self.assertFalse(is_new_document_request(msg))

    def test_plus_code(self):
        msg='alamat H8QV+MHJ, '+ ADDR +' 1unit control box Jack harga 2 juta'
        self.assertEqual(customer_address(msg), 'H8QV+MHJ, '+ADDR)

    def test_short_quantity_and_typo(self):
        for msg in ('1 unit', '1 unut', '1 unot', '1 pcs'):
            self.assertEqual(single_quantity(msg),1)
        self.assertIsNone(single_quantity('Harga 1 unit 2 juta'))
        self.assertIsNone(single_quantity('PK LK-1900B'))
        self.assertIsNone(single_quantity('2 juta'))
        self.assertEqual(single_quantity('1',allow_bare=True),1)

    def test_address_only_patch_does_not_add_second_item(self):
        old={'items':[{'name':'service control box Jack','qty':1,'price':2000000,'unit':'UNIT','note':''}]}
        bad_nlu={'action':'document_update','data':{'patch':{'items':[{'note':ADDR}]}}}
        result=improve_document_nlu('tambahkan alamat di bawah PT SGB. '+ADDR,bad_nlu,old)
        patch=result['data']['patch']
        self.assertEqual(patch['customer_address'],ADDR)
        self.assertNotIn('items',patch)
        self.assertNotIn('item_changes',patch)

    def test_new_request_enrich_item_and_note_without_fabrication(self):
        parsed={'action':'document_create','data':{'doc_type':'offer','customer':'PT Serasi Gaya Busana',
               'attention':'Pak Aming','items':[{'name':'control box Jack','qty':1,
               'price':2000000,'note':ADDR}]}}
        result=improve_document_nlu(FULL,parsed,None)['data']
        self.assertEqual(result['customer_address'],ADDR)
        self.assertEqual(len(result['items']),1)
        self.assertEqual(result['items'][0]['name'],'service control box Jack')
        self.assertEqual(result['items'][0]['note'],'selesai service')

    def test_note_only_single_existing_item(self):
        old={'items':[{'name':'service control box Jack','qty':1,'price':2000000}]}
        nlu={'action':'document_update','data':{'patch':{'items':[{'note':'selesai service'}]}}}
        patch=improve_document_nlu('kasih keterangan selesai service',nlu,old)['data']['patch']
        self.assertNotIn('items',patch)
        self.assertEqual(patch['item_changes'],{'note':'selesai service'})
        self.assertEqual(patch['target_index'],1)

    def test_no_plus_address_without_explicit_address_instruction(self):
        self.assertIsNone(customer_address('Kantor saya di '+ADDR))
        self.assertIsNone(requested_item_note('alamat '+ADDR))

    def test_scrub_only_address_note(self):
        items=[{'note':'Alamat: '+ADDR},{'note':'selesai service'}]
        scrub_address_from_items(items,ADDR)
        self.assertEqual(items[0]['note'],'')
        self.assertEqual(items[1]['note'],'selesai service')

if __name__=='__main__':
    unittest.main()

# Extra regressions based on the November 19 Telegram conversation.
class ConversationRegressionTests(unittest.TestCase):
    def test_complete_offer_without_ai(self):
        from tosbot_ai.document_intent import fallback_simple_document
        doc = fallback_simple_document('@mustikasaribot ' + FULL)
        self.assertIsNotNone(doc)
        self.assertEqual(doc['action'], 'document_create')
        data = doc['data']
        self.assertEqual(data['customer'], 'PT Serasi Gaya Busana')
        self.assertEqual(data['attention'], 'Pak Aming')
        self.assertEqual(data['customer_address'], ADDR)
        self.assertEqual(data['items'], [dict(name='service control box Jack', qty=1,
                                              unit='UNIT', price=2000000,
                                              note='selesai service')])
        self.assertNotIn('terms',data)

    def test_address_first_then_instruction(self):
        text = 'H8QV+MHJ, ' + ADDR + ' tambahkan alamat ini'
        self.assertEqual(customer_address(text), 'H8QV+MHJ, '+ ADDR)

    def test_fallback_one_item_only(self):
        from tosbot_ai.document_intent import fallback_simple_document
        msg = ('buatkan penawaran untuk PT SGB kepada pak Aming 1unit control box Jack harga 2 juta')
        data=fallback_simple_document(msg)['data']
        self.assertEqual(data['items'][0]['qty'] * data['items'][0]['price'], 2000000)
        self.assertNotIn('customer_address',data)
        self.assertIsNone(fallback_simple_document(msg+' dan 1 unit PLC harga 1 juta'))

    def test_amounts_and_mentions(self):
        from tosbot_ai.document_intent import fallback_simple_document, single_price_reply
        self.assertTrue(is_new_document_request('@mustikasaribot ' + FULL))
        self.assertEqual(single_price_reply('Harga 1 unit 2juta'), 2000000)
        self.assertEqual(single_price_reply('harga 1,5 juta'), 1500000)
        self.assertEqual(single_price_reply('harga Rp2.000.000'), 2000000)
        self.assertIsNotNone(fallback_simple_document(FULL))

    def test_no_address_becomes_item_note(self):
        from tosbot_ai.document_intent import fallback_simple_document
        msg = ('buatkan penawaran untuk PT SGB kepada pak Aming alamat H8QV+MHJ, '
               + ADDR + ' 1unit control box Jack harga 2 juta')
        doc=fallback_simple_document(msg)['data']
        self.assertEqual(doc['customer_address'], 'H8QV+MHJ, '+ ADDR)
        self.assertNotIn('note', doc['items'][0])

