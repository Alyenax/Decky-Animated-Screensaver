"""Heartbeat recovery uses the same lease, never another upload/acquisition."""
import threading
import time
import unittest
from unittest.mock import patch
from das.jsaux.protocol import BrokerError
from das.jsaux.player_relay import safe_reply
import test_jsaux as fixture

class HeartbeatContinuityTests(unittest.TestCase):
    def setUp(self):
        f=fixture.ManagerTests();f.setUp();self.addCleanup(f.doCleanups);f.prepare_receipt()
        self.f=f;self.m=f.manager
        self.assertTrue(self.m.player(f.message())['accepted'])

    def hb(self,seq=2):return self.m.player(self.f.message('heartbeat',seq))

    def test_single_lost_read_recovers_same_session_without_acquire_or_ready(self):
        m=self.m;session=m.session;operation=self.f.fake.operation;calls=[]
        def fail(**p):calls.append(p);raise BrokerError('BROKER_UNAVAILABLE')
        self.f.fake.operation=fail
        first=self.hb();self.assertFalse(first['accepted']);self.assertTrue(first['retryable'])
        self.assertGreater(first['lease_remaining_ms'],0);self.assertFalse(session['terminal'])
        self.assertEqual(m._heartbeat_diagnostic()['state'],'degraded')
        self.f.fake.operation=operation
        result=self.hb(3);self.assertTrue(result['accepted']);self.assertIs(m.session,session)
        self.assertFalse(session['transport_uncertain'])
        self.assertEqual(sum(name=='acquire' for name,_ in self.f.fake.calls),1)
        self.assertEqual(sum(name=='ready' for name,_ in self.f.fake.calls),0)
        self.assertIn('heartbeat-recovered',[e['event']for e in m.events])

    def test_lost_renew_ack_reads_status_then_renews_with_larger_sequence(self):
        m=self.m;s=m.session;s['renew_at']=0
        original=self.f.fake.renew;seen=[]
        def lost(**p):seen.append(p['sequence']);raise BrokerError('BROKER_UNAVAILABLE',uncertain=True)
        self.f.fake.renew=lost;deadline=s['lease_deadline']
        self.assertTrue(self.hb()['retryable']);self.assertEqual(s['lease_deadline'],deadline)
        def renew(**p):seen.append(p['sequence']);return original(**p)
        self.f.fake.renew=renew
        self.assertTrue(self.hb(3)['accepted']);self.assertEqual(seen,[1,2])
        self.assertEqual(sum(name=='acquire' for name,_ in self.f.fake.calls),1)

    def test_persistent_loss_never_extends_the_last_acknowledged_lease(self):
        self.f.fake.operation=lambda **p:(_ for _ in ()).throw(BrokerError('BROKER_UNAVAILABLE'))
        session=self.m.session;deadline=session['lease_deadline']
        self.assertTrue(self.hb()['retryable']);self.assertEqual(session['lease_deadline'],deadline)
        session['lease_deadline']=time.monotonic()-1
        result=self.hb(3);self.assertFalse(result.get('retryable',False));self.assertFalse(result['accepted'])
        self.assertTrue(session['terminal']);self.assertEqual(result['reason'],'LEASE_EXPIRED')

    def test_explicit_denials_and_changed_boot_are_terminal(self):
        for code in ('STALE_BOOT','DISPLAY_OFF','PRIORITY_ACTIVE','AUTH_DENIED','LEASE_EXPIRED'):
            with self.subTest(code=code):
                self.m.session['terminal']=False
                with patch.object(self.f.fake,'operation',side_effect=BrokerError(code)):
                    result=self.hb(self.m.session['sequence']+1)
                self.assertFalse(result.get('retryable',False));self.assertTrue(self.m.session['terminal'])
        self.m.session['terminal']=False;self.m.session['broker_boot']='old'
        self.f.fake.boot='new'
        self.assertEqual(self.hb(self.m.session['sequence']+1)['reason'],'STALE_BOOT')

    def test_stop_during_failed_heartbeat_cannot_modify_replacement(self):
        entered=threading.Event();resume=threading.Event();result=[];m=self.m
        def lost(**p):entered.set();assert resume.wait(2);raise BrokerError('BROKER_UNAVAILABLE')
        with patch.object(self.f.fake,'operation',side_effect=lost):
            worker=threading.Thread(target=lambda:result.append(self.hb()));worker.start();self.assertTrue(entered.wait(1))
            m.stop();replacement=dict(id='replacement',terminal=False)
            with m.lock:m.session=replacement;m.epoch+=1;m.phase='waiting'
            resume.set();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertIs(m.session,replacement);self.assertFalse(replacement['terminal'])
        self.assertFalse(result[0]['accepted']);m.session=None

    def test_stop_reason_is_preserved_without_arbitrary_browser_text(self):
        result=self.m.player(self.f.message('stop',2,reason='visibility-hidden'))
        self.assertTrue(result['accepted']);self.assertEqual(self.m.player_end_reason,'visibility-hidden')
        self.assertIn(('player-stop','visibility-hidden'),[(e['event'],e['reason'])for e in self.m.events])
        self.assertFalse(self.m.player(self.f.message('stop',3,reason='anything-private'))['accepted'])
        for value in ([],{},42,None):self.assertFalse(self.m.player(self.f.message('stop',3,reason=value))['accepted'])
        value=safe_reply(dict(accepted=False,retryable=True,lease_remaining_ms=5000,secret='not-exposed'))
        self.assertTrue(value['retryable']);self.assertEqual(value['lease_remaining_ms'],5000);self.assertNotIn('secret',value)
        self.assertNotIn('lease_remaining_ms',safe_reply(dict(lease_remaining_ms=8001)))

    def test_stale_stop_cannot_overwrite_new_session_end_reason(self):
        m=self.m;entered=threading.Event();resume=threading.Event();original=m.stop;results=[]
        def delayed(*a,**kw):entered.set();assert resume.wait(2);return original(*a,**kw)
        with patch.object(m,'stop',side_effect=delayed):
            worker=threading.Thread(target=lambda:results.append(m.player(self.f.message('stop',2,reason='visibility-hidden'))))
            worker.start();self.assertTrue(entered.wait(1))
            with m.lock:
                m.epoch+=1;m.session=dict(id='replacement',terminal=False);m.player_end_reason='manual-pause'
            resume.set();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertFalse(results[0]['accepted'])
        self.assertEqual(m.player_end_reason,'manual-pause');m.session=None
