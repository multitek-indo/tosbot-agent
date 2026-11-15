"""Offline tests for strict mention-gated group access and privilege isolation."""
from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tosbot_ai.bot import process_update, _group_addressed
from tosbot_ai.config import Settings
from tosbot_ai.group import GroupAssistant, GROUP_HELP
from tosbot_ai.storage import Store

BOT='tosbot_example'
BOT_ID=777888999


def message(text, chat=-100123456789, uid=222, typ='supergroup', message_id=5, **overrides):
    msg={
        'chat':{'id':chat,'type':typ}, 'from':{'id':uid,'is_bot':False},
        'text':text, 'message_id':message_id,
    }
    msg.update(overrides)
    return {'message':msg}

class GroupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{
            'TELEGRAM_OWNER_ID':'111',
            'TELEGRAM_GROUPS_ENABLED':'true',
            'TELEGRAM_ALLOWED_GROUP_IDS':'-100123456789',
            'TOSBOT_DB_PATH':str(root/'db.sqlite3'),
        })
        self.env.start()
        self.s=Settings.load()
        self.store=Store(self.s.db_path)
        self.mock_ai=Mock()
        self.mock_ai.converse_group.return_value='Jawaban aman.'
        self.group=GroupAssistant(self.s,self.store,ai=self.mock_ai)
        self.telegram=Mock()
        self.private_engine=Mock()
        self.terminal=Mock()
        self.terminal.handle.return_value=None

    def tearDown(self):
        self.store.db.close()
        self.env.stop()
        self.tmp.cleanup()

    def dispatch(self, msg):
        process_update(msg,self.telegram,self.private_engine,self.s,self.terminal,
                       self.group,BOT,bot_user_id=BOT_ID)

    def test_only_explicit_mention_triggers(self):
        self.dispatch(message('Halo semua'))
        self.dispatch(message('halo',reply_to_message={'from':{'id':123,'is_bot':True}}))
        self.dispatch(message('/help'))
        self.dispatch(message('halo @bot_lain'))
        self.dispatch(message('email@tosbot_example.com bukan mention'))
        self.telegram.say.assert_not_called()
        self.private_engine.handle.assert_not_called()
        self.terminal.handle.assert_not_called()
        self.dispatch(message('halo @TOSBOT_EXAMPLE'))
        self.telegram.say.assert_called_once()
        args,kwargs=self.telegram.say.call_args
        self.assertEqual(args[0],-100123456789)
        self.assertEqual(kwargs['reply_to_message_id'],5)
        self.assertIn('Halo!',args[1])

    def test_reply_to_our_bot_counts_as_explicit_address(self):
        reply={'from':{'id':BOT_ID,'is_bot':True},
               'chat':{'id':-100123456789,'type':'supergroup'},
               'message_id':4,'text':'Rancangan PENAWARAN'}
        self.dispatch(message('sudah sesuai',reply_to_message=reply))
        self.telegram.say.assert_called_once()
        self.assertEqual(self.telegram.say.call_args.kwargs['reply_to_message_id'],5)
        self.assertIn('Jawaban aman.',self.telegram.say.call_args.args[1])
        self.mock_ai.converse_group.assert_called_once()
        self.assertEqual(self.mock_ai.converse_group.call_args.args[0],'sudah sesuai')

    def test_reply_to_someone_else_or_fake_bot_stays_silent(self):
        group=-100123456789
        for sender in (
            {'id':1234,'is_bot':False},
            {'id':1234,'is_bot':True},
            {'id':BOT_ID,'is_bot':False},
        ):
            self.dispatch(message('halo',reply_to_message={
                'from':sender,'chat':{'id':group},'message_id':4}))
        self.dispatch(message('halo',reply_to_message={
            'from':{'id':BOT_ID,'is_bot':True},
            'chat':{'id':-100222222},'message_id':4}))
        self.dispatch(message('halo',reply_to_message={
            'from':{'id':BOT_ID,'is_bot':True},'message_id':4}))
        self.dispatch(message('halo',reply_to_message={
            'from':{'id':BOT_ID,'is_bot':True},
            'chat':{'id':group},'message_thread_id':123},
            message_thread_id=456))
        self.telegram.say.assert_not_called()

    def test_reply_to_bot_in_other_group_stays_silent(self):
        self.dispatch(message('halo',chat=-100555,reply_to_message={
            'from':{'id':BOT_ID,'is_bot':True},'chat':{'id':-100555}}))
        self.telegram.say.assert_not_called()

    def test_any_user_without_individual_id_authorization(self):
        for user in (222,333,444):
            self.dispatch(message(f'@{BOT} halo',uid=user))
        self.assertEqual(self.telegram.say.call_count,3)
        self.private_engine.handle.assert_not_called()

    def test_owner_private_still_uses_engine(self):
        self.private_engine.handle.return_value=('private ok',None)
        self.dispatch(message('halo',chat=111,uid=111,typ='private'))
        self.private_engine.handle.assert_called_once_with('halo')
        self.terminal.handle.assert_called_once_with('halo')

    def test_unauthorized_private_user_silenced(self):
        self.dispatch(message('@'+BOT+' halo',chat=222,uid=222,typ='private'))
        self.telegram.say.assert_not_called()
        self.private_engine.handle.assert_not_called()

    def test_group_admin_tools_blocked_even_for_owner(self):
        commands=[
            f'@{BOT} /sudo whoami',
            f'@{BOT} /sh ls -lah',
            f'@{BOT} apt upgrade',
            f'@{BOT} buat invoice untuk PT XYZ',
            f'@{BOT} catat pengeluaran 200000',
            f'@{BOT} buat folder test',
            f'@{BOT} /auth 123456',
            f'@{BOT} cek direktori /etc',
        ]
        for i,raw in enumerate(commands):
            self.dispatch(message(raw,uid=111+i))
            self.assertIn('⛔',self.telegram.say.call_args.args[1],raw)
        self.assertEqual(self.telegram.say.call_count,len(commands))
        self.private_engine.handle.assert_not_called()
        self.terminal.handle.assert_not_called()
        self.mock_ai.converse_group.assert_not_called()

    def test_other_groups_denied(self):
        self.dispatch(message(f'@{BOT} halo',chat=-100999))
        self.telegram.say.assert_not_called()

    def test_group_disabled_by_default(self):
        with patch.dict(os.environ,{'TELEGRAM_GROUPS_ENABLED':'false'}):
            s=Settings.load()
        process_update(message(f'@{BOT} halo'),self.telegram,self.private_engine,s,
                       self.terminal,self.group,BOT)
        self.telegram.say.assert_not_called()

    def test_group_memory_separate_users_topics_and_private(self):
        self.dispatch(message(f'@{BOT} jelaskan Linux',message_thread_id=42))
        self.dispatch(message(f'@{BOT} jelaskan server',message_thread_id=42))
        self.dispatch(message(f'@{BOT} jelaskan jaringan',uid=333,message_thread_id=42))
        self.dispatch(message(f'@{BOT} jelaskan jaringan',uid=222,message_thread_id=43))
        self.assertEqual(len(self.mock_ai.converse_group.call_args_list),4)
        self.assertEqual(len(self.mock_ai.converse_group.call_args_list[0].args[1]),0)
        self.assertEqual(len(self.mock_ai.converse_group.call_args_list[1].args[1]),2)
        self.assertEqual(len(self.mock_ai.converse_group.call_args_list[2].args[1]),0)
        self.assertEqual(len(self.mock_ai.converse_group.call_args_list[3].args[1]),0)
        self.assertIsNone(self.store.get_kv('history'))
        self.assertEqual(self.telegram.say.call_args.kwargs['message_thread_id'],43)

    def test_help_and_public_metrics_no_ai(self):
        self.dispatch(message(f'@{BOT} /help@{BOT}'))
        self.assertIn('Terminal',self.telegram.say.call_args.args[1])
        self.dispatch(message(f'@{BOT} cek RAM'))
        self.assertIn('RAM VPS',self.telegram.say.call_args.args[1])
        self.dispatch(message(f'@{BOT} cek disk'))
        self.assertIn('Penyimpanan VPS',self.telegram.say.call_args.args[1])
        self.dispatch(message(f'@{BOT} cek status VPS'))
        self.assertIn('Server:',self.telegram.say.call_args.args[1])
        self.mock_ai.converse_group.assert_not_called()

    def test_sender_chat_and_bot_cannot_invoke(self):
        self.dispatch(message(f'@{BOT} halo',sender_chat={'id':-100123456789}))
        self.dispatch(message(f'@{BOT} halo',**{'from':{'id':222,'is_bot':True}}))
        self.telegram.say.assert_not_called()

    def test_mention_with_unicode_and_command_only_to_target(self):
        self.assertEqual(_group_addressed('🐈 /help@TOSBOT_EXAMPLE',[],BOT),(True,'🐈 /help'))
        self.assertEqual(_group_addressed('/help@other_bot',[],BOT)[0],False)
        self.assertEqual(_group_addressed('Halo @tosbot_example2',[],BOT)[0],False)
        self.assertEqual(_group_addressed('tolong @tosbot_example cek RAM',[],BOT),(True,'tolong cek RAM'))

if __name__=='__main__': unittest.main()
