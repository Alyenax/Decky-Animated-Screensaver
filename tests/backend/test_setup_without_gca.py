"""Expected setup failures and a former panel must not break TV-only use."""
import asyncio
import copy
import json
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import test_cold_start


class SetupWithoutGCATests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_cold_start.ColdStartTests.asyncSetUp

    async def start(self):
        await self.plugin._main()
        self.plugin.service.catalog.update(620,dict(name='Portal 2',status='pending',
            origin='manual',collection_member=True,excluded=False,installed=False))

    def assert_setup_error(self,value,code):
        self.assertEqual(value,dict(schema='das-action-error-v1',ok=False,error=code))

    async def test_missing_key_is_data_for_direct_api_actions_without_network(self):
        await self.start()
        with patch.object(self.plugin.provider,'_json_request',side_effect=AssertionError('No network without key')):
            for action,payload in (('validate_key',{}),('search',{'query':'Portal'}),('add',{'id':620}),
                                   ('candidates',{'appid':620,'role':'animation'})):
                with self.subTest(action=action):
                    self.assert_setup_error(await self.plugin.studio(action,payload),'key_missing')

    async def test_invalid_key_format_keeps_previous_secret_and_collection(self):
        await self.start()
        await self.plugin.studio('save_key',{'key':'fixture-valid-key-not-real'})
        secret=self.plugin.provider.path.read_bytes();catalog=self.plugin.service.catalog.path.read_bytes()
        for value in ('invalid key','short',None,123):
            with self.subTest(value=value):
                self.assert_setup_error(await self.plugin.studio('save_key',{'key':value}),'steamgriddb_invalid_key')
                self.assertEqual(self.plugin.provider.path.read_bytes(),secret)
                self.assertEqual(self.plugin.service.catalog.path.read_bytes(),catalog)

    async def test_rejected_saved_key_is_data_and_does_not_start_preparation(self):
        await self.start();await self.plugin.studio('save_key',{'key':'fixture-valid-key-not-real'})
        error=self.module.SteamGridDBError('fixture-response-must-stay-private','unauthorized')
        with patch.object(self.plugin.provider,'_json_request',side_effect=error):
            value=await self.plugin.studio('validate_key')
        self.assert_setup_error(value,'steamgriddb_unauthorized')
        self.assertNotIn('fixture-response',json.dumps(value));self.assertIsNone(self.plugin.service.thread)

    async def test_missing_video_tools_is_data_before_decoder_or_worker(self):
        await self.start()
        for ffmpeg,ffprobe,code in ((False,False,'ffmpeg_missing'),(True,False,'ffprobe_missing')):
            with self.subTest(code=code),patch.object(self.plugin.service.compiler,'capabilities',
                 return_value=dict(ffmpeg=ffmpeg,ffprobe=ffprobe,native_first=True)),\
                 patch.object(self.plugin.service.compiler,'ensure_runtime',side_effect=AssertionError('No decoder')):
                self.assert_setup_error(await self.plugin.studio('prepare'),code)
                self.assertIsNone(self.plugin.service.thread)

    async def test_decoder_failure_during_resume_is_data_outside_apply_lock(self):
        await self.start();self.plugin.service.job['state']='paused'
        error=self.module.ScreensaverError('Video tools unavailable','ffmpeg_missing')
        with patch.object(self.plugin.service,'control',side_effect=error):
            self.assert_setup_error(await self.plugin.studio('resume'),'ffmpeg_missing')

    async def test_collection_missing_tools_stays_recoverable_and_does_not_install(self):
        await self.start();before=self.plugin.service.catalog.get(620)
        with patch.object(self.plugin.service.compiler,'capabilities',return_value=dict(ffmpeg=False,ffprobe=False,native_first=True)),\
             patch.object(self.plugin.installer,'install',side_effect=AssertionError('No incomplete install')):
            reply=await self.plugin.studio('workspace_prepare',{'confirm':True})
            self.assertIn('job',reply)
            await asyncio.to_thread(self.plugin.workspace.thread.join,3)
            self.assertFalse(self.plugin.workspace.busy())
        self.assertEqual(self.plugin.workspace.data['task']['error'],'ffmpeg_missing')
        self.assertEqual(self.plugin.service.catalog.get(620),before)
        self.assertFalse(self.plugin.installer.destination.exists())

    async def test_prepared_tv_can_install_without_key_or_tools(self):
        from test_studio import scene
        await self.start();scene(self.plugin.service.catalog)
        with patch.object(self.plugin.service.compiler,'capabilities',return_value=dict(ffmpeg=False,ffprobe=False,native_first=True)),\
             patch.object(self.plugin.provider,'_json_request',side_effect=AssertionError('No API for prepared TV')):
            value=await self.plugin.studio('install',{'confirm':True})
        self.assertTrue(value['installation']['installed']);self.assertFalse(value['jsaux']['detected'])


class FormerFaceplateExportTests(unittest.TestCase):
    def test_missing_panel_never_starts_a_relay_or_publishes_cached_panel_content(self):
        from test_jsaux import ManagerTests,BrokerError
        for reason in ('BROKER_UNAVAILABLE','DEVICE_ABSENT'):
            with self.subTest(reason=reason):
                fixture=ManagerTests();fixture.setUp()
                try:
                    fixture.prepare_receipt();manager=fixture.manager
                    saved=copy.deepcopy(manager.receipt);options=dict(manager.options)
                    descriptor=dict(kind='http-loopback-v1',url='http://127.0.0.1:37681/jsaux/v1/player')
                    manager.player_relay=SimpleNamespace(descriptor=lambda:descriptor,
                        start=Mock(side_effect=AssertionError('No relay for an absent panel')),close=Mock(),
                        snapshot=lambda:dict(running=False))
                    if reason=='BROKER_UNAVAILABLE':fixture.fake.discover=Mock(side_effect=BrokerError(reason))
                    else:fixture.fake.current['hardware']='absent'
                    # Presence is deliberately stale here. install() itself
                    # must discover the removal before publishing anything.
                    self.assertTrue(manager.detected)
                    self.assertTrue(manager.readiness()['ready'])
                    with patch.object(manager,'publish_installed_player',side_effect=AssertionError('No publication for absent panel')):
                        fixture.installer.install()
                    self.assertFalse(manager.detected)
                    marker=fixture.installer.destination/'.decky-animated-screensaver.json'
                    self.assertIsNone(json.loads(marker.read_text())['jsaux'])
                    self.assertEqual(manager.receipt,saved);self.assertEqual(manager.options,options)
                    manager.player_relay.start.assert_not_called()
                finally:
                    manager.player_relay=None;fixture.doCleanups()
