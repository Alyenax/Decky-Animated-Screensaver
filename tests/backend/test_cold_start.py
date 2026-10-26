"""Run against source OR an extracted release using DAS_AUDIT_PLUGIN_ROOT.

The tests use real DAS imports and a temporary Steam/homebrew layout, without
GCA, USB hardware, network downloads or the host's Steam installation.
"""
import asyncio
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(os.environ.get('DAS_AUDIT_PLUGIN_ROOT',Path(__file__).resolve().parents[2])).resolve()

class ColdStartTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.contexts=ExitStack();self.addCleanup(self.contexts.close)
        self.home=Path(self.tmp.name)/'deck';self.home.mkdir()
        self.steam=self.home/'.local/share/Steam';self.steam.mkdir(parents=True)
        (self.home/'.steam').mkdir();(self.home/'.steam/steam').symlink_to(self.steam)
        self.settings=self.home/'homebrew/settings/Decky-Animated-Screensaver'
        self.contexts.enter_context(patch.dict(os.environ,{'HOME':str(Path(self.tmp.name)/'root'),
            'DECKY_USER_HOME':str(self.home),'DAS_STEAM_ROOT':''}))
        stub=types.SimpleNamespace(DECKY_PLUGIN_SETTINGS_DIR=str(self.settings),DECKY_PLUGIN_DIR=str(ROOT))
        self.contexts.enter_context(patch.dict(sys.modules,{'decky':stub}))
        spec=importlib.util.spec_from_file_location('das_cold_start',ROOT/'main.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.plugin=self.module.Plugin();self.addAsyncCleanup(self.plugin._unload)

    async def stalled_start(self):
        reached=asyncio.Event();resume=asyncio.Event();original=asyncio.to_thread
        async def delayed(function,*args,**kwargs):
            if (getattr(function,'__self__',None) is getattr(self.plugin,'installer',None)
                and getattr(function,'__name__',None)=='status' and args==(True,)):
                reached.set();await resume.wait()
            return await original(function,*args,**kwargs)
        self.contexts.enter_context(patch('asyncio.to_thread',new=delayed))
        task=asyncio.create_task(self.plugin._main())
        await asyncio.wait_for(reached.wait(),3)
        # A real missing endpoint exercises the production BrokerError class.
        self.plugin.jsaux.broker.runtime=Path(self.tmp.name)/'no-gca'
        return task,resume

    async def test_all_four_early_rpcs_without_gca(self):
        task,resume=await self.stalled_start()
        try:
            for action in ('state','jsaux_refresh','jsaux_recover','update_status'):
                with self.subTest(action=action):
                    reply=await asyncio.wait_for(self.plugin.studio(action),3)
                    if action=='update_status':self.assertIn('channel',reply)
                    else:
                        self.assertEqual(reply['version'],'1.0.0');self.assertIn('updates',reply)
                        self.assertFalse(reply['jsaux']['detected'])
        finally:
            resume.set();await asyncio.wait_for(task,5)

    async def test_rpc_before_main_is_retryable_data(self):
        reply=await self.plugin.studio('state')
        self.assertEqual(reply,dict(schema='das-action-error-v1',ok=False,error='backend_starting'))

    async def test_root_user_paths_and_restart_preserve_settings_without_gca(self):
        await self.plugin._main()
        self.assertEqual(self.plugin.installer.boundary.steam_root,self.steam.resolve())
        self.assertEqual(self.plugin.root,self.settings/'library')
        self.assertTrue(self.plugin.root.is_dir())
        self.assertFalse((Path(os.environ['HOME'])/'.local/share/Steam').exists())
        await self.plugin.studio('configure',{'patch':{'scene_seconds':37}})
        # A former GCA installation's preferences must survive its absence.
        await self.plugin.studio('jsaux_configure',{'patch':{'enabled':True}})
        catalog=self.plugin.service.catalog.path.read_bytes()
        await self.plugin._unload()
        self.plugin=self.module.Plugin();self.addAsyncCleanup(self.plugin._unload)
        await self.plugin._main()
        state=await self.plugin.studio('jsaux_refresh',{'force':True})
        self.assertEqual(state['options']['scene_seconds'],37)
        self.assertTrue(state['jsaux']['enabled']);self.assertFalse(state['jsaux']['detected'])
        self.assertEqual(self.plugin.service.catalog.path.read_bytes(),catalog)
        # TV-only installation remains possible with no prepared JSAUX receipt.
        from test_studio import scene
        scene(self.plugin.service.catalog)
        result=await self.plugin.studio('install',{'confirm':True})
        self.assertTrue(result['installation']['installed'])
        marker=self.plugin.installer.destination/'.decky-animated-screensaver.json'
        self.assertIsNone(json.loads(marker.read_text())['jsaux'])
        for path in self.plugin.installer.destination.rglob('*'):
            self.assertTrue(path.stat().st_mode & 0o004)

    async def test_unavailable_jsaux_service_does_not_break_tv_rpcs(self):
        task,resume=await self.stalled_start()
        try:
            error=self.module.BrokerError
            for code in ('BROKER_UNAVAILABLE','AUTH_DENIED','VERSION_UNSUPPORTED'):
                with self.subTest(code=code),patch.object(self.plugin.jsaux.broker,'discover',side_effect=error(code)):
                    state=await self.plugin.studio('jsaux_refresh',{'force':True})
                    self.assertEqual(state['jsaux']['reason'],code)
                    self.assertFalse(state['jsaux']['detected'])
                    self.assertIn('updates',await self.plugin.studio('state'))
        finally:
            resume.set();await asyncio.wait_for(task,5)

    async def test_partial_initialization_refuses_rpc_without_attribute_error(self):
        self.plugin.service=object();self.plugin._closed=False
        reply=await self.plugin.studio('update_status')
        self.assertEqual(reply['error'],'backend_starting')
        # Remove the artificial dependency before real unload.
        del self.plugin.service

    async def test_settings_permission_failure_is_actionable_and_traceback_is_preserved(self):
        with patch.object(self.module,'recover_settings',side_effect=PermissionError('fixture-private-path')):
            with self.assertRaises(PermissionError):await self.plugin._main()
        reply=await self.plugin.studio('state')
        self.assertEqual(reply['error'],'backend_storage')
        self.assertNotIn('fixture-private-path',json.dumps(reply))

    async def test_optional_updater_storage_failure_keeps_tv_usable(self):
        with patch.object(self.module,'Updater',side_effect=OSError('fixture-update-path')):
            await self.plugin._main()
        state=await self.plugin.studio('state')
        self.assertIn('updates',state);self.assertFalse(state['jsaux']['detected'])
        self.assertEqual(state['updates']['error'],'update_storage')

    async def test_old_gca_export_survives_gca_removal_and_can_be_rebuilt_for_tv(self):
        from test_studio import scene
        await self.plugin._main();scene(self.plugin.service.catalog)
        await self.plugin.studio('jsaux_configure',{'patch':{'enabled':True}})
        descriptor=dict(enabled=True,mode='sync',collection_id='a'*64,sync_wait_ms=2500,
            controller='GabeCubeAura',relay=dict(kind='http-loopback-v1',url='http://127.0.0.1:37680/jsaux/v1/player'))
        # Only the former broker publication is simulated. Steam export bytes,
        # ownership marker, startup and subsequent no-GCA RPCs are real DAS.
        with patch.object(self.plugin.jsaux,'export',return_value=descriptor),\
             patch.object(self.plugin.jsaux,'publish_installed_player',return_value=descriptor):
            await self.plugin.studio('install',{'confirm':True})
        destination=self.plugin.installer.destination
        before={p.name:p.read_bytes() for p in destination.iterdir() if p.is_file()}
        saved=self.plugin.service.catalog.path.read_bytes()
        await self.plugin._unload()
        self.plugin=self.module.Plugin();self.addAsyncCleanup(self.plugin._unload)
        await self.plugin._main()
        for action in ('state','jsaux_refresh','jsaux_recover','update_status'):
            value=await self.plugin.studio(action)
            if action!='update_status':self.assertFalse(value['jsaux']['detected'])
        self.assertEqual(self.plugin.service.catalog.path.read_bytes(),saved)
        self.assertEqual({p.name:p.read_bytes() for p in destination.iterdir() if p.is_file()},before)
        # With no available/prepared panel, the explicit rebuild is TV-only;
        # the user's preference is kept rather than silently disabled.
        result=await self.plugin.studio('install',{'confirm':True})
        self.assertTrue(result['installation']['installed']);self.assertTrue(result['jsaux']['enabled'])
        self.assertIsNone(json.loads((destination/'.decky-animated-screensaver.json').read_text())['jsaux'])

if __name__=='__main__':unittest.main()
