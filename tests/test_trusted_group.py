"""Tests that a trusted group is explicitly opted-in and isolated."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from tosbot_ai.bot import process_update
from tosbot_ai.config import Settings
from tosbot_ai.storage import Store
from tosbot_ai.terminal import TrustedGroupTerminal
from tosbot_ai.group import GroupAssistant

G=-1003733083844
USER=4321
BOT='mustikasaribot'
BOT_ID=777888999

def message(body,group=G,user=USER,**extra):
    m={'chat':{'id':group,'type':'supergroup'}, 'from':{'id':user,'is_bot':False},
       'text':body,'message_id':55}
    m.update(extra)
    return {'message':m}

class TestTrustedGroup(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'TELEGRAM_OWNER_ID':'111',
            'TELEGRAM_GROUPS_ENABLED':'true',
            'TELEGRAM_ALLOWED_GROUP_IDS':str(G),
            'TELEGRAM_TRUSTED_GROUP_ADMIN':'true',
            'TOSBOT_DB_PATH':str(Path(self.temp.name)/'test.sqlite')})
        self.env.start()
        self.s=Settings.load()
        self.db=Store(self.s.db_path)
        self.tg=Mock()
        self.owner_engine=Mock()
        self.owner_terminal=Mock()
        self.other_group=Mock()
        self.routers={}

    def tearDown(self):
        self.db.db.close()
        self.env.stop()
        self.temp.cleanup()

    def route(self,event):
        process_update(event,self.tg,self.owner_engine,self.s,self.owner_terminal,
            self.other_group,BOT,self.db,self.routers,BOT_ID)

    def test_optin_requires_group_id(self):
        with patch.dict(os.environ,{'TELEGRAM_ALLOWED_GROUP_IDS':''}):
            with self.assertRaises(ValueError):Settings.load().validate()

    def test_group_root_without_individual_auth(self):
        with patch('tosbot_ai.terminal.broker',return_value={'ok':True,'job_id':'a'*20}) as submit:
            self.route(message('@mustikasaribot /sudo whoami'))
            self.route(message('@mustikasaribot apt update',user=5555))
        self.assertEqual(submit.call_count,2)
        self.assertEqual(submit.call_args.args[0],'group-submit')
        self.assertEqual(submit.call_args.args[1]['group_id'],G)
        self.assertEqual(submit.call_args.args[1]['actor_id'],5555)
        self.assertEqual(submit.call_args.args[1]['mode'],'root')
        self.assertEqual(submit.call_args.args[1]['command'],'apt-get update')
        self.assertEqual(self.tg.say.call_count,2)
        self.owner_engine.handle.assert_not_called()

    def test_group_isolated_and_mention_required(self):
        self.route(message('/sudo whoami'))
        self.route(message('@mustikasaribot /sudo whoami',group=-100777))
        self.route(message('@mustikasaribot /sudo whoami',sender_chat={'id':G}))
        self.route(message('@mustikasaribot /sudo whoami',**{'from':{'id':100,'is_bot':True}}))
        self.tg.say.assert_not_called()

    def test_group_business_and_pdf_shared_only_in_group(self):
        with patch('tosbot_ai.bot.Engine') as engine:
            ins=engine.return_value
            ins.handle.return_value=('proposal drafted',None)
            self.route(message('@mustikasaribot buat penawaran PT ABC',user=222))
            self.route(message('@mustikasaribot revisi penawaran tadi',user=333))
        self.assertEqual(ins.handle.call_count,2)
        self.assertEqual(engine.call_args.args[0].owner_id,G)
        self.assertEqual(self.tg.say.call_count,2)
        self.owner_engine.handle.assert_not_called()

    def test_reply_to_preview_without_mention_generates_pdf(self):
        quoted={'from':{'id':BOT_ID,'is_bot':True},
                'chat':{'id':G,'type':'supergroup'},
                'message_id':54,'text':'📄 Rancangan PENAWARAN'}
        with patch('tosbot_ai.bot.Engine') as factory:
            flow=factory.return_value
            pdf=Path('/tmp/tosbot-test-reply-document.pdf')
            flow.handle.side_effect=[('Rancangan PENAWARAN',None),('PDF dibuat',pdf)]
            self.route(message('@mustikasaribot buat penawaran PT ABC',user=222))
            self.route(message('sudah sesuai',user=333,reply_to_message=quoted))
        self.assertEqual([x.args[0] for x in flow.handle.call_args_list],
                         ['buat penawaran PT ABC','sudah sesuai'])
        self.tg.file.assert_called_once_with(G,pdf)
        self.assertEqual(self.tg.say.call_count,2)

    def test_reply_to_other_bot_does_not_finalise_document(self):
        quoted={'from':{'id':123456,'is_bot':True},
                'chat':{'id':G,'type':'supergroup'},'message_id':54}
        self.route(message('sudah sesuai',reply_to_message=quoted))
        self.tg.say.assert_not_called()

    def test_terminal_command_in_reply_requires_explicit_mention(self):
        quoted={'from':{'id':BOT_ID,'is_bot':True},
                'chat':{'id':G,'type':'supergroup'},'message_id':54}
        with patch('tosbot_ai.terminal.broker') as broker:
            self.route(message('/sudo whoami',reply_to_message=quoted))
        broker.assert_not_called()
        self.assertIn('@mustikasaribot',self.tg.say.call_args.args[1])

    def test_group_cwd_and_jobs_are_isolated(self):
        first=TrustedGroupTerminal(self.s,self.db,G)
        second=TrustedGroupTerminal(self.s,self.db,-100888)
        self.assertIn('/home/tosbot', first.handle('cd /home/tosbot',USER))
        self.assertNotEqual(first._cwd(),second._cwd())
        with patch('tosbot_ai.terminal.broker',return_value={'ok':True,'job_id':'b'*20}):
            first.handle('/sudo id',USER)
        self.assertIn('Job tersebut',second.handle('/job '+'b'*20,USER))

if __name__=='__main__':unittest.main()
