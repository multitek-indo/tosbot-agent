"""V1.6 offline directory-agent acceptance tests; no provider credentials."""
from __future__ import annotations
import importlib.util
from importlib.machinery import SourceFileLoader
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tosbot_ai.directory_agent import DirectoryAgent, parse_directory_command, safe_path
from tosbot_ai.config import Settings
from tosbot_ai.engine import Engine
from tosbot_ai.storage import Store

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_loader('fsctl', SourceFileLoader('fsctl', str(ROOT / 'scripts/tosbot-ai-fs-ctl')))
fsctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fsctl)


class AgentDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / 'home'
        self.base.mkdir()
        (self.base / 'script').mkdir()
        (self.base / 'script' / 'ai-agent').mkdir()
        (self.base / 'script' / 'lainnya').mkdir()
        (self.base / 'README.md').write_text('hello')
        (self.base / '.ssh').mkdir()
        (self.base / 'script' / '.env').write_text('PRIVATE')
        (self.base / 'script' / 'ai-agent' / 'install.sh').write_text('echo hi')
        secret = Path(self.tmp.name) / 'secret'
        secret.mkdir()
        (secret / 'root.key').write_text('PRIVATE')
        (self.base / 'script' / 'link').symlink_to(secret, target_is_directory=True)
        self.run_tool = lambda op,path: (fsctl.make_dir(self.base,path,owner=None) if op=='mkdir' else fsctl.scan(self.base,path,op))
        self.env = patch.dict(os.environ, {
            'TELEGRAM_OWNER_ID': '123456', 'GROQ_API_KEY': 'test',
            'TOSBOT_DB_PATH': str(Path(self.tmp.name) / 'tosbot.sqlite3'),
            'TOSBOT_OUTPUT_DIR': str(Path(self.tmp.name) / 'pdf'),
        })
        self.env.start()
        self.store = Store(Settings.load().db_path)
        self.engine = Engine(Settings.load(), self.store)
        self.engine.flow = None
        self.engine.directory_agent = DirectoryAgent(runner=self.run_tool)

    def tearDown(self):
        self.store.db.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_direct_listing(self):
        for msg in ('cek dir script','isi dir script','list isi folder script',
                    'lihat isi direktori /home/tosbot/script', 'ls /home/tosbot/script'):
            with self.subTest(msg=msg):
                text,_=self.engine.handle(msg)
                self.assertIn('📁 ai-agent',text)
                self.assertIn('📁 lainnya',text)
                self.assertNotIn('Apakah Anda',text)
                self.assertNotIn('.env',text)
                self.assertNotIn('link',text)

    def test_current_directory_commands(self):
        text,_=self.engine.handle('cek dir home')
        self.assertIn('📁 script',text)
        text,_=self.engine.handle('cd home')
        self.assertIn('Direktori aktif sekarang: /home/tosbot',text)
        text,_=self.engine.handle('cd script')
        self.assertIn('Direktori aktif sekarang: /home/tosbot/script',text)
        text,_=self.engine.handle('ls')
        self.assertIn('📁 ai-agent',text)
        text,_=self.engine.handle('pwd')
        self.assertIn('/home/tosbot/script',text)
        text,_=self.engine.handle('cd ..')
        self.assertIn('Direktori aktif sekarang: /home/tosbot',text)

    def test_counts_and_tree(self):
        text,_=self.engine.handle('ada berapa folder dalam folder script?')
        self.assertIn('Jumlah folder: 2',text)
        tree,_=self.engine.handle('struktur folder script')
        self.assertIn('install.sh',tree)
        self.assertNotIn('root.key',tree)

    def test_unspecified_and_followup(self):
        text,_=self.engine.handle('cek isi dir')
        self.assertIn('📁 script',text) # uses current directory, no repeated question
        self.store.set_kv('pending_directory',{'operation':'list','path':None})
        reply,_=self.engine.handle('script')
        self.assertIn('📁 ai-agent',reply)

    def test_yes_old_prompt(self):
        self.store.set_kv('history',[
            {'role':'user','content':'ada berapa folder dalam folder script?'},
            {'role':'assistant','content':'Apakah Anda ingin saya menghitung jumlah folder di direktori /script?'}])
        result,_=self.engine.handle('iya')
        self.assertIn('Jumlah folder: 2',result)

    def test_outside_denied(self):
        result,_=self.engine.handle('cek dir root')
        self.assertIn('luar izin',result)
        self.assertIsNone(safe_path('/root'))
        self.assertIsNone(safe_path('/home/tosbot/script/../.ssh'))
        self.assertIsNone(safe_path('/home/tosbot/.ssh'))
        self.assertIsNone(parse_directory_command('hapus folder script'))
        with self.assertRaises((OSError,ValueError)):
            fsctl.scan(self.base,'/etc/passwd','list')
        with self.assertRaises((OSError,ValueError)):
            fsctl.scan(self.base,'/home/tosbot/script/link','list')
        denied=DirectoryAgent(runner=self.run_tool).run('list','/root')
        self.assertIn('luar izin',denied)

    def test_nlu_lists_tools(self):
        from tosbot_ai.ai import ACTIONS,NLU_SYSTEM
        for name in ('server_directory_list','server_ping','server_directory_mkdir','server_directory_cd'):
            self.assertIn(name,ACTIONS)
        self.assertIn('cek dir script',NLU_SYSTEM)

if __name__=='__main__': unittest.main()
