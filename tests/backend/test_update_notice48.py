"""Scheduling settings must not erase an already detected or verified release."""
import tempfile
from pathlib import Path
import unittest
from das.updates import Updater
from test_updates import release

class UpdateNotice48Tests(unittest.TestCase):
    def test_schedule_changes_keep_available_or_verified_release_and_confirmation(self):
        for phase in ('available','ready'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as d:
                root=Path(d);m=Updater(root/'updates',root/'Decky-Animated-Screensaver','0.1.0')
                try:
                    m.release=release('0.2.0',False);m.phase=phase;m.confirmation='verified-token'
                    for patch in ({'interval_minutes':1440},{'auto_check':False},{'channel':'stable'}):
                        m.configure(patch)
                        self.assertTrue(m.status()['available']);self.assertEqual(m.status()['available_version'],'0.2.0')
                        self.assertEqual(m.phase,phase);self.assertEqual(m.confirmation,'verified-token')
                    m.configure({'channel':'beta'})
                    self.assertFalse(m.status()['available']);self.assertEqual(m.phase,'idle');self.assertEqual(m.confirmation,'')
                finally:m.shutdown()
