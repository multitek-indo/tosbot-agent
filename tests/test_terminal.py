from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tosbot_ai.terminal import Terminal, terminal_path, literal_shell, normalize_command, safe_root_readonly

class FakeStore:
    def __init__(self): self.state={}; self.audit_entries=[]
    def get_kv(self,key,default=None): return self.state.get(key,default)
    def set_kv(self,key,val): self.state[key]=val
    def audit(self,*args): self.audit_entries.append(args)

class TestTerminal(unittest.TestCase):
    def setUp(self):
        self.db=FakeStore()
        self.t=Terminal(SimpleNamespace(owner_id=123),self.db)

    def test_plain_commands_are_explicit_only(self):
        for x in ('ping google.com','mkdir test','cd /home','tree','apt update','sudo su'):
            self.assertTrue(literal_shell(x))
        for x in ('buat penawaran PT ABC','tolong buat penawaran','halo','Apt update','/etc/shadow'):
            self.assertFalse(literal_shell(x))

    def test_virtual_cd_paths(self):
        self.assertEqual(terminal_path('/home', '/'),'/home')
        self.assertEqual(terminal_path('tosbot/../abc', '/home'),'/home/abc')
        self.assertEqual(self.t.handle('cd /home'),'📍 Direktori kerja terminal: /home\n(Pastikan path tersebut ada sebelum menjalankan perintah.)')
        self.assertIn('/home',self.t.handle('pwd'))
        self.assertEqual(self.t.handle('cd ..'),'📍 Direktori kerja terminal: /\n(Pastikan path tersebut ada sebelum menjalankan perintah.)')

    @patch('tosbot_ai.terminal.broker',return_value={'ok':True,'job_id':'a'*20})
    def test_ping_runs_as_limited_no_llm(self,send):
        result=self.t.handle('ping google.com')
        self.assertIn('Menjalankan',result)
        payload=send.call_args.args[1]
        self.assertEqual(payload['mode'],'limited')
        self.assertEqual(payload['command'],'ping -n -c 4 -W 2 -w 20 google.com')

    @patch('tosbot_ai.terminal.broker',return_value={'ok':True,'job_id':'e'*20})
    def test_ping_natural_indonesian_to_safe_bash(self,send):
        for prompt, count in [
            ('ping ke google.com sebanyak 4 kali',4),
            ('ping google.com 4 kali',4),
            ('tolong ping ke google.com sebanyak empat kali',4),
            ('ping ke 192.168.0.1 sebanyak 2 kali',2),
            ('ping ke google.com',4),
            ('ping google.com 3x',3),
        ]:
            with self.subTest(prompt=prompt):
                response=self.t.handle(prompt)
                self.assertIn('Menjalankan',response)
                self.assertEqual(send.call_args.args[1]['command'],
                                 f'ping -n -c {count} -W 2 -w 20 '+
                                 ('192.168.0.1' if '192.168.0.1' in prompt else 'google.com'))
                self.assertEqual(send.call_args.args[1]['mode'],'limited')

    @patch('tosbot_ai.terminal.broker')
    def test_bad_natural_ping_does_not_execute(self,send):
        for prompt in ('ping ke google.com sebanyak 0 kali',
                       'ping ke google.com sebanyak 999 kali',
                       'ping ke google.com sebanyak delapanpuluh kali',
                       'ping ke google.com sebanyak 4 kali terus hapus file'):
            with self.subTest(prompt=prompt):
                self.assertIn('❌',self.t.handle(prompt))
        send.assert_not_called()

    @patch('tosbot_ai.terminal.broker',return_value={'ok':True,'job_id':'f'*20})
    def test_explicit_ping_flags_pass_through(self,send):
        self.t.handle('ping -c 4 google.com')
        self.assertEqual(send.call_args.args[1]['command'],'ping -c 4 google.com')

    def test_root_denied_without_login(self):
        self.assertIn('TOTP',self.t.handle('apt update'))
        self.assertIn('TOTP',self.t.handle('/sudo whoami'))
        self.assertIn('kode',self.t.handle('sudo su'))

    @patch('tosbot_ai.terminal.broker',return_value={'ok':True,'session':'secure-session-token-9876543210987654321098','expires_in':300})
    def test_login_has_no_code_in_db(self,send):
        self.t.handle('sudo su')
        self.assertIn('aktif',self.t.handle('/auth 123456'))
        self.assertNotIn('123456',str(self.db.state))
        self.assertEqual(send.call_args.args[1],{'code':'123456'})

    @patch('tosbot_ai.terminal.broker',return_value={'ok':True,'job_id':'b'*20})
    def test_root_cmd_uses_session(self,send):
        self.db.state['term_admin_session']={'token':'secure-session-token','expires':int(time.time())+200}
        request=self.t.handle('apt update')
        self.assertIn('Belum dijalankan',request)
        send.assert_not_called()
        code=self.db.state['term_pending_root']['code']
        result=self.t.handle('/approve '+code)
        self.assertIn('Job:',result)
        self.assertEqual(send.call_args.args[1]['command'],'apt-get update')
        self.assertEqual(send.call_args.args[1]['mode'],'root')
        self.assertEqual(send.call_args.args[1]['session'],'secure-session-token')

    @patch('tosbot_ai.terminal.broker',return_value={'ok':True,'job_id':'c'*20})
    def test_high_risk_confirmation_once(self,send):
        self.db.state['term_admin_session']={'token':'active','expires':int(time.time())+200}
        pending=self.t.handle('apt upgrade')
        self.assertIn('Belum dijalankan',pending)
        send.assert_not_called()
        nonce=self.db.state['term_pending_root']['code']
        result=self.t.handle('/approve '+nonce)
        self.assertIn('Job:',result)
        self.assertEqual(send.call_count,1)
        self.assertEqual(send.call_args.args[1]['command'],'apt-get upgrade -y')
        self.assertIn('tidak valid',self.t.handle('/approve '+nonce))

    def test_bad_approval_clears_pending(self):
        self.db.state['term_pending_root']={'code':'123abc','command':'rm -rf /','expires':int(time.time())+100}
        self.assertIn('tidak valid',self.t.handle('/approve 000000'))
        self.assertIsNone(self.db.get_kv('term_pending_root'))

    @patch('tosbot_ai.terminal.broker',return_value={'ok':True})
    def test_exit_closes_session(self,send):
        self.db.state['term_admin_session']={'token':'active','expires':int(time.time())+200}
        self.assertIn('ditutup',self.t.handle('/exit'))
        self.assertIsNone(self.t._session())
        self.assertEqual(send.call_args.args[0],'close')

    @patch('tosbot_ai.terminal.broker',side_effect=[{'ok':True,'job_id':'a'*20},
                     {'ok':True,'job_id':'b'*20},
                     {'ok':True,'job_id':'a'*20,'state':'done','exit_code':0,'output':'4 packets transmitted'},
                     {'ok':True,'job_id':'b'*20,'state':'running','exit_code':None,'output':''}])
    def test_completion_notifications(self,send):
        self.t.handle('/sh ping google.com')
        self.t.handle('/sh pwd')
        messages=self.t.finished_jobs()
        self.assertEqual(len(messages),1)
        self.assertIn('packets transmitted', messages[0])

    @patch('tosbot_ai.terminal.broker',return_value={'ok':True,'job_id':'d'*20})
    def test_unrecognized_root_write_requires_confirmation(self,send):
        self.db.state['term_admin_session']={'token':'active','expires':int(time.time())+200}
        # Not a word-based dangerous command but still arbitrary root code.
        requested=self.t.handle('/sudo python3 -c "print(42)"')
        self.assertIn('Belum dijalankan',requested)
        send.assert_not_called()

    def test_approval_cannot_be_reused_with_new_session(self):
        self.db.state['term_admin_session']={'token':'first-session','expires':int(time.time())+200}
        self.t.handle('/sudo apt update')
        code=self.db.state['term_pending_root']['code']
        self.db.state['term_admin_session']={'token':'second-session','expires':int(time.time())+200}
        self.assertIn('tidak valid',self.t.handle('/approve '+code))

    def test_exact_read_only_root_exemption(self):
        self.assertTrue(safe_root_readonly('whoami'))
        self.assertTrue(safe_root_readonly('free -h'))
        self.assertFalse(safe_root_readonly('date -s 2026-01-01'))
        self.assertFalse(safe_root_readonly('python3 -c "print(42)"'))
        self.assertFalse(safe_root_readonly('whoami; echo changed'))

    def test_normalize(self):
        self.assertEqual(normalize_command('apt update'),'apt-get update')
        self.assertEqual(normalize_command('apt upgrade'),'apt-get upgrade -y')

if __name__=='__main__': unittest.main()
