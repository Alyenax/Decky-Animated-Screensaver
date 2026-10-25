"""Compact preparation/cache regressions; no physical USB success claim."""
import copy
import hashlib
import json
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from das.jsaux.collection import PALETTE,STARTUP_TARGET_BYTES,MAX_BYTES,preparation_spec
from test_studio import scene
import test_jsaux as fixtures


class CompactIndependent58Tests(unittest.TestCase):
    def fixture(self):
        f=fixtures.ManagerTests();f.setUp();self.addCleanup(f.doCleanups)
        return f

    def test_old_independent_receipt_is_stale_sync_identity_is_unchanged(self):
        f=self.fixture();f.prepare_receipt();m=f.manager
        sync_spec=preparation_spec(m.games(),m.options,m.store.options())
        self.assertEqual(sync_spec['startup_target_bytes'],65536)
        self.assertNotIn('maximum_bytes',sync_spec)
        sync_identity=m.identity()
        m.configure({'mode':'async'})
        self.assertNotEqual(m.identity(),sync_identity)
        current=preparation_spec(m.games(),m.options,m.store.options())
        legacy=copy.deepcopy(current);legacy['startup_target_bytes']=MAX_BYTES;legacy.pop('maximum_bytes')
        m.receipt.update(input_spec=legacy,collection_id=hashlib.sha256(json.dumps(legacy,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        saved=copy.deepcopy(m.receipt)
        for _ in range(3):
            ready=m.readiness()
            self.assertFalse(ready['ready']);self.assertEqual(ready['reason'],'PREPARATION_STALE')
            self.assertEqual(ready['changed'],['startup_target_bytes','maximum_bytes'])
        self.assertEqual(m.receipt,saved)
        self.assertTrue(f.service.catalog.managed(saved['path']).exists())
        m.configure({'mode':'sync'})
        self.assertEqual(m.identity(),sync_identity)

    def test_real_manager_compacts_eleven_pages_and_installs_without_upload(self):
        f=self.fixture();m=f.manager
        for number in range(1,11):scene(f.service.catalog,number)
        m.refresh();m.configure(dict(enabled=True,mode='async',transition='fade'))
        f.service.compiler.runner=SimpleNamespace(ffmpeg='fixture-no-process',library_path=None)
        rng=random.Random(23)
        pages=[bytes(rng.randrange(32) for _ in range(3456)) for _ in range(11)]
        raw=[bytes(c for index in page for c in PALETTE[index]) for page in pages]
        with patch('das.jsaux.manager.capture',side_effect=raw),patch.object(f.service,'_assets',return_value=[]):
            m.prepare();m.thread.join(20)
        self.assertFalse(m.busy());state=m.status()
        self.assertTrue(state['prepared']['ready'],state)
        self.assertEqual(state['prepared']['pages'],11)
        self.assertLessEqual(state['prepared']['bytes'],STARTUP_TARGET_BYTES)
        self.assertTrue(state['prepared']['transition_optimized'])
        self.assertEqual(m.receipt['input_spec']['startup_target_bytes'],STARTUP_TARGET_BYTES)
        self.assertEqual(m.receipt['input_spec']['maximum_bytes'],80*1024)
        self.assertEqual(m.receipt['duration_cs'],11*2400)
        f.installer.install()
        self.assertTrue(m.status()['installed'])
        self.assertEqual(f.installer.jsaux_export['mode'],'async')
        self.assertEqual(f.installer.status()['scene_count'],11)
        self.assertFalse(any(call[0]=='acquire' for call in f.fake.calls))
