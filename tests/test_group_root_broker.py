"""Offline authorization checks for root-owned trusted-group allowlist."""
import importlib.machinery
import importlib.util
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1]/'scripts/tosbot-ai-admin-ctl'
loader=importlib.machinery.SourceFileLoader('tosbot_root_broker_test',str(SRC))
spec=importlib.util.spec_from_loader(loader.name,loader)
broker=importlib.util.module_from_spec(spec)
loader.exec_module(broker)

class DummyPath:
    def __init__(self,mode=stat.S_IFREG|0o600, uid=0):
        self.mode, self.uid = mode, uid
    def lstat(self):
        return SimpleNamespace(st_mode=self.mode,st_uid=self.uid)
    def is_file(self):return stat.S_ISREG(self.mode)

class GroupRootBrokerTests(unittest.TestCase):
    def setUp(self):
        self.saved=broker.TRUSTED_GROUPS
        broker.TRUSTED_GROUPS=DummyPath()
        self.json=patch.object(broker,'read_json',return_value={
           'enabled':True,'group_ids':[-1003733083844]})
        self.json.start()

    def tearDown(self):
        broker.TRUSTED_GROUPS=self.saved
        self.json.stop()

    def test_explicit_group_id_and_user_required(self):
        self.assertEqual(broker.trusted_group_id({'group_id':-1003733083844,'actor_id':45}),-1003733083844)
        for packet in ({'group_id':-100999,'actor_id':45},
                       {'group_id':-1003733083844,'actor_id':0},
                       {'group_id':-1003733083844},
                       {'group_id':42,'actor_id':45}):
            with self.subTest(packet=packet),self.assertRaises(PermissionError):
                broker.trusted_group_id(packet)

    def test_non_root_file_rejected(self):
        broker.TRUSTED_GROUPS=DummyPath(uid=1000)
        with self.assertRaises(PermissionError):
            broker.trusted_group_id({'group_id':-1003733083844,'actor_id':45})

    def test_loose_file_permissions_rejected(self):
        broker.TRUSTED_GROUPS=DummyPath(mode=stat.S_IFREG|0o644)
        with self.assertRaises(PermissionError):
            broker.trusted_group_id({'group_id':-1003733083844,'actor_id':45})

    def test_symlink_rejected(self):
        broker.TRUSTED_GROUPS=DummyPath(mode=stat.S_IFLNK|0o777)
        with self.assertRaises(PermissionError):
            broker.trusted_group_id({'group_id':-1003733083844,'actor_id':45})

if __name__=='__main__':unittest.main()
