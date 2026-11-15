"""User screenshot scenarios: safe Linux tool execution and confirmation."""
from __future__ import annotations
import importlib.util
from importlib.machinery import SourceFileLoader
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tosbot_ai.network_agent import valid_ip, parse_ping, ping_private
from tosbot_ai.config import Settings
from tosbot_ai.engine import Engine
from tosbot_ai.storage import Store
from tosbot_ai.directory_agent import DirectoryAgent

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_loader('fsctl',SourceFileLoader('fsctl',str(ROOT/'scripts/tosbot-ai-fs-ctl')))
fsctl=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fsctl)

class FakeRun:
    def __init__(self):self.cmds=[]
    def __call__(self,command,**kwargs):
        self.cmds.append(command)
        class Process:
            stdout='4 packets transmitted, 4 received, 0% packet loss\nrtt min/avg/max/mdev = 0.1/0.2/0.3/0.1 ms'
            stderr=''
            returncode=0
        return Process()


class AgentToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.home=Path(self.tmp.name)/'home'
        self.home.mkdir()
        (self.home/'script').mkdir()
        self.calls=[]
        def fs_runner(op,path):
            self.calls.append((op,path))
            return fsctl.make_dir(self.home,path,owner=None) if op=='mkdir' else fsctl.scan(self.home,path,op)
        self.fs_runner=fs_runner
        self.env=patch.dict(os.environ,{'TELEGRAM_OWNER_ID':'1234','GROQ_API_KEY':'dummy',
                                      'TOSBOT_DB_PATH':str(Path(self.tmp.name)/'data.sqlite3'),
                                      'TOSBOT_OUTPUT_DIR':str(Path(self.tmp.name)/'pdf')})
        self.env.start()
        self.db=Store(Settings.load().db_path)
        self.engine=Engine(Settings.load(),self.db)
        self.engine.flow=None
        self.engine.directory_agent=DirectoryAgent(runner=fs_runner)

    def tearDown(self):
        self.db.db.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_mkdir_requires_confirmation_and_works(self):
        r,_=self.engine.handle('buat folder bernama test di dalam dir /home/tosbot/')
        self.assertIn('Konfirmasi',r)
        self.assertFalse((self.home/'test').exists())
        r,_=self.engine.handle('ya buatkan')
        self.assertIn('berhasil dibuat',r)
        self.assertTrue((self.home/'test').is_dir())
        self.assertEqual(self.calls[-1],('mkdir','/home/tosbot/test'))

    def test_mkdir_shell_relative_and_timeout(self):
        text,_=self.engine.handle('mkdir test')
        self.assertIn('Akan membuat folder: /home/tosbot/test',text)
        self.assertFalse((self.home/'test').exists())
        pending=self.db.get_kv('pending_mkdir')
        pending['created_at']=0
        self.db.set_kv('pending_mkdir',pending)
        msg,_=self.engine.handle('iya')
        self.assertIn('kedaluwarsa',msg)
        self.assertFalse((self.home/'test').exists())

    def test_mkdir_alias_follows_current(self):
        self.engine.handle('cd script')
        r,_=self.engine.handle('buat folder hello')
        self.assertIn('/home/tosbot/script/hello',r)
        self.engine.handle('iya')
        self.assertTrue((self.home/'script'/'hello').is_dir())

    def test_reject_home_root_then_followup(self):
        r,_=self.engine.handle('buatkan folder di dalam /home dengan nama test')
        self.assertIn('tidak dapat',r)
        self.assertFalse((self.home/'test').exists())
        r,_=self.engine.handle('/home/tosbot')
        self.assertIn('/home/tosbot/test',r)
        self.assertFalse((self.home/'test').exists())
        r,_=self.engine.handle('ya buatkan')
        self.assertIn('berhasil dibuat',r)
        self.assertTrue((self.home/'test').exists())

    def test_mkdir_denials_and_cancel(self):
        r,_=self.engine.handle('mkdir /root/suspect')
        self.assertIn('tidak dapat',r)
        with self.assertRaises(ValueError):
            fsctl.make_dir(self.home,'/home/tosbot/.ssh',owner=None)
        with self.assertRaises(ValueError):
            fsctl.make_dir(self.home,'/home/tosbot/script/ai-agent/a',owner=None)
        self.engine.handle('buat folder test')
        self.engine.handle('batal')
        self.assertFalse((self.home/'test').exists())

    def test_symlink_mkdir_no_follow(self):
        outside=Path(self.tmp.name)/'outside';outside.mkdir()
        (self.home/'script').rename(self.home/'original-script')
        (self.home/'script').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError):
            fsctl.make_dir(self.home,'/home/tosbot/script/new',owner=None)
        self.assertFalse((outside/'new').exists())

    def test_ping_validation(self):
        self.assertEqual(parse_ping('ping ke 192.168.0.1 sebanyak 4 kali'),('192.168.0.1',4))
        self.assertEqual(parse_ping('ping 10.0.0.1 999 kali'),('10.0.0.1',4))
        self.assertEqual(valid_ip('192.168.0.1'),'192.168.0.1')
        self.assertEqual(valid_ip('100.92.1.9'),'100.92.1.9')
        self.assertIsNone(valid_ip('8.8.8.8'))
        self.assertIsNone(valid_ip('127.0.0.1'))
        self.assertIsNone(valid_ip('1.1.1.1; rm -rf /'))
        fake=FakeRun()
        result=ping_private('192.168.0.1',4,runner=fake)
        self.assertIn('4 received',result)
        self.assertEqual(fake.cmds[0],['ping','-n','-c','4','-W','2','-w','12','192.168.0.1'])
        self.assertIn('dibatasi',ping_private('8.8.8.8',4,runner=fake))
        self.assertEqual(len(fake.cmds),1)

    def test_ping_old_yes_migrated(self):
        self.db.set_kv('history',[
            {'role':'user','content':'ping ke 192.168.0.1 sebanyak 4 kali'},
            {'role':'assistant','content':'Apakah Anda ingin saya melakukan ping 192.168.0.1 sebanyak 4 kali?'}])
        with patch('tosbot_ai.engine.ping_private',return_value='ping performed') as func:
            result,_=self.engine.handle('ya')
        self.assertEqual(result,'ping performed')
        func.assert_called_once_with('192.168.0.1',4)

if __name__=='__main__': unittest.main()
