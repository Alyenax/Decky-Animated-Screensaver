"""Calibration does not prepare media, acquire USB or alter the broker contract."""
import copy
import unittest
from unittest.mock import patch
import test_jsaux as fixtures
from das.jsaux.alignment import calibration_key, correction, reference, saved_calibrations
from das.jsaux.manager import Delegation
from das.jsaux.protocol import BrokerError
from das.jsaux.player_relay import safe_reply


class Alignment25Tests(unittest.TestCase):
    def fixture(self):
        f=fixtures.ManagerTests();f.setUp();self.addCleanup(f.doCleanups)
        f.prepare_receipt();return f

    def test_reference_uses_actual_confirmation_age_not_size_or_poll_arrival(self):
        r=reference({'event_ages_ms':{'candidate':1200}},10000,10004)
        self.assertEqual(r,dict(reference_mono_ms=8802,uncertainty_ms=3,basis='broker-confirmation-event'))
        for ages,sent,end in (({},10000,10004),({'candidate':True},10000,10004),
                ({'candidate':-1},10000,10004),({'candidate':16000},10000,10004),
                ({'candidate':10},10000,10051),({'candidate':10},10001,10000)):
            self.assertIsNone(reference({'event_ages_ms':ages},sent,end))

    def test_http_relay_only_exports_bounded_timing_not_device_or_credentials(self):
        result=safe_reply(dict(accepted=True,alignment_ms=-5000,device_key='secret',capability='secret',
            timing=dict(reference_mono_ms=7000,uncertainty_ms=4,basis='broker-confirmation-event',raw='secret')))
        self.assertEqual(result,dict(accepted=True,alignment_ms=-5000,
            timing=dict(reference_mono_ms=7000,uncertainty_ms=4,basis='broker-confirmation-event')))
        self.assertEqual(safe_reply(dict(alignment_ms=True,timing=dict(reference_mono_ms=-1,uncertainty_ms=40,basis='broker-confirmation-event'))),{})

    def test_calibration_has_bounded_scope_and_signed_steps(self):
        key=calibration_key('port-a','a'*64)
        self.assertNotEqual(key,calibration_key('port-b','a'*64))
        self.assertNotEqual(key,calibration_key('port-a','b'*64))
        self.assertNotIn('port-a',key)
        for v in (-10000,-5000,0,100,10000):self.assertTrue(correction(v))
        for v in (True,1,10001,'500',500.0):self.assertFalse(correction(v))
        self.assertEqual(saved_calibrations({'a'*64:200,'b'*64:True,'private':100}),{'a'*64:200})
        self.assertLessEqual(len(saved_calibrations({f'{n:064x}':100 for n in range(40)})),8)

    def test_save_and_restart_preserve_gif_export_and_routes_without_broker_calls(self):
        f=self.fixture();before=copy.deepcopy(f.manager.receipt);export=f.manager.export_descriptor(True)
        f.fake.calls.clear();f.manager.configure({'alignment_ms':5000})
        self.assertEqual(f.fake.calls,[]);self.assertEqual(f.manager.receipt,before)
        self.assertEqual(f.manager.export_descriptor(True),export)
        other=Delegation(f.service,f.installer,f.fake);self.addCleanup(other.shutdown);other.refresh()
        self.assertEqual(other.calibration_status()['offset_ms'],5000)
        self.assertNotIn('panel',str(f.service.catalog.data.get('jsaux_alignment')))
        report=other.diagnostic_snapshot()
        self.assertEqual(report['calibration']['offset_ms'],5000)
        self.assertNotIn('device_key',str(report['calibration']))
        other.configure({'alignment_ms':0});self.assertEqual(other.calibration_status()['offset_ms'],0)

    def test_other_collection_or_connection_never_inherits_correction(self):
        f=self.fixture();f.manager.configure({'alignment_ms':2500})
        f.fake.current['ownership']['device_key']='other';f.manager.refresh()
        self.assertEqual(f.manager.calibration_status()['offset_ms'],0)
        f.fake.current['ownership']['device_key']='panel';f.manager.refresh()
        self.assertEqual(f.manager.calibration_status()['offset_ms'],2500)
        f.manager.configure({'transition':'slide'})
        self.assertEqual(f.manager.calibration_status()['offset_ms'],0)

    def test_validation_and_live_session_rejection_do_not_revoke_or_upload(self):
        f=self.fixture();f.fake.calls.clear()
        for value in (-10001,12,True,'500'):
            with self.assertRaises(BrokerError):f.manager.configure({'alignment_ms':value})
        f.manager.session={'terminal':False}
        with self.assertRaisesRegex(BrokerError,'PREPARATION_BUSY'):f.manager.configure({'alignment_ms':500})
        self.assertEqual(f.fake.calls,[]);self.assertFalse(f.manager.session['terminal'])
        f.manager.session=None;f.fake.current['hardware']='absent';f.manager.refresh()
        with self.assertRaisesRegex(BrokerError,'DEVICE_ABSENT'):f.manager.configure({'alignment_ms':500})

    def test_open_freezes_correction_and_heartbeat_retains_first_bounded_reference(self):
        f=self.fixture();f.manager.configure({'alignment_ms':-2000})
        result=f.manager.player(f.message());self.assertEqual(result['alignment_ms'],-2000)
        candidate=dict(candidate_id='candidate1',deadline_mono_ms=20000,
                       phase_basis='gif-end-ack-assumption',optical_alignment='unknown')
        value=dict(lease_state='active',transfer_state='confirmed',reason=None,candidate=candidate,
                   event_ages_ms={'candidate':1200})
        with patch.object(f.fake,'operation',return_value=value),patch('das.jsaux.manager.time.monotonic_ns',side_effect=[10000000000,10004000000]):
            reply=f.manager.player(f.message('heartbeat',2))
        self.assertEqual(reply['timing']['reference_mono_ms'],8802)
        with patch.object(f.fake,'operation',return_value=value):
            again=f.manager.player(f.message('heartbeat',3))
        self.assertEqual(reply['timing'],again['timing'])
        self.assertEqual(f.manager.last_alignment['offset_ms'],-2000)
