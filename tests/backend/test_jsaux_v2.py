"""Regression tests for the actual DAS paths; USB is never opened."""
import copy
import os
from pathlib import Path
from unittest.mock import patch
import threading
import time
import unittest
from das.jsaux.collection import transfer_estimate_ms,compile_pages
from das.jsaux.protocol import BrokerError
from das.studio.installer import player_catalog
import test_jsaux as fixtures


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.manager=self.f.manager;self.service=self.f.service;self.fake=self.f.fake

    def test_timing_is_precautionary_and_large_sync_never_acquires(self):
        self.assertEqual(transfer_estimate_ms(16*1024),4453)
        self.assertGreater(transfer_estimate_ms(80*1024),2500)
        self.f.prepare_receipt();self.manager.receipt['bytes']=80*1024
        self.assertFalse(self.manager.player(self.f.message())['accepted'])
        self.assertNotIn('acquire',[x[0] for x in self.fake.calls])
        self.assertEqual(self.manager.reason,'JSAUX_SYNC_WINDOW')

    def test_independent_has_no_sync_size_gate_and_does_not_rewrite_shuffle(self):
        self.f.prepare_receipt();self.manager.configure({'mode':'async'})
        self.manager.receipt.update(collection_id=self.manager.identity(),bytes=192*1024)
        self.f.installer.install();p=self.f.message();p['mode']='async'
        self.assertTrue(self.manager.player(p)['accepted'])
        self.assertTrue(self.service.catalog.options()['shuffle'])

    def test_delayed_independent_steam_read_waits_before_one_acquire(self):
        self.f.prepare_receipt();self.fake.current['steam']['observed']='inactive'
        timer=threading.Timer(.12,lambda:self.fake.current['steam'].update(observed='active'))
        timer.start();self.addCleanup(timer.cancel)
        self.assertTrue(self.manager.player(self.f.message())['accepted'])
        self.assertEqual(sum(x[0]=='acquire' for x in self.fake.calls),1)

    def test_stop_during_read_wait_does_not_acquire_later(self):
        self.f.prepare_receipt();self.fake.current['steam']['observed']='inactive'
        result=[];worker=threading.Thread(target=lambda:result.append(self.manager.player(self.f.message())))
        worker.start();time.sleep(.08)
        self.assertTrue(self.manager.player(self.f.message('stop',2,reason='player-ended'))['accepted'])
        self.fake.current['steam']['observed']='active';worker.join(2)
        self.assertFalse(worker.is_alive());self.assertFalse(result[0]['accepted'])
        self.assertNotIn('acquire',[x[0] for x in self.fake.calls])

    def test_cold_registration_waits_for_validation_without_second_acquire(self):
        self.f.prepare_receipt();calls=[]
        self.fake.register=lambda *a:{'validation_id':'valid1'}
        def operation(**kw):
            calls.append(kw)
            return dict(state='validating') if len(calls)<2 else dict(state='ready',content_id='content1')
        self.fake.operation=operation
        self.assertTrue(self.manager.player(self.f.message())['accepted'])
        self.assertEqual(self.manager.validation,'ready')
        self.assertEqual(sum(x[0]=='acquire' for x in self.fake.calls),1)

    def test_revalidation_rate_limit_is_readable_and_recoverable(self):
        self.f.prepare_receipt();count=[]
        def register(*a):
            count.append(1)
            if len(count)==1:raise BrokerError('RATE_LIMITED',50)
            return {'content_id':'content1'}
        self.fake.register=register
        self.assertTrue(self.manager.player(self.f.message())['accepted'])
        self.assertEqual(len(count),2)

    def test_heartbeat_copies_existing_wire_state_axes_and_retry(self):
        self.f.prepare_receipt();self.manager.player(self.f.message())
        self.fake.operation=lambda **kw:dict(lease_state='active',reason='FLASH_DEFERRED',retry_after_ms=60000,
            transfer_state='deferred',alignment_state='unconfirmed',restore_state='deferred')
        self.manager.player(self.f.message('heartbeat',2));s=self.manager.status()
        self.assertEqual(s['retry_after_ms'],60000);self.assertEqual(s['alignment_state'],'unconfirmed')
        self.assertEqual(s['restore_state'],'deferred')

    def test_failed_renewal_recovers_original_revocation_without_retry_or_acquisition(self):
        self.f.prepare_receipt();self.assertTrue(self.manager.player(self.f.message())['accepted'])
        self.manager.session['renew_at']=0;before=list(self.fake.calls);reads=[]
        def expired(**kw):raise BrokerError('LEASE_EXPIRED')
        def operation(**kw):
            reads.append(kw);return dict(lease_state='preempted',reason='STEAM_INACTIVE',restore_state='confirmed',transfer_state='confirmed')
        self.fake.renew=expired;self.fake.operation=operation
        reply=self.manager.player(self.f.message('heartbeat',2))
        self.assertFalse(reply['accepted']);self.assertEqual(reply['reason'],'STEAM_INACTIVE')
        self.assertEqual(len(reads),1);self.assertEqual(self.fake.calls,before)
        self.assertEqual(self.manager.last_evidence['reason'],'STEAM_INACTIVE')
        self.assertTrue(self.manager.session['terminal'])
        events=self.manager.diagnostic_snapshot()['events']
        self.assertTrue(any(e['event']=='player-refused' and e['reason']=='LEASE_EXPIRED' for e in events))
        self.assertTrue(any(e['event']=='player-revocation' and e['reason']=='STEAM_INACTIVE' for e in events))

    def test_revocation_evidence_read_failure_preserves_original_refusal_and_never_retries(self):
        self.f.prepare_receipt();self.assertTrue(self.manager.player(self.f.message())['accepted'])
        self.manager.session['renew_at']=0;before=list(self.fake.calls)
        def expired(**kw):raise BrokerError('LEASE_EXPIRED')
        self.fake.renew=expired;self.fake.operation=expired
        reply=self.manager.player(self.f.message('heartbeat',2))
        self.assertEqual(reply['reason'],'LEASE_EXPIRED');self.assertEqual(self.fake.calls,before)
        self.assertTrue(self.manager.session['terminal'])

    def test_panel_selection_crop_are_independent_of_tv(self):
        self.f.prepare_receipt();before=self.service.catalog.get(620)
        self.service._candidates[(620,'panel')]=[dict(id=123,width=512,height=512,animated=False)]
        self.service.choose(620,123,'panel');self.service.update_game(620,{'faceplate_crop':{'x':12,'y':84}})
        after=self.service.catalog.get(620)
        self.assertEqual(after.get('asset'),before.get('asset'));self.assertEqual(after.get('pending_change'),before.get('pending_change'))
        self.assertEqual(after['panel_asset']['id'],123);self.assertTrue(after['panel_pending'])
        self.assertEqual(after['faceplate_crop'],dict(x=12,y=84))

    def test_matrix_and_tv_share_the_exact_ready_file_set(self):
        self.f.prepare_receipt();game=self.service.catalog.get(620)
        self.service.catalog.managed(game['media']['tv'],True).unlink()
        self.assertEqual(self.manager.games(),[]);self.assertEqual(player_catalog(self.service.catalog)['games'],[])

    def test_discovery_failure_preserves_export_listener_and_recovery_card_state(self):
        self.f.prepare_receipt()
        def failure(*a):raise BrokerError('AUTH_DENIED')
        self.fake.discover=failure;self.manager.refresh();s=self.manager.status()
        self.assertTrue(s['configured']);self.assertFalse(s['detected']);self.assertEqual(s['hardware'],'unknown')
        self.assertTrue(s['relay_enabled']);self.assertTrue(s['enabled'])

    def test_expired_remaining_budget_releases_without_sending_ready(self):
        self.f.prepare_receipt();self.assertTrue(self.manager.player(self.f.message())['accepted'])
        # Use a controlled positive clock; macOS monotonic starts near zero per process.
        now=10000
        with patch('das.jsaux.manager.time.monotonic_ns',return_value=now*1000000):
            result=self.manager.player(self.f.message('ready',2,ready_mono_ms=now-2400,
                deadline_mono_ms=now+100,clock_uncertainty_ms=1))
        self.assertFalse(result['accepted']);self.assertNotIn('ready',[x[0] for x in self.fake.calls])
        self.assertEqual(sum(x[0]=='release' for x in self.fake.calls),1)

    def test_recovery_after_broker_late_start_is_finite_without_ui(self):
        self.fake.discover=lambda *a:(_ for _ in ()).throw(BrokerError('BROKER_UNAVAILABLE'))
        self.manager.recover();time.sleep(.05)
        self.fake.discover=lambda *a:copy.deepcopy(self.fake.current)
        self.manager.recovery_thread.join(2)
        self.assertFalse(self.manager.recovery_thread.is_alive());self.assertTrue(self.manager.compatible)
        self.assertEqual(self.fake.calls,[])

    @unittest.skipUnless(os.environ.get('DAS_TEST_FFMPEG'),'explicit FFmpeg required')
    def test_actual_prepared_native_pixels_change_with_crop_without_tv_reconversion(self):
        from PIL import Image
        from das.studio.media import Media
        self.service.compiler=Media(str(Path(os.environ['DAS_TEST_FFMPEG']).resolve()))
        source=self.service.catalog.managed('wide.png')
        image=Image.new('RGB',(108,54),'red');image.paste('blue',(54,0,108,54));image.save(source)
        game=self.service.catalog.get(620);before=copy.deepcopy(game['media']);media=dict(before,panel_source='wide.png')
        self.service.catalog.update(620,dict(media=media))
        self.manager.configure({'enabled':True,'mode':'async','transition':'none'})
        results=[]
        for x in (0,100):
            self.service.update_game(620,{'faceplate_crop':dict(x=x,y=50)})
            self.manager._prepare();self.assertEqual(self.manager.reason,'')
            results.append(self.service.catalog.managed(self.manager.receipt['path'],True).read_bytes())
        self.assertNotEqual(results[0],results[1]);self.assertEqual(self.service.catalog.get(620)['media']['tv'],before['tv'])
