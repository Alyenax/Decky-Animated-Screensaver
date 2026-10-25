"""Power admission regressions. Measured proxy only, never physical acceptance."""
import copy
import hashlib
import io
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from das.jsaux.collection import compile_pages,preparation_spec
from das.jsaux.gif import encode
from das.jsaux.power import PALETTE,POWER_POLICY,POWER_BUDGET_PPM,MAX_ENERGY,ENERGY,energy,limit_frame
from das.jsaux.protocol import BrokerError
import test_jsaux as fixtures


class Power22Tests(unittest.TestCase):
    def test_safe_pixels_and_black_are_byte_identical(self):
        for frame in (bytes(3456),bytes([0xe0])*3456,bytes([255])*1728+bytes(1728)):
            self.assertLessEqual(energy(frame),MAX_ENERGY)
            self.assertEqual(limit_frame(frame),frame)

    def test_white_has_balanced_channel_averages_deterministic_pixels_and_bounded_energy(self):
        frame=bytes([255])*3456;safe=limit_frame(frame)
        self.assertLessEqual(energy(safe),MAX_ENERGY);self.assertGreater(energy(safe),MAX_ENERGY-300)
        self.assertEqual(safe,limit_frame(frame));self.assertEqual(limit_frame(safe),safe)
        means=[sum(PALETTE[i][channel] for i in safe)/3456 for channel in range(3)]
        self.assertTrue(all(abs(value-127.5)<.03 for value in means),means)
        self.assertGreater(len(set(safe)),1) # balanced native quantisation, not a coarse yellow/grey palette substitution

    def test_tiny_excess_does_not_dim_the_entire_image_or_touch_black(self):
        frame=bytes([255])*1729+bytes(1727);safe=limit_frame(frame)
        self.assertLessEqual(energy(safe),MAX_ENERGY);self.assertEqual(safe[1729:],bytes(1727))
        self.assertLess(sum(a!=b for a,b in zip(frame,safe)),24)

    def test_random_frames_are_safe_and_channel_ratios_are_preserved(self):
        rng=random.Random(22)
        for n in range(32):
            frame=rng.randbytes(3456) if n<16 else bytes(rng.randrange(128,256) for _ in range(3456))
            safe=limit_frame(frame);total=energy(frame)
            self.assertLessEqual(energy(safe),MAX_ENERGY)
            if total<=MAX_ENERGY:self.assertEqual(safe,frame);continue
            for channel in range(3):
                source=sum(PALETTE[i][channel] for i in frame)
                actual=sum(PALETTE[i][channel] for i in safe)
                ideal=source*MAX_ENERGY//total
                self.assertLessEqual(actual,ideal);self.assertLess(ideal-actual,85)

    def test_all_transitions_are_limited_after_composition_and_keep_timing_palette_and_frames(self):
        from PIL import Image
        # Each page is safe alone; their wipe/slide can make a brighter composite.
        pages=[bytes(([255]*32+[0]*32)*54),bytes(([0]*32+[255]*32)*54)]
        for kind in ('fade','slide','wipe','dissolve','none'):
            data,details=compile_pages(pages,24,kind)
            self.assertEqual(details['duration_cs'],4800)
            self.assertEqual(details['power_policy'],POWER_POLICY)
            self.assertLessEqual(details['peak_load_ppm'],POWER_BUDGET_PPM)
            self.assertEqual(data[13:781],bytes(c for rgb in PALETTE for c in rgb))
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.n_frames,details['frames']);duration=0
                for n in range(image.n_frames):
                    image.seek(n);duration+=image.info['duration']
                    self.assertLessEqual(sum(image.convert('RGB').tobytes()),MAX_ENERGY)
                self.assertEqual(duration,48000)

    def test_normalization_checks_cancellation_and_never_returns_partial_output(self):
        count=[0]
        def stop():
            count[0]+=1
            if count[0]==2:raise BrokerError('PREPARATION_CANCELLED')
        with self.assertRaisesRegex(BrokerError,'PREPARATION_CANCELLED'):limit_frame(bytes([255])*3456,stop)

    def test_legacy_receipt_is_unusable_without_background_repair_or_hardware(self):
        f=fixtures.ManagerTests();f.setUp();self.addCleanup(f.doCleanups);f.prepare_receipt()
        old=copy.deepcopy(f.manager.receipt);old.pop('power_policy');old.pop('peak_load_ppm')
        f.manager.receipt=old;f.fake.calls.clear()
        state=f.manager.status()['prepared']
        self.assertFalse(state['ready']);self.assertTrue(state['power_upgrade_required'])
        self.assertEqual(state['reason'],'PREPARATION_POWER_REQUIRED');self.assertIsNone(f.manager.export())
        self.assertEqual(f.fake.calls,[])

    def test_power_repair_uses_cached_cover_without_api_or_download_and_reports_safe_load(self):
        f=fixtures.ManagerTests();f.setUp();self.addCleanup(f.doCleanups);f.prepare_receipt()
        f.manager.receipt.pop('power_policy');f.manager.receipt.pop('peak_load_ppm')
        f.manager.service.compiler.runner=SimpleNamespace(ffmpeg='fixture-not-executed',library_path=None)
        with patch('das.jsaux.manager.capture',return_value=bytes([255])*10368),\
                patch.object(f.service,'_assets',side_effect=AssertionError('No API needed for power repair')),\
                patch.object(f.service,'_download',side_effect=AssertionError('No artwork download')):
            f.manager.prepare();f.manager.thread.join(5)
        state=f.manager.status();self.assertTrue(state['prepared']['ready'],state)
        self.assertFalse(state['prepared']['power_upgrade_required']);self.assertLessEqual(state['prepared']['peak_load_ppm'],500000)
        self.assertGreater(state['prepared']['power_limited_frames'],0)
        self.assertTrue(any(event['event']=='power-checked' for event in f.manager.events))
        self.assertNotIn('acquire',[call[0] for call in f.fake.calls]);self.assertFalse(state['installed'])
        f.installer.install();self.assertTrue(f.manager.status()['installed'])

    def test_power_diagnostic_does_not_export_arbitrary_receipt_text(self):
        f=fixtures.ManagerTests();f.setUp();self.addCleanup(f.doCleanups);f.prepare_receipt()
        f.manager.receipt.update(peak_load_ppm='PRIVATE',source_peak_load_ppm={'PRIVATE':1},power_limited_frames='PRIVATE')
        power=f.manager.diagnostic_snapshot()['prepared']
        self.assertIsNone(power['peak_load_ppm']);self.assertIsNone(power['source_peak_load_ppm']);self.assertIsNone(power['power_limited_frames'])


@unittest.skipUnless(os.environ.get('DAS_TEST_GCA_ROOT'),'explicit actual GCA checkout required')
class ActualGuard22Tests(unittest.TestCase):
    def test_actual_validator_and_coordinator_accept_white_collection_without_brightness_mutation(self):
        sys.path.insert(0,str(Path(os.environ['DAS_TEST_GCA_ROOT'])/'py_modules'))
        self.addCleanup(lambda:sys.path.remove(str(Path(os.environ['DAS_TEST_GCA_ROOT'])/'py_modules')))
        from signalbar.jsaux_broker.validator import validate_bytes
        from signalbar.faceplate.coordinator import FaceplateCoordinator
        class Link:
            def __init__(self,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def command(self,*args,**kwargs):return None
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);coordinator=FaceplateCoordinator(root,root/'state.json',link_factory=Link,
                port_finder=lambda:'fixture',identity_reader=lambda _:'same')
            coordinator.configure(True,100);coordinator.powered=True;coordinator.effective_brightness=100
            calls=[];coordinator._send_protected=lambda link,data,**kwargs:calls.append('upload') or True
            coordinator._write_brightness=lambda *args,**kwargs:self.fail('DAS must not change hardware brightness')
            # Reproduce the actual pre-USB refusal with an old valid white GIF.
            unsafe=encode(64,54,PALETTE,[bytes([255])*3456]*2,delay_cs=[100,100])
            old_meta=validate_bytes(unsafe)
            refused=coordinator.synchronize_scene(unsafe,'screensaver','old',peak_load=old_meta['peak_load'],delegated=True)
            self.assertEqual(refused['policy_reason'],'CONTENT_INVALID');self.assertEqual(calls,[])
            data,details=compile_pages([bytes([255])*3456],24,'none')
            measured=validate_bytes(data)
            self.assertLessEqual(measured['peak_load'],.50)
            result=coordinator.synchronize_scene(data,'screensaver',hashlib.sha256(data).hexdigest(),peak_load=measured['peak_load'],delegated=True)
            self.assertTrue(result['synchronized'],result);self.assertEqual(calls,['upload'])
            self.assertEqual(coordinator.brightness,100);self.assertEqual(coordinator.effective_brightness,100)
