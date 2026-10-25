import unittest
from das.jsaux.protocol import BrokerError
import test_jsaux_interop as interop
import test_jsaux as fixtures

@unittest.skipUnless(interop.GCA,'explicit DAS_TEST_GCA_ROOT required')
class ReauditWireTests(unittest.TestCase):
    setUp=interop.InteropTests.setUp
    def test_lost_acquire_ack_releases_actual_wire_lease_and_finishes_terminal_receipt(self):
        f=fixtures.ManagerTests();f.setUp()
        try:
            f.prepare_receipt();m=f.manager;m.broker=self.client
            original=self.client.acquire;acquires=[]
            def lost(**kw):
                value=original(**kw);acquires.append(value)
                # Reply is lost to orchestration after actual authenticated RPC.
                self.client.close()
                raise BrokerError('BROKER_UNAVAILABLE',uncertain=True)
            self.client.acquire=lost
            result=m.player(f.message());self.assertFalse(result['accepted'])
            m.opening_thread.join(3);self.assertFalse(m.opening_thread.is_alive())
            self.assertEqual(1,len(acquires));self.assertIsNone(m.opening)
            self.assertEqual('confirmed',m.restore_state);self.assertFalse(m.display_busy())
            self.assertIsNone(m.last_operation);self.assertFalse(m.return_thread and m.return_thread.is_alive())
            kinds=[kind for kind,_ in self.hardware.commands]
            self.assertEqual(['reserve','cancel','restore'],kinds)
        finally:f.doCleanups()
