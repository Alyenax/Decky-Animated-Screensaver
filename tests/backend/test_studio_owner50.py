"""Real paired Studio -> Unix publication -> Steam HTTP -> GCA ownership."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import test_jsaux_interop as interop
import test_jsaux as fixtures
from test_studio import scene,ASSETS,FakeMedia
from das.studio.service import StudioService
from das.studio.installer import Installer
from das.jsaux.manager import Delegation

@unittest.skipUnless(interop.GCA,'explicit DAS_TEST_GCA_ROOT required')
class StudioOwnerTests(unittest.TestCase):
    setUp=interop.InteropTests.setUp
    def studio(self):
        self.service=StudioService(self.root/'library',media=FakeMedia(),games_provider=lambda:[])
        self.addCleanup(self.service.shutdown);scene(self.service.catalog)
        (self.root/'Steam').mkdir()
        self.installer=Installer(self.service.catalog,self.root/'Steam',ASSETS)
        self.manager=Delegation(self.service,self.installer,self.client)
        self.installer.delegation=self.manager;self.addCleanup(self.manager.shutdown)
        fixtures.ManagerTests.prepare_receipt(self)
        self.assertEqual(self.client.hello['negotiated_version'],'1.1')
        self.assertEqual(self.installer.jsaux_export['controller'],'GabeCubeAura')
        self.assertIn(':37680/',self.installer.jsaux_export['relay']['url'])
        self.assertEqual(self.hardware.commands,[])
        self.sequence=0
    def player(self,event,**fields):
        self.sequence+=1
        body=dict(event=event,token=self.installer.token,collection_id=self.installer.jsaux_export['collection_id'],
            session_id='steam-installed',mode=self.installer.jsaux_export['mode'],sequence=self.sequence,**fields)
        c=http.client.HTTPConnection('127.0.0.1',37680,timeout=4)
        try:
            c.request('POST','/jsaux/v1/player',body=json.dumps(body),headers={'Origin':'https://decky-animated-screensaver.steamloopback.host','Content-Type':'application/json'})
            r=c.getresponse();self.assertEqual(r.status,200);return json.loads(r.read())
        finally:c.close()
    def start(self):
        self.assertTrue(self.player('open')['accepted'])
        now=self.player('clock')['broker_mono_ms']
        # Exercises migration of a previously prepared 2.5s collection too.
        self.assertTrue(self.player('ready',ready_mono_ms=now,deadline_mono_ms=now+self.installer.jsaux_export['sync_wait_ms'],clock_uncertainty_ms=1)['gate_accepted'])
        hb=self.player('heartbeat');candidate=hb['candidate']['candidate_id']
        self.assertTrue(self.player('started',started_mono_ms=time.monotonic_ns()//1000000,outcome='software-coordinated',candidate_id=candidate)['gca_owned'])
    def test_direct_player_survives_das_shutdown_and_no_das_relay_required(self):
        self.studio();self.manager.shutdown();self.start()
        lease=self.broker.lease
        self.assertEqual([c[0] for c in self.hardware.commands],['reserve','submit'])
        self.broker.clock=lambda:time.monotonic()+7200
        self.broker.tick();self.assertTrue(self.broker.is_valid(lease['operation_id']))
        self.assertTrue(self.player('stop',reason='unloading')['gca_owned'])
        self.assertTrue(self.broker.is_valid(lease['operation_id']))
        self.hardware.state['steam']['observed']='inactive';self.broker.tick()
        self.assertFalse(self.broker.is_valid(lease['operation_id']))
        self.assertEqual([c[0] for c in self.hardware.commands],['reserve','submit','cancel','restore'])
    def test_failed_staging_preserves_export_token_and_published_binding(self):
        self.studio();token=self.installer.token;old=copy.deepcopy(self.broker.player_runtime.bindings)
        marker=self.installer.destination/'.decky-animated-screensaver.json';before=marker.read_bytes()
        with patch('das.studio.installer.ScreensaverInstaller._copy',side_effect=OSError('fixture storage full')):
            with self.assertRaises(OSError):self.installer.install()
        self.assertEqual(self.installer.token,token);self.assertEqual(marker.read_bytes(),before)
        self.assertEqual(old,self.broker.player_runtime.bindings)
        self.assertEqual(self.hardware.commands,[])
        self.start()
    def test_calibration_status_and_disable_are_control_operations_only(self):
        self.studio();runtime=self.broker.player_runtime
        token=self.installer.token
        self.client.request('calibrate_player',dict(token=token,alignment_ms=300))
        self.assertEqual(runtime.bindings[hashlib.sha256(token.encode()).hexdigest()]['alignment_ms'],300)
        status=self.client.request('player_status',dict(token=token))
        self.assertTrue(status['published']);self.assertEqual(status['phase'],'idle');self.assertFalse(status['first_player'])
        self.start();status=self.client.request('player_status',dict(token=token));self.assertEqual(status['phase'],'active')
        self.manager.configure({'enabled':False})
        self.assertEqual(runtime.bindings,{})
        self.assertFalse(self.broker.is_valid(self.broker.lease['operation_id']))

    def test_independent_slow_transfer_outlives_sync_window_and_unconfirmed_is_not_retried(self):
        self.studio()
        self.manager.configure({'mode':'async'})
        # Reuse the codec fixture only; registration, publication, installed
        # descriptor and HTTP -> GCA lease/restore path remain production code.
        self.manager.receipt['collection_id']=self.manager.identity()
        self.manager.registered_boot=None
        self.installer.install()
        pending=[]
        def delayed_submit(job,report):
            self.hardware.commands.append(('submit',job['operation_id']))
            report(job['operation_id'],transfer_state='transferring')
            pending.append((job['operation_id'],report))
        with patch.object(self.hardware,'submit',side_effect=delayed_submit):
            self.assertTrue(self.player('open')['accepted'])
            gate=self.player('ready',ready_mono_ms=None,deadline_mono_ms=None,clock_uncertainty_ms=None)
            self.assertTrue(gate['gate_accepted'])
            result=self.player('started',started_mono_ms=None,outcome='independent',candidate_id=None)
            self.assertTrue(result['gca_owned'])
        lease=self.broker.lease
        self.manager.shutdown()
        self.broker.clock=lambda:time.monotonic()+31
        self.broker.tick()
        self.assertTrue(self.broker.is_valid(lease['operation_id']))
        self.assertTrue(self.player('heartbeat')['gca_owned'])
        self.assertEqual([c[0] for c in self.hardware.commands],['reserve','submit'])
        operation,report=pending[0]
        report(operation,transfer_state='unconfirmed',reason='USB_UNCONFIRMED')
        self.broker.tick()
        status=self.client.request('player_status',dict(token=self.installer.token))
        self.assertEqual(status['reason'],'USB_UNCONFIRMED')
        self.assertEqual(status['last_transfer'],'unconfirmed')
        self.assertEqual(status['restore_state'],'confirmed')
        self.assertFalse(self.broker.is_valid(operation))
        self.assertEqual([c[0] for c in self.hardware.commands],['reserve','submit','cancel','restore'])
        self.broker.tick()
        self.assertEqual([c[0] for c in self.hardware.commands],['reserve','submit','cancel','restore'])
