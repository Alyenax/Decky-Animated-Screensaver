"""15-game capacity and extended start regressions; never physical USB proof."""
import copy
import io
import random
import time
import unittest
from das.jsaux.collection import PALETTE,compile_pages,transfer_estimate_ms
from das.jsaux.power import limit_frame
from das.jsaux.protocol import BrokerError,validate_hello
import test_jsaux as fixtures


class Collection13Tests(unittest.TestCase):
    def test_fifteen_high_entropy_images_keep_all_pages_palette_and_timing(self):
        from PIL import Image
        rng=random.Random(142)
        pages=[rng.randbytes(3456) for _ in range(15)]
        for kind in ('fade','slide','dissolve'):
            with self.subTest(transition=kind):
                data,meta=compile_pages(pages,24,kind)
                self.assertLessEqual(len(data),196608)
                self.assertTrue(meta['transition_optimized'])
                self.assertEqual(meta['pages'],15)
                self.assertEqual(meta['duration_cs'],15*2400)
                # Async capacity is preserved, not advertised as sync-safe.
                self.assertGreater(transfer_estimate_ms(len(data)),15000)
                with Image.open(io.BytesIO(data)) as image:
                    self.assertEqual(image.n_frames,meta['frames'])
                    total=0
                    for frame in range(image.n_frames):
                        image.seek(frame);total+=image.info['duration']
                        if frame%(meta['transition_steps']+1)==0:
                            page=limit_frame(pages[frame//(meta['transition_steps']+1)])
                            expected=bytes(c for index in page for c in PALETTE[index])
                            self.assertEqual(image.convert('RGB').tobytes(),expected)
                    self.assertEqual(total,15*24000)

    def test_small_collections_keep_original_transition_density(self):
        _,meta=compile_pages([bytes(3456),bytes([255])*3456],24,'fade')
        self.assertEqual(meta['transition_steps'],8)
        self.assertFalse(meta['transition_optimized'])

    def test_cancel_is_checked_inside_transitions_and_never_returns_partial_gif(self):
        calls=[]
        def cancel():
            calls.append(1)
            if len(calls)==4:raise BrokerError('PREPARATION_CANCELLED')
        with self.assertRaisesRegex(BrokerError,'PREPARATION_CANCELLED'):
            compile_pages([bytes(3456),bytes([255])*3456],24,'fade',checkpoint=cancel)

    def test_revision3_remains_explicitly_limited_and_revision4_is_bounded(self):
        value=fixtures.hello();validate_hello(value)
        old=copy.deepcopy(value);old['contract_revision']=3
        old['limits'].update(sync_wait_ms=2500,screensaver_min_attempt_interval_ms=600000)
        validate_hello(old)
        old['limits']['sync_wait_ms']=15000
        with self.assertRaises(BrokerError):validate_hello(old)
        value['limits']['sync_wait_ms']=15001
        with self.assertRaises(BrokerError):validate_hello(value)


class ExtendedManager13Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare_receipt();self.manager=self.f.manager
        self.manager.receipt.update(sync_wait_ms=15000,bytes=65536)
        self.f.installer.install()

    def test_large_collection_export_acquire_and_ready_use_the_same_window(self):
        self.assertEqual(self.f.installer.jsaux_export['sync_wait_ms'],15000)
        self.assertTrue(self.manager.status()['prepared']['sync_admissible'])
        self.assertTrue(self.manager.player(self.f.message())['accepted'])
        now=time.monotonic_ns()//1000000
        self.assertTrue(self.manager.player(self.f.message('ready',2,ready_mono_ms=now,
            deadline_mono_ms=now+15000,clock_uncertainty_ms=1))['accepted'])
        self.assertEqual(sum(call[0]=='ready' for call in self.f.fake.calls),1)
        self.manager.stop('player-ended')
        self.assertEqual(sum(call[0]=='release' for call in self.f.fake.calls),1)

    def test_browser_cannot_override_the_installed_window(self):
        self.assertTrue(self.manager.player(self.f.message())['accepted'])
        now=time.monotonic_ns()//1000000
        self.assertFalse(self.manager.player(self.f.message('ready',2,ready_mono_ms=now,
            deadline_mono_ms=now+2500,clock_uncertainty_ms=1))['accepted'])
        self.assertNotIn('ready',[call[0] for call in self.f.fake.calls])

    def test_broker_upgrade_does_not_promise_new_budget_for_old_prepared_export(self):
        self.manager.receipt['sync_wait_ms']=2500
        status=self.manager.status()['prepared']
        self.assertEqual(status['sync_wait_ms'],2500)
        self.assertFalse(status['sync_admissible'])
