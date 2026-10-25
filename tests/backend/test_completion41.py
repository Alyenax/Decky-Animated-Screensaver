"""Missing player stop must not leave a ghost session blocking preparation."""
import threading
import time
import unittest
from unittest.mock import patch
import test_jsaux as fixtures
from test_studio import scene
from das.jsaux.protocol import BrokerError


class Completion41Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.manager=self.f.manager;self.fake=self.f.fake
        def released(**payload):
            self.fake.calls.append(('release',payload));return dict(restore_state='confirmed')
        self.fake.release=released

    def open(self,session_id='session1'):
        self.f.prepare_receipt()
        self.assertTrue(self.manager.player({**self.f.message(),'session_id':session_id})['accepted'])
        self.manager.phase='active'
        return self.manager.session

    def test_missing_stop_releases_once_and_unblocks_without_acquire_or_upload(self):
        self.open();before=list(self.fake.calls)
        self.manager.last_player=time.monotonic()-9
        self.assertTrue(self.manager.expire_session())
        self.assertIsNone(self.manager.session);self.assertEqual(self.manager.phase,'idle')
        self.assertFalse(self.manager.display_busy());self.assertFalse(self.manager.busy())
        self.assertFalse(self.manager.expire_session())
        self.assertEqual([kind for kind,_ in self.fake.calls[len(before):]],['release'])
        self.assertTrue(any(e['event']=='player-heartbeat-timeout' for e in self.manager.events))

    def test_watchdog_fires_without_ui_poll_or_another_player_message(self):
        released=threading.Event()
        def release(**payload):
            self.fake.calls.append(('release',payload));released.set();return dict(restore_state='confirmed')
        self.fake.release=release
        with patch('das.jsaux.manager.PLAYER_HEARTBEAT_TIMEOUT',.05):
            self.open()
            self.assertTrue(released.wait(1))
            self.manager.watchdog_thread.join(1)
            self.assertFalse(self.manager.watchdog_thread.is_alive())
            self.assertIsNone(self.manager.session)

    def test_real_return_stays_blocking_until_broker_confirms_it(self):
        self.open();self.manager.last_player=time.monotonic()-9
        self.fake.release=lambda **payload:dict(restore_state='pending')
        with patch.object(self.manager,'recover'):
            self.assertTrue(self.manager.expire_session())
        self.assertTrue(self.manager.display_busy());self.assertEqual(self.manager.phase,'restoring')
        self.fake.operation=lambda **payload:dict(lease_state='released',restore_state='confirmed')
        self.manager.poll_return()
        self.assertFalse(self.manager.display_busy());self.assertEqual(self.manager.phase,'idle')

    def test_new_preparation_is_not_rejected_by_a_silent_old_player(self):
        self.open();self.manager.last_player=time.monotonic()-9
        scene(self.f.service.catalog,730)
        with patch.object(self.manager,'_prepare') as prepare:
            self.manager.prepare();self.manager.thread.join(1)
        self.assertEqual(prepare.call_count,1)
        self.assertIsNone(self.manager.session)

    def test_ambiguous_release_stays_blocking_until_terminal_wire_evidence(self):
        self.open();self.fake.release=lambda **payload:(_ for _ in ()).throw(BrokerError('UNAVAILABLE'))
        with patch.object(self.manager,'recover'):
            self.manager.stop()
        self.assertTrue(self.manager.display_busy());self.assertEqual(self.manager.phase,'restoring')
        self.fake.operation=lambda **payload:dict(lease_state='active',restore_state='not-needed')
        self.manager.poll_return();self.assertTrue(self.manager.display_busy())
        self.fake.operation=lambda **payload:dict(lease_state='expired',restore_state='confirmed')
        self.manager.poll_return();self.assertFalse(self.manager.display_busy())

    def test_fresh_heartbeat_wins_against_expiration_check(self):
        self.open();self.manager.last_player=time.monotonic()-9
        stop=self.manager.stop
        def refreshed(*args,**kwargs):
            self.manager.last_player=time.monotonic()
            return stop(*args,**kwargs)
        with patch.object(self.manager,'stop',side_effect=refreshed):
            self.assertFalse(self.manager.expire_session())
        self.assertIsNotNone(self.manager.session)
        self.assertFalse(any(kind=='release' for kind,_ in self.fake.calls))

    def test_live_session_is_not_expired_or_misreported_as_preparation(self):
        self.open();self.assertFalse(self.manager.expire_session())
        self.assertTrue(self.manager.display_busy())
        self.assertFalse(self.manager.status()['worker_active'])
        self.assertTrue(self.manager.activity()['watchdog_active'])

    def test_regular_heartbeats_keep_the_watchdog_alive_across_multiple_deadlines(self):
        with patch('das.jsaux.manager.PLAYER_HEARTBEAT_TIMEOUT',.1):
            self.open()
            for sequence in range(2,10):
                time.sleep(.025)
                self.assertTrue(self.manager.player(self.f.message('heartbeat',sequence))['accepted'])
                self.assertIsNotNone(self.manager.session)
            self.assertFalse(any(kind=='release' for kind,_ in self.fake.calls))

    def test_old_watchdog_cannot_close_a_new_activation(self):
        old=self.open();self.manager.stop()
        self.assertTrue(self.manager.player({**self.f.message(),'session_id':'session2'})['accepted'])
        new=self.manager.session;self.manager.last_player=time.monotonic()-9
        self.assertFalse(self.manager.expire_session(old))
        self.assertIs(self.manager.session,new)

    def test_stop_during_acquisition_never_binds_a_late_reply(self):
        self.f.prepare_receipt();acquire=self.fake.acquire
        def stopped(**payload):
            lease=acquire(**payload);self.manager.stop();return lease
        self.fake.acquire=stopped
        self.fake.release=lambda **payload:(_ for _ in ()).throw(BrokerError('UNAVAILABLE'))
        self.assertFalse(self.manager.player(self.f.message())['accepted'])
        self.assertIsNone(self.manager.session);self.assertIsNone(self.manager.watchdog_thread)
        self.assertTrue(any(e['event']=='stale-acquisition-release-failed' for e in self.manager.events))

    def test_late_release_reply_does_not_overwrite_new_session(self):
        self.open();entered=threading.Event();finish=threading.Event();calls=[]
        def release(**payload):
            calls.append(payload)
            if len(calls)==1:entered.set();finish.wait(2)
            return dict(restore_state='pending' if len(calls)==1 else 'confirmed')
        self.fake.release=release
        thread=threading.Thread(target=self.manager.stop);thread.start()
        self.addCleanup(finish.set);self.addCleanup(lambda:thread.join(2))
        self.assertTrue(entered.wait(1))
        self.assertTrue(self.manager.display_busy(),'release in flight still blocks updates')
        self.manager.stop()
        self.assertEqual(self.manager.phase,'releasing','duplicate stop preserves pending release')
        self.assertTrue(self.manager.player({**self.f.message(),'session_id':'session2'})['accepted'])
        new=self.manager.session;finish.set();thread.join(1)
        self.assertIs(self.manager.session,new);self.assertEqual(self.manager.phase,'waiting')
        self.assertIsNone(self.manager.last_operation)

    def test_authenticated_old_player_can_stop_after_working_collection_changes(self):
        self.open();stop=self.f.message('stop',2,reason='player-ended')
        scene(self.f.service.catalog,730)
        self.assertNotEqual(stop['collection_id'],self.manager.identity())
        self.assertFalse(self.manager.player({**stop,'token':'not-the-installed-token'})['accepted'])
        self.assertIsNotNone(self.manager.session)
        self.assertTrue(self.manager.player(stop)['accepted'])
        self.assertIsNone(self.manager.session);self.assertFalse(self.manager.display_busy())

    def test_status_on_idle_manager_does_not_start_watchdog_or_hardware(self):
        before=list(self.fake.calls)
        self.manager.status();self.manager.activity()
        self.assertIsNone(self.manager.watchdog_thread);self.assertEqual(self.fake.calls,before)
