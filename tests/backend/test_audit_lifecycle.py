import threading
import unittest
from unittest.mock import Mock
from das.jsaux.protocol import BrokerError
import test_jsaux as fixtures

class LifecycleAuditTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare_receipt();self.manager=self.f.manager

    def test_real_client_distinguishes_remote_refusal_from_malformed_mutation_reply(self):
        for value in ([],{},BrokerError('DISPLAY_BUSY')):
            f=fixtures.ClientTests();f.setUp()
            try:
                f.client.discover();f.endpoint.hook=lambda request:value
                with self.assertRaises(BrokerError) as error:
                    f.client.acquire(activation_id='a',session_id='s',content_id='c',collection_id='a'*64,mode='sync')
                self.assertEqual(not isinstance(value,BrokerError),error.exception.uncertain)
                self.assertEqual(1,sum(row['op']=='acquire_display' for row in f.endpoint.calls))
            finally:f.doCleanups()

    def test_definitive_refusal_without_stop_clears_only_its_opening(self):
        manager=self.manager;calls=[]
        def refuse(**kw):calls.append(kw);raise BrokerError('DISPLAY_BUSY')
        self.f.fake.acquire=refuse
        self.assertFalse(manager.player(self.f.message())['accepted'])
        self.assertIsNone(manager.opening);self.assertIsNone(manager.session)
        self.assertFalse(manager.display_busy());self.assertFalse(manager.expire_session())
        self.assertEqual(1,len(calls))

    def test_ambiguous_acquire_uses_metadata_reconciliation_without_retry(self):
        manager=self.manager;entered=threading.Event();release=threading.Event()
        def acquire(**kw):raise BrokerError('BROKER_UNAVAILABLE',uncertain=True)
        self.f.fake.acquire=acquire
        discover=self.f.fake.discover
        def unavailable(*args):
            entered.set();assert release.wait(2)
            return discover(*args)
        # The first discover belongs to open, the second to reconciliation.
        count=[0]
        def delayed(*args):
            count[0]+=1
            return unavailable(*args) if count[0]>1 else discover(*args)
        self.f.fake.discover=delayed
        self.assertFalse(manager.player(self.f.message())['accepted'])
        self.assertTrue(entered.wait(2));self.assertEqual('session1',manager.opening)
        release.set();manager.opening_thread.join(2)
        self.assertFalse(manager.opening_thread.is_alive());self.assertFalse(manager.display_busy())
        self.assertEqual(0,sum(kind=='acquire' for kind,_ in self.f.fake.calls))

    def test_real_stop_tracks_restore_beyond_the_old_finite_recovery_window(self):
        manager=self.manager;self.assertTrue(manager.player(self.f.message())['accepted'])
        now=[0];before=list(self.f.fake.calls)
        def wait(delay):
            now[0]+=delay
            return manager.recovery_stop.is_set()
        manager.recovery_stop.wait=wait
        manager._wait_return=lambda stop,delay:now.__setitem__(0,now[0]+delay) or stop.is_set()
        self.f.fake.release=lambda **kw:dict(restore_state='pending')
        self.f.fake.operation=lambda **kw:dict(lease_state='released',restore_state='confirmed' if now[0]>=27 else 'pending')
        manager.stop()
        worker=getattr(manager,'return_thread',None) or manager.recovery_thread
        worker.join(2)
        self.assertFalse(worker.is_alive());self.assertGreaterEqual(now[0],27)
        self.assertEqual('confirmed',manager.restore_state);self.assertFalse(manager.display_busy())
        self.assertEqual(before,self.f.fake.calls)

    def test_receipt_confirmed_after_27_simulated_seconds_and_broker_outage(self):
        for unavailable in (False,True):
            with self.subTest(unavailable=unavailable):
                manager=self.manager;manager.last_operation='return-a';manager.restore_state='pending';manager.phase='restoring'
                now=[0];reads=[]
                manager._wait_return=lambda stop,delay:now.__setitem__(0,now[0]+delay) or stop.is_set()
                def operation(**kw):
                    reads.append(kw)
                    if unavailable and now[0]<10:raise BrokerError('BROKER_UNAVAILABLE')
                    return dict(lease_state='released',restore_state='confirmed' if now[0]>=27 else 'deferred')
                self.f.fake.operation=operation;register=Mock(side_effect=AssertionError('No registration'))
                manager._registered=register;before=list(self.f.fake.calls)
                manager.follow_return();manager.return_thread.join(2)
                self.assertFalse(manager.return_thread.is_alive());self.assertGreaterEqual(now[0],27)
                self.assertEqual('confirmed',manager.restore_state);self.assertFalse(manager.display_busy())
                self.assertTrue(all(row=={'operation_id':'return-a'} for row in reads))
                self.assertEqual(before,self.f.fake.calls);register.assert_not_called()

    def test_late_receipt_does_not_touch_new_session_or_plugin_shutdown(self):
        for transition in ('new-session','shutdown'):
            with self.subTest(transition=transition):
                manager=self.manager;manager.closed=False;manager.last_operation='old';manager.restore_state='pending';manager.phase='restoring'
                entered=threading.Event();release=threading.Event()
                def operation(**kw):entered.set();assert release.wait(2);return dict(lease_state='released',restore_state='confirmed')
                self.f.fake.operation=operation
                worker=threading.Thread(target=manager.poll_return);worker.start();self.assertTrue(entered.wait(2))
                if transition=='new-session':
                    manager.epoch+=1;manager.last_operation='new';manager.phase='active'
                else:manager.closed=True
                release.set();worker.join(2);self.assertFalse(worker.is_alive())
                self.assertEqual('pending',manager.restore_state)
                self.assertEqual('new' if transition=='new-session' else 'old',manager.last_operation)
        manager.closed=False;manager.last_operation=None;manager.phase='idle'

    def test_unknown_receipt_is_terminal_unconfirmed_and_no_longer_busy(self):
        manager=self.manager;manager.last_operation='lost';manager.restore_state='pending';manager.phase='restoring'
        self.f.fake.operation=lambda **kw:(_ for _ in ()).throw(BrokerError('LEASE_EXPIRED'))
        manager.poll_return()
        self.assertEqual('unconfirmed',manager.restore_state);self.assertFalse(manager.display_busy())
