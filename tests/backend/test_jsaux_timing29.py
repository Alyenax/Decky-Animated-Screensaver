"""Conservative admission is shared, non-destructive and hardware-free."""
import copy
import os
from pathlib import Path
import random
import unittest
from das.jsaux.collection import compile_pages, transfer_estimate_ms
from das.jsaux.timing import admits, SYNC_MAX_BYTES, MODEL
from das.jsaux.protocol import BrokerError
import test_jsaux as fixtures


class Timing29Tests(unittest.TestCase):
    def fixture(self):
        f=fixtures.ManagerTests();f.setUp();self.addCleanup(f.doCleanups)
        f.prepare_receipt();return f

    def test_real_28_game_report_is_refused_before_registration_or_acquisition(self):
        f=self.fixture();m=f.manager
        m.receipt.update(bytes=147518,pages=28,sync_wait_ms=15000)
        before=list(f.fake.calls)
        old=f.service.catalog.managed(m.receipt['path']).read_bytes()
        state=m.status()
        self.assertFalse(state['prepared']['sync_admissible'])
        self.assertGreater(state['prepared']['estimate_ms'],17653)
        self.assertEqual(state['prepared']['sync_max_bytes'],81920)
        for i in range(3):
            message=f.message();message['session_id']='oversized-'+str(i)
            self.assertFalse(m.player(message)['accepted'])
            self.assertEqual(m.reason,'JSAUX_SYNC_WINDOW')
        self.assertEqual(f.fake.calls,before)
        self.assertEqual(old,f.service.catalog.managed(m.receipt['path']).read_bytes())

    def test_same_large_collection_is_still_available_in_independent_mode(self):
        f=self.fixture();m=f.manager
        m.configure({'mode':'async'})
        m.receipt.update(collection_id=m.identity(),bytes=147518)
        f.installer.install()
        message=f.message();message['mode']='async'
        self.assertTrue(m.player(message)['accepted'])
        self.assertEqual(len([c for c in f.fake.calls if c[0]=='acquire']),1)

    def test_80k_is_a_sync_budget_not_a_hardware_or_game_count_limit(self):
        self.assertTrue(admits(SYNC_MAX_BYTES,15000))
        self.assertFalse(admits(SYNC_MAX_BYTES+1,15000))
        self.assertFalse(admits(SYNC_MAX_BYTES,2500))
        data,meta=compile_pages([bytes(3456)]*28,24,'fade',prefer_small=True)
        self.assertEqual(meta['pages'],28) # Low-complexity identities can fit.
        self.assertTrue(admits(len(data),15000))
        self.assertEqual(meta['duration_cs'],28*2400)

    def test_sync_compile_never_falls_back_to_oversized_async_budget(self):
        rng=random.Random(29)
        pages=[rng.randbytes(3456) for _ in range(15)]
        with self.assertRaises(BrokerError) as raised:
            compile_pages(pages,24,'fade',prefer_small=True)
        self.assertEqual(raised.exception.code,'JSAUX_SYNC_WINDOW')
        data,meta=compile_pages(pages,24,'fade',prefer_small=False)
        self.assertLessEqual(len(data),196608)
        self.assertEqual(meta['pages'],15)
        self.assertEqual(meta['duration_cs'],15*2400)

    def test_poll_return_updates_transfer_and_alignment_evidence(self):
        f=self.fixture();m=f.manager
        m.last_operation='ended-operation'
        f.fake.operation=lambda **kwargs:dict(lease_state='expired',transfer_state='unconfirmed',
            alignment_state='abandoned',restore_state='confirmed',reason='ALIGNMENT_EXPIRED')
        m.poll_return()
        self.assertEqual(m.last_transfer,'unconfirmed')
        self.assertEqual(m.alignment,'abandoned')
        self.assertEqual(m.last_evidence['reason'],'ALIGNMENT_EXPIRED')
        self.assertEqual(m.restore_state,'confirmed')
        for reason in ('PLAYER_ENDED','USER_DISABLED','CLIENT_STOPPING'):
            m.last_operation='normal-release'
            f.fake.operation=lambda reason=reason,**kwargs:dict(lease_state='released',
                transfer_state='confirmed',alignment_state='software-coordinated',
                restore_state='confirmed',reason=reason)
            m.poll_return()
            self.assertEqual(m.reason,'')
            self.assertEqual(m.last_evidence['reason'],reason)

    @unittest.skipUnless(os.environ.get('DAS_TEST_GCA_ROOT'),'explicit actual GCA checkout required')
    def test_timing_policy_source_is_identical_in_both_plugins(self):
        ours=Path(__file__).resolve().parents[2]/'py_modules/das/jsaux/timing.py'
        gca=Path(os.environ['DAS_TEST_GCA_ROOT'])/'py_modules/signalbar/faceplate/timing.py'
        self.assertEqual(ours.read_bytes(),gca.read_bytes())
        self.assertEqual(MODEL,'jsaux-measured-envelope-v2')


if __name__=='__main__':unittest.main()
