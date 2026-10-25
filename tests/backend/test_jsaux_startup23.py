"""Startup byte budget, never USB or optical performance claims."""
import random
import unittest
from das.jsaux.collection import compile_pages,_compile_pages,STARTUP_TARGET_BYTES,MAX_BYTES
from das.jsaux.protocol import BrokerError


class Startup23Tests(unittest.TestCase):
    def test_target_reduces_transition_samples_not_games_or_palette_or_duration(self):
        rng=random.Random(23)
        pages=[bytes(rng.randrange(32) for _ in range(3456)) for _ in range(11)]
        old,baseline=_compile_pages(pages,24,'fade',MAX_BYTES,lambda:None)
        data,meta=compile_pages(pages,24,'fade',prefer_small=True)
        self.assertGreater(len(old),STARTUP_TARGET_BYTES)
        self.assertLessEqual(len(data),STARTUP_TARGET_BYTES)
        self.assertLess(meta['transition_steps'],baseline['transition_steps'])
        self.assertEqual(meta['pages'],11);self.assertEqual(meta['duration_cs'],26400)
        self.assertEqual(data[13:781],old[13:781]);self.assertLessEqual(meta['peak_load_ppm'],500000)

    def test_independent_eleven_games_prefers_compact_file_without_dropping_pages(self):
        rng=random.Random(23)
        pages=[bytes(rng.randrange(32) for _ in range(3456)) for _ in range(11)]
        old,baseline=_compile_pages(pages,24,'fade',MAX_BYTES,lambda:None)
        data,meta=compile_pages(pages,24,'fade',prefer_small=False)
        self.assertGreater(len(old),STARTUP_TARGET_BYTES)
        self.assertLessEqual(len(data),STARTUP_TARGET_BYTES)
        self.assertLess(meta['frames'],baseline['frames']);self.assertTrue(meta['transition_optimized'])
        self.assertEqual(meta['pages'],11);self.assertEqual(meta['duration_cs'],26400)
        self.assertEqual(data[13:781],old[13:781]);self.assertLessEqual(meta['peak_load_ppm'],500000)

    def test_soft_target_never_discards_games_and_preserves_established_hard_limit(self):
        rng=random.Random(142);pages=[rng.randbytes(3456) for _ in range(15)]
        with self.assertRaises(BrokerError) as raised:
            compile_pages(pages,24,'fade',prefer_small=True)
        self.assertEqual(raised.exception.code,'JSAUX_SYNC_WINDOW')
        data,meta=compile_pages(pages,24,'fade',prefer_small=False)
        self.assertGreater(len(data),STARTUP_TARGET_BYTES)
        self.assertLessEqual(len(data),MAX_BYTES)
        self.assertEqual(meta['pages'],15);self.assertEqual(meta['duration_cs'],36000)
        self.assertEqual(meta['transition_steps'],1,'Fallback keeps the smallest candidate, not a new dense pass')

    def test_sync_fallback_retains_bitwise_output_of_legacy_two_pass_policy(self):
        rng=random.Random(142);pages=[rng.randbytes(3456) for _ in range(8)]
        with self.assertRaisesRegex(BrokerError,'CONTENT_TOO_LARGE'):
            _compile_pages(pages,24,'fade',STARTUP_TARGET_BYTES,lambda:None)
        legacy=_compile_pages(pages,24,'fade',80*1024,lambda:None)
        current=compile_pages(pages,24,'fade',prefer_small=True)
        self.assertEqual(len(current[0]),73079)
        self.assertEqual(current,legacy)

    def test_cancellation_is_not_mistaken_for_a_capacity_fallback(self):
        calls=[]
        def cancel():calls.append(1);raise BrokerError('PREPARATION_CANCELLED')
        with self.assertRaisesRegex(BrokerError,'PREPARATION_CANCELLED'):
            compile_pages([bytes(3456)],24,'fade',checkpoint=cancel,prefer_small=True)
        self.assertEqual(len(calls),1)
