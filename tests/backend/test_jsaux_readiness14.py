"""Preparation -> installed player evidence. No physical USB claims."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from das.core.catalog import ScreensaverError
from das.jsaux.collection import preparation_spec
from das.jsaux.diagnostics import relay_snapshot
from das.jsaux.manager import Delegation
from das.studio.service import StudioService
from das.studio.installer import Installer
from test_studio import ASSETS,FakeMedia
import test_jsaux as fixtures


class Readiness14Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare_receipt();self.m=self.f.manager
        self.m.receipt['input_spec']=preparation_spec(self.m.games(),self.m.options,self.m.store.options())

    def test_exact_stale_reason_and_components_no_source_leak(self):
        self.m.configure({'transition':'slide'})
        report=self.m.diagnostic_snapshot()
        self.assertEqual(report['prepared']['reason'],'PREPARATION_STALE')
        self.assertEqual(report['prepared']['changed'],['playback'])
        self.assertFalse(report['installation']['collection_matches'])
        self.assertTrue(report['installation']['prepared_collection_matches'])
        raw=json.dumps(report)
        for private in ('input_spec',str(self.f.root),self.m.receipt['collection_id'],'identities.gif','content1','token1'):
            self.assertNotIn(private,raw)
        self.assertFalse(report['relay']['observed'])

    def test_missing_registration_and_file_reference_are_distinct(self):
        self.m.receipt.pop('content_id')
        self.assertEqual(self.m.readiness()['reason'],'REGISTRATION_MISSING')
        self.m.receipt.pop('path')
        self.assertEqual(self.m.readiness()['reason'],'PREPARED_FILE_MISSING')

    def test_connected_requested_faceplate_cannot_be_silently_omitted_from_install(self):
        marker=self.f.installer.destination/'.decky-animated-screensaver.json'
        old=marker.read_bytes()
        self.m.configure({'transition':'slide'})
        with self.assertRaises(ScreensaverError) as raised:self.f.installer.install()
        self.assertEqual(raised.exception.code,'JSAUX_PREPARATION_REQUIRED')
        self.assertEqual(marker.read_bytes(),old)
        self.assertEqual(self.m.events[-1]['event'],'installation-blocked')
        self.assertFalse(self.m.events[-1]['ready'])

    def test_absent_or_disabled_faceplate_does_not_block_tv_install(self):
        self.m.configure({'transition':'slide'})
        # Installation now refreshes presence itself: the broker fixture must
        # report the absence, not only an overwritten cached UI flag.
        self.f.fake.current['hardware']='absent'
        self.assertTrue(self.f.installer.install()['installed'])
        self.assertFalse(self.m.detected)
        self.assertIsNone(self.f.installer.jsaux_export)
        self.f.fake.current['hardware']='available';self.m.configure({'enabled':False})
        self.assertTrue(self.f.installer.install()['installed'])
        self.assertIsNone(self.f.installer.jsaux_export)

    def test_readiness_export_order_survive_new_store_and_manager(self):
        self.m.store.data['jsaux_collection']=copy.deepcopy(self.m.receipt);self.m.store.save()
        service=StudioService(self.m.store.root,media=FakeMedia(),games_provider=lambda:[])
        self.addCleanup(service.shutdown)
        installer=Installer(service.catalog,self.f.root/'Steam',ASSETS);installer.status(True)
        manager=Delegation(service,installer,self.f.fake);installer.delegation=manager
        self.addCleanup(manager.shutdown)
        self.assertEqual(self.m.identity(),manager.identity())
        self.assertTrue(manager.status()['prepared']['ready'])
        self.assertTrue(manager.status()['installed'])
        self.assertTrue(manager.diagnostic_snapshot()['installation']['collection_matches'])

    def test_old_preparation_is_explicitly_stale_not_silently_blessed(self):
        self.m.receipt['collection_id']='f'*64;self.m.receipt.pop('input_spec')
        report=self.m.diagnostic_snapshot()
        self.assertEqual(report['prepared']['reason'],'PREPARATION_STALE')
        self.assertIsNone(report['prepared']['input_schema'])
        self.assertEqual(report['prepared']['changed'],[])

    def test_frontend_snapshot_allowlist_discards_paths_tokens_invalid_values(self):
        raw=dict(schema='das-jsaux-relay-v1',enabled=True,token='private',
            iframe=dict(installed=True,routed=4,errors=-1,last_error='BACKEND_FAILED',path='/private'),
            storage=dict(available=True,running=True,probes=999999,read_errors=True,last_error='secret',last_rejection='INVALID_STORAGE'),
            recovery=dict(requested=2,failed=1,username='private'))
        report=self.m.diagnostic_snapshot(raw)
        self.assertTrue(report['relay']['observed'])
        self.assertEqual(report['relay']['iframe'],dict(installed=True,routed=4,last_error='BACKEND_FAILED'))
        self.assertEqual(report['relay']['storage'],dict(available=True,running=True,probes=999999,last_rejection='INVALID_STORAGE'))
        self.assertNotIn('private',json.dumps(report))
        self.assertFalse(relay_snapshot(dict(schema='other'))['observed'])
        malformed=dict(schema='das-jsaux-relay-v1',storage=dict(last_error_name=['private'],last_native_result=True))
        self.assertEqual(relay_snapshot(malformed)['storage'],{})

    def test_player_arrival_is_logged_even_if_installed_export_is_stale(self):
        message=self.f.message();self.m.configure({'transition':'slide'})
        self.assertFalse(self.m.player(message)['accepted'])
        self.assertEqual([e['event'] for e in self.m.events[-2:]],['player-message-open','player-refused'])
        self.assertEqual(self.m.events[-1]['reason'],'CONTENT_MISSING')
        self.assertEqual(self.f.fake.calls,[])

    def test_explicit_prepare_records_complete_current_readiness(self):
        self.m.configure({'transition':'slide'})
        self.m.service.compiler.runner=SimpleNamespace(ffmpeg='fixture-not-executed',library_path=None)
        with patch('das.jsaux.manager.capture',return_value=bytes(10368)),patch.object(self.m.service,'_assets',return_value=[]):
            self.m.prepare();self.m.thread.join(5)
        state=self.m.status()
        self.assertTrue(state['prepared']['ready'],state)
        self.assertEqual(state['prepared']['input_schema'],6)
        self.assertFalse(state['installed'])
        self.assertEqual(self.m.events[-1]['event'],'collection-registered')
        self.assertTrue(self.m.events[-1]['ready'])
        self.f.installer.install()
        self.assertTrue(self.m.status()['installed'])
        self.assertTrue(self.m.events[-1]['included'])
