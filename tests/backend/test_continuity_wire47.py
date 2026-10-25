"""Actual DAS manager + client + Unix GCA server, simulated hardware only."""
import time
import unittest
from unittest.mock import patch
from das.jsaux.protocol import BrokerError
import test_jsaux as fixtures
import test_jsaux_interop as interop

@unittest.skipUnless(interop.GCA,'explicit DAS_TEST_GCA_ROOT required')
class ContinuityWireTests(unittest.TestCase):
    setUp=interop.InteropTests.setUp

    def test_lost_renew_reply_recovers_actual_lease_without_second_acquire_or_gif(self):
        f=fixtures.ManagerTests();f.setUp();self.addCleanup(f.doCleanups)
        f.prepare_receipt();m=f.manager;m.broker=self.client
        self.assertTrue(m.player(f.message())['accepted'])
        now=time.monotonic_ns()//1000000
        self.assertTrue(m.player(f.message('ready',2,ready_mono_ms=now,deadline_mono_ms=now+2500,clock_uncertainty_ms=1))['accepted'])
        lease=self.broker.lease;operation=lease['operation_id'];m.session['renew_at']=0
        original=self.client.renew
        def lost(**kw):
            original(**kw);self.client.close()
            raise BrokerError('BROKER_UNAVAILABLE',uncertain=True)
        with patch.object(self.client,'renew',side_effect=lost):
            result=m.player(f.message('heartbeat',3))
        self.assertTrue(result['retryable']);self.assertEqual(lease['sequence'],1)
        result=m.player(f.message('heartbeat',4))
        self.assertTrue(result['accepted']);self.assertEqual(lease['sequence'],2)
        self.assertEqual(m.session['operation_id'],operation)
        kinds=[kind for kind,_ in self.hardware.commands]
        self.assertEqual(kinds,['reserve','submit'])
        m.player(f.message('stop',5,reason='visibility-hidden'))
        self.assertEqual(m.player_end_reason,'visibility-hidden')
        self.assertEqual([kind for kind,_ in self.hardware.commands],['reserve','submit','cancel','restore'])
