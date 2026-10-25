"""Controls stay responsive; replacement work never overlaps an old encoder."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from das.studio.service import StudioService
from das.core.catalog import ScreensaverError

class Media:
    def __init__(self): self.stop=threading.Event()
    def capabilities(self): return dict(ffmpeg=True)
    def cancel(self): self.stop.set()

class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.media=Media()
        self.service=StudioService(Path(self.tmp.name)/'library',media=self.media,games_provider=lambda:[])
        self.addCleanup(self.service.shutdown)
        self.service._scanned=True
        self.service.catalog.update(620,dict(name='Portal',status='pending',excluded=False))
    def settled(self):
        deadline=time.monotonic()+4
        while self.service._busy() and time.monotonic()<deadline: time.sleep(.01)
        self.assertFalse(self.service._busy())
    def test_cancel_preserves_cancelled_state_after_decoder_exits_with_signal(self):
        started=threading.Event()
        def one(_):
            started.set(); self.assertTrue(self.media.stop.wait(2))
            raise ScreensaverError('terminated','worker_signal')
        with patch.object(self.service,'_one',side_effect=one):
            self.service.prepare(); self.assertTrue(started.wait(2))
            self.service.control('cancel'); self.settled()
        self.assertEqual(self.service.job['state'],'cancelled')
        self.assertEqual(self.service.job['error'],'')
        self.assertEqual(self.service.job['queue'],[])
    def test_restart_stops_old_work_then_reprepares_without_overlap(self):
        started=threading.Event(); calls=[]; active=0; maximum=0
        def one(number):
            nonlocal active,maximum
            active+=1; maximum=max(maximum,active); calls.append(number)
            try:
                if len(calls)==1:
                    started.set(); self.assertTrue(self.media.stop.wait(2))
                    raise ScreensaverError('terminated','worker_signal')
            finally: active-=1
        with patch.object(self.service,'_one',side_effect=one):
            self.service.prepare(); self.assertTrue(started.wait(2))
            self.service.prepare(); self.settled()
        self.assertEqual(calls,[620,620]); self.assertEqual(maximum,1)
        self.assertEqual(self.service.job['state'],'complete')
    def test_resume_requested_while_old_worker_stops_is_not_lost(self):
        started=threading.Event(); release=threading.Event(); calls=[]
        def one(number):
            calls.append(number)
            if len(calls)==1:
                started.set(); self.assertTrue(release.wait(2))
                raise ScreensaverError('terminated','worker_signal')
        with patch.object(self.service,'_one',side_effect=one):
            self.service.prepare(); self.assertTrue(started.wait(2))
            self.service.control('pause'); self.service.control('resume')
            release.set(); self.settled()
        self.assertEqual(calls,[620,620]); self.assertEqual(self.service.job['state'],'complete')
    def test_cancel_discards_pending_restart(self):
        started=threading.Event(); release=threading.Event(); calls=[]
        def one(number):
            calls.append(number); started.set(); self.assertTrue(release.wait(2))
            raise ScreensaverError('terminated','worker_signal')
        with patch.object(self.service,'_one',side_effect=one):
            self.service.prepare(); self.assertTrue(started.wait(2))
            self.service.prepare(); self.service.control('cancel'); release.set(); self.settled()
        self.assertEqual(calls,[620]); self.assertEqual(self.service.job['state'],'cancelled')
