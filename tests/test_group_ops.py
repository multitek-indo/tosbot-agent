"""New group operations do not grant shell/root or expose other groups."""
from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tosbot_ai.config import Settings
from tosbot_ai.group import GroupAssistant, _ping_command, _group_ops
from tosbot_ai.storage import Store

class GroupOpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{
            'TELEGRAM_OWNER_ID':'111',
            'TELEGRAM_GROUPS_ENABLED':'true',
            'TELEGRAM_ALLOWED_GROUP_IDS':'-1003733083844',
            'TELEGRAM_GROUP_OPERATIONS_ENABLED':'true',
            'TOSBOT_DB_PATH': str(Path(self.tmp.name)/'db.sqlite3'),
            'ADMIN_ALLOWED_SERVICES':'nginx',
        })
        self.env.start()
        self.s=Settings.load()
        self.store=Store(self.s.db_path)
        self.ai=Mock()
        self.ai.converse_group.return_value="Percakapan biasa"
        self.assistant=GroupAssistant(self.s,self.store,self.ai)

    def tearDown(self):
        self.store.db.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_all_group_users_get_readonly_ops(self):
        for uid in (222,333):
            self.assertIn('Penyimpanan VPS',self.assistant.handle('df -h',-1003733083844,uid))
        self.ai.converse_group.assert_not_called()

    def test_ping_no_shell_and_bounded(self):
        outcome=Mock(returncode=0,stdout='4 packets transmitted',stderr='')
        with patch('tosbot_ai.group.subprocess.run',return_value=outcome) as run:
            response=self.assistant.handle('ping ke google.com sebanyak 4 kali',-1003733083844,222)
        self.assertIn('Ping google.com',response)
        args=run.call_args.args[0]
        self.assertEqual(args,['ping','-n','-c','4','-W','2','-w','12','google.com'])
        self.assertFalse(run.call_args.kwargs['check'])
        self.assertEqual(run.call_args.kwargs['timeout'],15)
        self.assertEqual(_ping_command('ping google.com; rm -rf /'),None)
        self.assertEqual(_ping_command('ping -c 99 google.com'),None)

    def test_dangerous_command_denied_before_ai(self):
        for ix,cmd in enumerate(('/sudo whoami','/sh whoami','apt upgrade','sudo su',
                    'mkdir -p /root/test', 'systemctl restart nginx')):
            result=self.assistant.handle(cmd,-1003733083844,200+ix)
            self.assertIn('⛔',result,cmd)
        self.ai.converse_group.assert_not_called()

    def test_other_group_cannot_enable_readonly_ops(self):
        with patch('tosbot_ai.group.subprocess.run') as run:
            self.assistant.handle('ping google.com',-100000001,222)
        run.assert_not_called()

    def test_disabled_without_explicit_group_allowlist(self):
        with patch.dict(os.environ,{'TELEGRAM_ALLOWED_GROUP_IDS':''}):
            s=Settings.load()
        with patch('tosbot_ai.group.subprocess.run') as run:
            # No allowlist -> GroupAssistant calls AI chat, not tool.
            r=GroupAssistant(s,self.store,self.ai).handle('ping google.com',-1003733083844,222)
        run.assert_not_called()
        self.assertEqual(r,self.ai.converse_group.return_value)

if __name__ == '__main__': unittest.main()
