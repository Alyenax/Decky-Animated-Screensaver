"""Real Delegation/workspace/export logic; decoder and broker are bounded fixtures.

These tests prove software state and preserved export bytes, never USB or optics.
"""
import copy
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from das.jsaux.protocol import BrokerError
from das.studio.workspace import CollectionWorkspace
import test_jsaux as fixtures


class HardwarePreparation54Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare_receipt();self.manager=self.f.manager;self.service=self.f.service
        self.fake=self.f.fake;self.installer=self.f.installer
        self.service._scanned=True;self.service._ready.add(620)
        self.service._assets=lambda *args:[]
        self.service.compiler.runner=SimpleNamespace(ffmpeg='decoder-fixture',library_path=None)
        self.manager.configure({'transition':'slide'});self.fake.calls.clear()

    def test_disconnect_during_local_compile_cannot_claim_new_prepared_or_usb_output(self):
        previous=copy.deepcopy(self.manager.receipt)
        installed=(self.installer.destination/'catalog.js').read_bytes()
        entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        def decode(*args,**kwargs):
            entered.set();self.assertTrue(release.wait(2));return bytes(64*54*3)
        def refuse(path,collection_id):
            self.fake.calls.append(('register-refused',collection_id));raise BrokerError('DEVICE_ABSENT')
        self.fake.register=refuse
        with patch('das.jsaux.manager.capture',side_effect=decode):
            self.manager.prepare();self.assertTrue(entered.wait(1))
            self.fake.current['hardware']='absent';self.manager.refresh()
            self.assertFalse(self.manager.detected)
            release.set();self.manager.thread.join(3)
        self.assertFalse(self.manager.busy());self.assertEqual(self.manager.reason,'DEVICE_ABSENT')
        # Registration refusal removes newly encoded files and must not replace
        # its former receipt or fabricate preparation/USB success.
        self.assertEqual(list(self.service.catalog.managed('jsaux').glob('*.gif')),[], 'Failed generation must remove its unpublished GIFs')
        self.assertEqual(self.manager.receipt,previous)
        status=self.manager.status();self.assertFalse(status['prepared']['ready'])
        self.assertEqual(status['last_transfer'],'not-started');self.assertFalse(status['installed'])
        self.assertEqual((self.installer.destination/'catalog.js').read_bytes(),installed)
        self.assertEqual([row[0] for row in self.fake.calls],['register-refused'])

    def test_real_workspace_broker_refusal_is_partial_and_preserves_installed_collection(self):
        before={path.name:path.read_bytes() for path in self.installer.destination.iterdir() if path.is_file()}
        old_descriptor=copy.deepcopy(self.installer.jsaux_export)
        old_receipt=copy.deepcopy(self.manager.receipt)
        def refuse(path,collection_id):
            self.fake.calls.append(('register-refused',collection_id));raise BrokerError('BROKER_UNAVAILABLE')
        self.fake.register=refuse
        workspace=CollectionWorkspace(self.service,self.installer,self.manager);self.addCleanup(workspace.shutdown)
        with patch('das.jsaux.manager.capture',return_value=bytes(64*54*3)):
            workspace.start(install_only=True);workspace.thread.join(4)
        self.assertFalse(workspace.busy());task=workspace.summary()['task']
        self.assertEqual(task['state'],'partial');self.assertEqual(task['faceplate_state'],'repair_required')
        self.assertEqual(task['tv_state'],'prepared');self.assertEqual(task['error'],'BROKER_UNAVAILABLE')
        self.assertNotIn('outcome',task)
        self.assertEqual({path.name:path.read_bytes() for path in self.installer.destination.iterdir() if path.is_file()},before)
        self.assertEqual(self.installer.jsaux_export,old_descriptor);self.assertEqual(self.manager.receipt,old_receipt)
        self.assertEqual(self.manager.status()['last_transfer'],'not-started')
        self.assertEqual([row[0] for row in self.fake.calls],['register-refused'])
