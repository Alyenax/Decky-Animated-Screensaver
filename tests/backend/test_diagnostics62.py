"""Actual guard signal evidence, persisted interruption and paused diagnostic RPC."""
import copy
import json
import os
import signal
import sys
import unittest
from unittest.mock import patch,Mock
import test_studio_controls as fixture
import test_plugin as rpc_fixture
from das.core.catalog import ScreensaverError
from das.core.process_guard import capture,failure_evidence,failure_snapshot
from das.studio.service import StudioService
from das.updates import UpdateError

class FailureEvidenceTests(unittest.TestCase):
    def test_real_payload_signal_is_distinct_from_supervisor_signal_and_redacted(self):
        with self.assertRaises(ScreensaverError) as stopped:
            capture([sys.executable,'-c','import os,signal,sys;print("private-secret-url",file=sys.stderr,flush=True);os.kill(os.getpid(),signal.SIGTERM)'],environment=os.environ,timeout=5,maximum=4096)
        self.assertEqual(stopped.exception.code,'worker_signal')
        evidence=stopped.exception.process_failure
        self.assertEqual(evidence['exit_code'],-signal.SIGTERM);self.assertEqual(evidence['exit_source'],'payload')
        self.assertEqual(evidence['supervisor_exit_code'],-signal.SIGKILL)
        self.assertNotIn('private-secret',json.dumps(evidence));self.assertNotIn('argv',evidence)

    def test_marker_and_persisted_evidence_only_keep_fixed_labels(self):
        value=failure_evidence(['/private/secret/ffprobe','secret-token'],-9,'cinema_memory_limit\n/private/secret\nhttps://private/?key=secret')
        self.assertEqual(value['process'],'ffprobe');self.assertEqual(value['signals'],['memory_limit']);self.assertEqual(value['exit_source'],'supervisor')
        self.assertNotIn('secret',json.dumps(value))
        for malformed in (None,[],dict(process={}),dict(process='secret-path'),dict(process='ffmpeg',exit_source={},exit_code=float('nan'),signals='secret')):
            safe=failure_snapshot(malformed);self.assertNotIn('secret',json.dumps(safe));self.assertNotIn('NaN',json.dumps(safe))

class RetainedFailureTests(unittest.TestCase):
    setUp=fixture.ControlsTests.setUp
    settled=fixture.ControlsTests.settled

    def test_interruption_keeps_queue_and_failure_after_cancel_and_restart(self):
        evidence=failure_evidence(['/private/ffprobe'],-9,'cinema_payload_exit=-11')
        error=ScreensaverError('stopped','runtime_isolation');error.process_failure=evidence
        with patch.object(self.service,'_one',side_effect=error):
            self.service.prepare();self.settled()
        self.assertEqual(self.service.job['state'],'paused');self.assertEqual(self.service.job['queue'],[620])
        failure=self.service.diagnostic_snapshot()['last_failure'];self.assertEqual(failure['appid'],620);self.assertEqual(failure['process'],evidence)
        self.service.control('cancel');self.assertEqual(self.service.diagnostic_snapshot()['last_failure'],failure)
        loaded=StudioService(self.service.root,media=fixture.Media(),games_provider=lambda:[]);self.addCleanup(loaded.shutdown)
        self.assertEqual(loaded.diagnostic_snapshot()['last_failure'],failure)

    def test_snapshot_is_bounded_and_redacts_persisted_arbitrary_fields(self):
        self.service.job.update(last_failure=dict(code='worker_signal',stage='https://secret',at=1,appid=620,argv='secret',process=dict(process='ffprobe',exit_code=-11,signals=['invalid_input','secret'],stderr='secret')),history=[dict(at=1,stage='validating',code='worker_signal',appid=620,name='/private/secret',url='secret')]*100)
        report=self.service.diagnostic_snapshot();self.assertEqual(len(report['history']),24)
        self.assertNotIn('secret',json.dumps(report));self.assertEqual(report['last_failure']['process']['exit_code'],-11)

    def test_failed_automatic_candidate_is_identified_before_it_can_be_committed(self):
        source=self.service.catalog.managed('sources/test.gif');source.parent.mkdir();source.write_bytes(b'GIF89a')
        asset=dict(id=9876,animated=True,width=1920,height=1080,url='https://cdn.steamgriddb.com/private.gif?key=secret',author='secret')
        error=ScreensaverError('stopped','worker_signal');error.process_failure=failure_evidence(['/private/ffprobe'],-9,'cinema_payload_exit=-11')
        with patch.object(self.service,'_assets',return_value=[asset]),patch.object(self.service,'_download',return_value=source),patch.object(self.media,'prepare',side_effect=error,create=True):
            self.service.prepare();self.settled()
        report=self.service.diagnostic_snapshot();self.assertEqual(report['state'],'complete');self.assertEqual(report['skipped_count'],1)
        self.assertEqual(report['last_failure']['asset'],dict(role='background',id=9876,width=1920,height=1080,animated=True,format='gif'))
        self.assertNotIn('secret',json.dumps(report));self.assertFalse(self.service.catalog.get(620).get('asset'))
        self.assertIsNone(self.service.game_details(620)['problem'])
        self.service.control('cancel');self.assertEqual(self.service.diagnostic_snapshot()['last_failure']['asset']['id'],9876)

class DiagnosticRPCTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=rpc_fixture.PluginTests.asyncSetUp
    call=rpc_fixture.PluginTests.call

    async def test_paused_local_report_retains_all_online_fields_and_adds_local_context(self):
        self.service.job.update(state='paused',stage='interrupted',error='worker_signal',completed=26,total=96,appid=322170,
            last_failure=dict(code='worker_signal',stage='validating',at=1,appid=322170,process=failure_evidence(['/private/ffprobe'],-9,'cinema_payload_exit=-11')))
        self.plugin.workspace.data['task'].update(state='paused',stage='tv',error='worker_signal')
        before=copy.deepcopy(self.service.job)
        with patch.object(self.plugin.workspace,'busy',return_value=True),patch.object(self.plugin.jsaux,'refresh',side_effect=AssertionError('No reconnect during snapshot')),patch.object(self.service,'control',side_effect=AssertionError('No cancellation')),patch.object(self.plugin.updater.github,'open',side_effect=AssertionError('No network')):
            result=await self.call('diagnostic')
        report=result['report']
        self.assertTrue(report['workflow']['workspace']['worker_active']);self.assertEqual(report['studio']['completed'],26)
        self.assertEqual(report['studio']['last_failure']['process']['exit_code'],-11)
        for key in ('schema','workflow','studio','discovery','artwork','local_checks','steam_browser','version','stages','relay','last_operation'):
            self.assertIn(key,report,key)
        for key,value in report['jsaux_delivery'].items():
            if key not in {'activity','installation','events'}:self.assertEqual(report[key],value,key)
        self.assertIn('installation',report['jsaux_delivery']);self.assertIn('events',report['jsaux_delivery'])
        for key in ('activity','workspace','jsaux','tools','installation','events','updates'):self.assertIn(key,report)
        self.assertEqual(self.service.job,before)
        self.assertTrue(result['saved']);self.assertEqual(json.loads(self.plugin.root.parent.joinpath('diagnostic.json').read_text()),report)

    async def test_removed_upload_and_auth_rpcs_cannot_collect_or_send_anything(self):
        with patch.object(self.plugin.jsaux,'diagnostic_snapshot') as collect,patch.object(self.plugin.updater.github,'open') as send:
            for action in ('diagnostic_upload','settings_github','update_auth_start','update_auth_poll','update_disconnect'):
                with self.subTest(action=action),self.assertRaises(ValueError):await self.call(action,confirm=True)
            collect.assert_not_called();send.assert_not_called()
        self.assertFalse((self.plugin.root.parent/'diagnostic.json').exists())
