"""Local diagnostic delivery chain preserves actual hardware evidence."""
import base64
import hashlib
import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock
from das.github import GitHub,API,UpdateError
import test_jsaux as fixtures


class Diagnostic13Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare_receipt();self.manager=self.f.manager

    def test_chain_has_no_usb_confirmation_until_actual_operation_receipt(self):
        report=self.manager.diagnostic_snapshot()
        self.assertTrue(report['stages']['prepared']);self.assertTrue(report['stages']['included_in_steam'])
        self.assertFalse(report['stages']['steam_player_observed'])
        self.assertEqual(report['stages']['usb_receipt'],'not-started')
        self.manager.player(self.f.message())
        self.f.fake.operation=lambda **kw:dict(lease_state='active',transfer_state='confirmed',alignment_state='candidate',
            restore_state='not-needed',reason=None,retry_after_ms=0,event_ages_ms={'ready':6000,'transfer':10})
        self.manager.player(self.f.message('heartbeat',2))
        report=self.manager.diagnostic_snapshot()
        self.assertEqual(report['stages']['usb_receipt'],'confirmed')
        expected=hashlib.sha256(b'operation1').hexdigest()[:16]
        self.assertEqual(report['last_operation']['correlation_id'],expected)
        raw=json.dumps(report)
        for secret in (str(self.f.root),'operation1','lease1','session1','content1','token1'):
            self.assertNotIn(secret,raw)
        self.assertEqual(report['last_operation']['optical_playback'],'not-measured')
