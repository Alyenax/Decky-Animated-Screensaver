"""21 October: state/discovery lock order and delayed player replies."""
import threading
import time
import unittest
from unittest.mock import Mock
from das.jsaux.protocol import BrokerError
import test_jsaux as fixtures

class ReauditManagerTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare_receipt();self.m=self.f.manager

    def test_prepare_discovery_does_not_hold_state_and_stop_invalidates_admission(self):
        m=self.m;entered=threading.Event();release=threading.Event();done=threading.Event();errors=[]
        original=self.f.fake.discover
        def discover(*a):entered.set();assert release.wait(2);return original(*a)
        self.f.fake.discover=discover;m._prepare=Mock()
        def prepare():
            try:m.prepare()
            except BrokerError as e:errors.append(e.code)
            finally:done.set()
        worker=threading.Thread(target=prepare,daemon=True);worker.start();self.assertTrue(entered.wait(2))
        stopped=threading.Event()
        def stop():m.stop();stopped.set()
        stopper=threading.Thread(target=stop,daemon=True);stopper.start()
        try:self.assertTrue(stopped.wait(1),'Stop waited for discovery under state lock')
        finally:release.set()
        worker.join(2);stopper.join(2);self.assertTrue(done.is_set())
        self.assertEqual(['STALE_GENERATION'],errors);m._prepare.assert_not_called()
        self.assertFalse(m.display_busy())

    def test_two_prepares_reserve_one_intent_while_refresh_remains_possible(self):
        m=self.m;entered=threading.Event();release=threading.Event();original=self.f.fake.discover
        def discover(*a):entered.set();assert release.wait(2);return original(*a)
        self.f.fake.discover=discover;m._prepare=Mock()
        worker=threading.Thread(target=m.prepare);worker.start();self.assertTrue(entered.wait(2))
        try:
            with self.assertRaises(BrokerError) as error:m.prepare()
            self.assertEqual('PREPARATION_BUSY',error.exception.code)
            self.assertTrue(m.lock.acquire(timeout=.5));m.lock.release()
        finally:release.set()
        worker.join(2);self.assertFalse(worker.is_alive());m.thread.join(2)
        m._prepare.assert_called_once()

    def test_late_success_or_error_cannot_revive_stopped_or_replacement_session(self):
        for event in ('ready','started','heartbeat'):
            for error in (False,True):
                for replacement in (False,True):
                    with self.subTest(event=event,error=error,replacement=replacement):
                        self.setUp();m=self.m;m.receipt['sync_wait_ms']=15000;self.f.installer.install();self.assertTrue(m.player(self.f.message())['accepted'])
                        entered=threading.Event();release=threading.Event();original=getattr(self.f.fake,{'ready':'ready','started':'tv_started','heartbeat':'operation'}[event])
                        def delayed(**kw):
                            value=original(**kw);entered.set();assert release.wait(2)
                            if error:raise BrokerError('BROKER_UNAVAILABLE')
                            return value
                        name={'ready':'ready','started':'tv_started','heartbeat':'operation'}[event]
                        setattr(self.f.fake,name,delayed)
                        now=time.monotonic_ns()//1000000
                        extra=dict(ready_mono_ms=now,deadline_mono_ms=now+15000,clock_uncertainty_ms=1) if event=='ready' else dict(started_mono_ms=0,outcome='tv-only',candidate_id=None) if event=='started' else {}
                        message=self.f.message(event,2,**extra)
                        worker=threading.Thread(target=lambda:m.player(message));worker.start();self.assertTrue(entered.wait(2))
                        self.f.fake.release=lambda **kw:dict(restore_state='confirmed')
                        m.stop()
                        new=dict(id='new',terminal=False) if replacement else None
                        if new:
                            with m.lock:m.session=new;m.phase='waiting';m.epoch+=1
                        release.set();worker.join(2);self.assertFalse(worker.is_alive())
                        self.assertIs(new,m.session);self.assertEqual('waiting' if new else 'idle',m.phase)
                        if new:self.assertFalse(new['terminal'])
                        else:self.assertFalse(m.display_busy())
                        setattr(self.f.fake,name,original)
                        m.session=None

    def test_lost_acquire_terminal_receipt_finishes_without_worker_or_retry(self):
        for terminal in ('confirmed','unconfirmed','failed','not-needed'):
            m=self.m;m.epoch+=1;epoch=m.epoch;m.opening='lost';m.phase='opening'
            self.f.fake.current['lease']=dict(session_id='lost',lease_id='lease1',generation=1,operation_id='operation1')
            self.f.fake.release=lambda **kw:dict(restore_state=terminal)
            m.reconcile_opening('lost',epoch);m.opening_thread.join(2)
            self.assertFalse(m.opening_thread.is_alive());self.assertEqual(terminal,m.restore_state)
            self.assertIsNone(m.last_operation);self.assertFalse(m.display_busy())
            self.assertFalse(m.return_thread and m.return_thread.is_alive())
            self.assertFalse(any(kind=='acquire' for kind,_ in self.f.fake.calls))

    def test_old_authenticated_stop_cannot_release_a_replacement_activation(self):
        m=self.m;self.assertTrue(m.player(self.f.message())['accepted'])
        entered=threading.Event();release=threading.Event();original=m.stop;results=[]
        def delayed(*a,**kw):entered.set();assert release.wait(2);return original(*a,**kw)
        m.stop=delayed
        worker=threading.Thread(target=lambda:results.append(m.player(self.f.message('stop',2,reason='player-ended'))));worker.start()
        self.assertTrue(entered.wait(2))
        with m.lock:
            m.epoch+=1;new=dict(m.session,id='new');m.session=new;m.phase='waiting'
        release.set();worker.join(2);m.stop=original
        self.assertFalse(worker.is_alive());self.assertIs(new,m.session);self.assertEqual('waiting',m.phase)
        self.assertFalse(results[0]['accepted'])

    def test_stop_during_actual_preparation_registration_cannot_commit_cancelled_receipt(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        import copy
        m=self.m;before=copy.deepcopy(m.receipt);saved=copy.deepcopy(m.store.data)
        entered=threading.Event();release=threading.Event();register=self.f.fake.register
        def delayed(*a,**kw):entered.set();assert release.wait(2);return register(*a,**kw)
        self.f.fake.register=delayed
        self.f.service.compiler.runner=SimpleNamespace(ffmpeg='/fake/ffmpeg',library_path=None)
        self.f.service._assets=lambda *a:[]
        with patch('das.jsaux.manager.capture',return_value=bytes((20,40,60))*(64*54)):
            m.prepare();self.assertTrue(entered.wait(2));m.stop();release.set();m.thread.join(2)
        self.assertFalse(m.thread.is_alive());self.assertEqual(before,m.receipt)
        self.assertEqual(saved.get('jsaux_collection'),m.store.data.get('jsaux_collection'))
        self.assertEqual('idle',m.phase);self.assertFalse(m.display_busy())
