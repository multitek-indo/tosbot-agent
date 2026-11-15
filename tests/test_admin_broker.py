from __future__ import annotations
import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]/'scripts'/'tosbot-ai-admin-ctl'
loader=importlib.machinery.SourceFileLoader('root_helper_testing',str(P))
spec=importlib.util.spec_from_loader('root_helper_testing',loader)
helper=importlib.util.module_from_spec(spec)
loader.exec_module(helper)


class AdminBrokerTests(unittest.TestCase):
    def test_totp_matches_reference_and_replay_rejected(self):
        key = base64.b32encode(b'12345678901234567890').decode().rstrip('=')
        self.assertEqual(helper.current_totp(key,59//30),'287082')
        with tempfile.TemporaryDirectory() as td:
            cfg=Path(td)/'admin-auth.json'
            helper.write_json(cfg, {'key':key,'last_step':-1,'fail_since':0,'fail_count':0})
            with patch.object(helper,'CFG',cfg), patch.object(helper.time,'time',return_value=59):
                helper.verify_totp('287082')
                with self.assertRaises(PermissionError):helper.verify_totp('287082')
                self.assertEqual(helper.read_json(cfg)['last_step'],1)

    def test_root_setup_must_not_change_env_parent_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'etc-tosbot'
            p.mkdir(mode=0o750)
            secretfile=p/'admin-auth.json'
            old=os.stat(p).st_mode & 0o777
            with patch.object(helper,'CFG',secretfile), patch.object(helper,'real_admin_only'):
                with contextlib.redirect_stdout(io.StringIO()):helper.setup()
            self.assertEqual(os.stat(p).st_mode & 0o777,old)
            self.assertEqual(os.stat(secretfile).st_mode & 0o777,0o600)

    def test_root_submit_requires_session(self):
        with patch.object(helper,'bot_only'), patch.object(helper,'read_packet',return_value={
            'mode':'root','command':'id','cwd':'/root','session':'fake'}), \
             patch.object(helper,'session_ok',return_value=False):
            with self.assertRaises(PermissionError):helper.submit()

    def test_limited_submit_never_needs_root_session(self):
        with tempfile.TemporaryDirectory() as td:
            dummy=type('CP',(),{'returncode':0})()
            with patch.object(helper,'ROOT',Path(td)/'jobs'),patch.object(helper,'bot_only'),\
                 patch.object(helper,'read_packet',return_value={
                     'mode':'limited','command':'pwd','cwd':'/home'}),\
                 patch.object(helper.subprocess,'run',return_value=dummy):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    helper.submit()
                result=json.loads(stdout.getvalue())
                self.assertTrue(result['ok'])
                self.assertEqual(result['mode'],'limited')
                j=helper.ROOT/(result['job_id']+'.json')
                self.assertEqual(os.stat(j).st_mode & 0o777,0o600)
                self.assertEqual(helper.read_json(j)['command'],'pwd')

    def test_root_outputs_locked_without_session(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            jid='e'*20
            helper.write_json(root/(jid+'.json'),{'id':jid,'mode':'root',
                'state':'done','exit_code':0,'started_at':int(time.time()),'completed_at':int(time.time())})
            (root/(jid+'.log')).write_text('ROOT_SECRET_SHOULD_NEVER_LEAK')
            with patch.object(helper,'ROOT',root),patch.object(helper,'bot_only'),\
                 patch.object(helper,'read_packet',return_value={'session':''}):
                with contextlib.redirect_stdout(io.StringIO()) as stdout: helper.status(jid)
                response=json.loads(stdout.getvalue())
                self.assertTrue(response['locked'])
                self.assertNotIn('ROOT_SECRET',str(response))

    def test_root_status_unlocks_only_authenticated_session(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            jid='f'*20
            helper.write_json(root/(jid+'.json'),{'id':jid,'mode':'root',
                'state':'done','exit_code':0,'started_at':int(time.time()),'completed_at':int(time.time())})
            (root/(jid+'.log')).write_text('result visible after auth')
            with patch.object(helper,'ROOT',root),patch.object(helper,'bot_only'),\
                 patch.object(helper,'read_packet',return_value={'session':'valid'}),\
                 patch.object(helper,'session_ok',return_value=True):
                with contextlib.redirect_stdout(io.StringIO()) as stdout: helper.status(jid)
                response=json.loads(stdout.getvalue())
                self.assertFalse(response['locked'])
                self.assertIn('result visible',response['output'])

if __name__=='__main__': unittest.main()
