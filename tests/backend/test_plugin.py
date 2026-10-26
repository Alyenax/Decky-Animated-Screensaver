import asyncio
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
from das.provider import Provider,_trusted_url,SteamGridDBError
from das.library import _steam_home,installed_games
from das.core.catalog import file_sha256,ScreensaverError
from das.studio.storage import validate
from das.studio.installer import MARKER

ROOT=Path(__file__).resolve().parents[2]
GIF=base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')

class Codec:
    lease_fd=None
    def capabilities(self):return dict(ffmpeg=True,ffprobe=True,native_first=True)
    def configure_runtime(self,*args):pass
    def cancel(self):pass
    def prepare(self,source,work,options,checkpoint,progress,static=False):
        checkpoint();progress('validating',.5);tv=work/'original.gif';tv.write_bytes(source.read_bytes())
        thumb=work/'thumbnail.jpg';thumb.write_bytes(b'\xff\xd8fixture')
        return dict(tv=tv,thumbnail=thumb,original_preserved=True,animated=True,width=1,height=1,duration=1,format='gif')

class PluginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.steam=self.root/'Steam';self.steam.mkdir()
        self.env=patch.dict(os.environ,{'DAS_STEAM_ROOT':str(self.steam)});self.env.start();self.addCleanup(self.env.stop)
        stub=types.SimpleNamespace(DECKY_PLUGIN_SETTINGS_DIR=str(self.root/'settings'),DECKY_PLUGIN_DIR=str(ROOT))
        spec=importlib.util.spec_from_file_location('das_plugin_test',ROOT/'main.py');module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'decky':stub}):spec.loader.exec_module(module)
        self.plugin=module.Plugin();await self.plugin._main();self.addAsyncCleanup(self.plugin._unload)
        self.service=self.plugin.service;self.service.compiler=Codec();self.plugin._generation=None
        self.service.games_provider=lambda:[dict(appid=620,name='Portal 2'),dict(appid=730,name='Counter Strike')]
        self.source=self.service.catalog.managed('sources/source.gif');self.source.parent.mkdir();self.source.write_bytes(GIF)
        self.provider=self.plugin.provider;self.provider.save('temporary-test-key-not-valid');self.service.refresh_key_state()
        self.service._assets=lambda number,role:[dict(id=number,animated=True,kind='hero',url='https://cdn.steamgriddb.com/fixture.gif',author='Fixture')] if role=='animation' else []
        self.service._download=lambda asset:self.source
        self.service.configure(dict(show_cover=False,name_display='title'))

    async def call(self,action,**payload):return await self.plugin.studio(action,payload)

    async def test_steam_deck_cold_start_rpc_before_backend_discovery_finishes(self):
        """Decky can invoke RPC during _main's first await, without GCA installed."""
        from das.jsaux.protocol import BrokerError
        plugin=self.plugin.__class__()
        reached=asyncio.Event();resume=asyncio.Event();original_to_thread=asyncio.to_thread
        async def delayed_to_thread(function,*args,**kwargs):
            if (getattr(function,'__self__',None) is getattr(plugin,'installer',None)
                    and getattr(function,'__name__',None)=='status' and args==(True,)):
                reached.set()
                await resume.wait()
            return await original_to_thread(function,*args,**kwargs)
        try:
            with patch('asyncio.to_thread',new=delayed_to_thread):
                starting=asyncio.create_task(plugin._main())
                try:
                    await asyncio.wait_for(reached.wait(),3)
                    with patch.object(plugin.jsaux.broker,'discover',side_effect=BrokerError('BROKER_UNAVAILABLE')):
                        state=await asyncio.wait_for(plugin.studio('state'),3)
                        self.assertEqual(state['version'],'1.0.0')
                        self.assertIn('updates',state)
                        updates=await asyncio.wait_for(plugin.studio('update_status'),3)
                        self.assertIn('channel',updates)
                        refreshed=await asyncio.wait_for(plugin.studio('jsaux_refresh'),3)
                        self.assertFalse(refreshed['jsaux']['detected'])
                finally:
                    resume.set()
                    await asyncio.wait_for(starting,5)
        finally:
            await plugin._unload()

    async def test_terminal_display_evidence_does_not_permanently_block_updater(self):
        self.plugin.jsaux.session={'terminal':True};self.plugin.jsaux.phase='idle'
        self.assertFalse(self.plugin.updater.blocked())
        self.plugin.jsaux.session['terminal']=False
        self.assertTrue(self.plugin.updater.blocked())
        self.plugin.jsaux.session=None;self.plugin.jsaux.phase='restoring'
        self.assertTrue(self.plugin.updater.blocked())
        self.plugin.jsaux.phase='idle'
        self.assertFalse(self.plugin.updater.blocked())

    async def test_paused_preparation_without_worker_blocks_automatic_install(self):
        self.plugin.workspace.data['task']['state']='paused'
        self.assertIn('collection_workflow',self.plugin._activity()['update_blockers'])
        self.plugin.workspace.data['task']['state']='idle';self.service.job['state']='paused_game'
        self.assertIn('tv_preparation',self.plugin._activity()['update_blockers'])
        self.service.job['state']='idle';self.assertFalse(self.plugin.updater.blocked())

    async def test_new_preparation_is_refused_after_update_installation_is_committed(self):
        self.plugin.updater.phase='installing'
        with patch.object(self.plugin.workspace,'start') as start:
            with self.assertRaises(ValueError):await self.call('workspace_prepare',confirm=True)
        start.assert_not_called()
        self.plugin.updater.phase='idle'

    async def test_both_diagnostics_include_actual_work_and_update_blockers(self):
        report=await self.call('diagnostic')
        self.assertIn('activity',report['report'])
        sent=report['report']
        self.assertEqual(sent['workflow']['update_blockers'],[])
        self.assertFalse(sent['workflow']['tv']['worker_active'])
        self.assertFalse(sent['workflow']['workspace']['worker_active'])
        self.assertFalse(sent['jsaux_delivery']['activity']['session_present'])

    async def test_update_waits_for_a_real_final_callback_to_return(self):
        import threading
        release=threading.Event();thread=threading.Thread(target=lambda:release.wait(2));thread.start()
        self.addCleanup(lambda:(release.set(),thread.join(1)))
        self.service.thread=thread;self.service._finished_thread=thread
        self.assertFalse(self.service._busy())
        self.assertTrue(self.plugin.updater.blocked())
        release.set();thread.join(1)
        self.assertFalse(self.plugin.updater.blocked())

    async def test_details_uses_prepared_thumbnail_and_source_preview_is_read_only(self):
        from test_studio import scene
        scene(self.service.catalog)
        details=await self.call('workspace_details',appid=620)
        self.assertTrue(details['thumbnail_url'].startswith('data:image/jpeg;base64,'))
        before=self.service.catalog.path.read_bytes()
        value=await self.call('preview_recipe',appid=620,patch=dict(crop=dict(mode='16:10',x=40,y=60)))
        self.assertEqual(value['count'],1);self.assertEqual(self.service.catalog.path.read_bytes(),before)
        await self.call('close_preview')
        self.assertFalse(self.plugin.preview.transport.files)

    async def test_preview_expected_error_is_data_and_not_python_exception(self):
        value=await self.call('preview_recipe',appid=620,patch=dict(choices={'animation':999}))
        self.assertFalse(value['ok']);self.assertEqual(value['error'],'not_installed')

    async def test_installed_preview_rpc_and_membership_use_real_export_not_new_choices(self):
        from test_studio import scene
        scene(self.service.catalog);self.plugin.installer.install()
        expected=self.service.catalog.get(620)['name']
        self.service.catalog.update(620,dict(name='Unapplied new name',pending_change=True))
        scene(self.service.catalog,730)
        value=await self.call('preview_installed',request_id='p'*32)
        self.assertTrue(value['installed']);self.assertEqual(value['count'],1)
        text=(self.plugin.preview.code/'catalog.js').read_text()
        self.assertEqual(json.loads(text.removeprefix('window.SAS_CATALOG=').removesuffix(';\n'))['games'][0]['name'],expected)
        self.assertNotIn('Unapplied new name',text)
        self.assertTrue((await self.call('workspace_details',appid=620))['installed_in_collection'])
        self.assertFalse((await self.call('workspace_details',appid=730))['installed_in_collection'])
        await self.call('close_preview',request_id='p'*32)
        self.assertIsNone(self.plugin.preview.snapshot)

    async def test_installed_preview_invalid_request_is_a_readable_data_error(self):
        for payload in (dict(appid=True),dict(request_id='bad')):
            value=await self.call('preview_installed',**payload)
            self.assertFalse(value['ok']);self.assertEqual(value['error'],'invalid_setting')

    async def test_candidate_preview_validates_server_owned_identity_and_returns_errors_as_data(self):
        for payload in (dict(appid=620,role=['animation'],asset_id=1,request_id='a'*32),dict(appid=620,role='animation',asset_id=True,request_id='a'*32)):
            value=await self.call('candidate_preview',**payload)
            self.assertEqual(value['error'],'invalid_setting');self.assertFalse(value['ok'])
        value=await self.call('candidate_preview',appid=620,role='animation',asset_id=999,request_id='a'*32,url='http://evil.test/source.gif')
        self.assertEqual(value['error'],'invalid_asset');self.assertFalse(value['ok'])

    async def test_discovery_reads_bypass_mutation_lock_and_never_prepare(self):
        with patch.object(self.plugin,'_lock') as lock,patch.object(self.plugin,'_status',side_effect=AssertionError('No heavy status')),patch.object(self.plugin.discovery,'search',return_value=dict(items=[],total=0)) as search:
            self.assertEqual(await self.call('browse_search',query='Portal'),dict(items=[],total=0))
            lock.__enter__.assert_not_called();search.assert_called_once_with('Portal')

    async def test_expected_top_failure_crosses_decky_as_data_not_python_exception(self):
        from das.studio.steam_http import SteamHTTPError
        with patch.object(self.plugin.discovery,'ranking',side_effect=SteamHTTPError('steam_tls_unavailable','steam_chart')):
            value=await self.call('browse_top')
        self.assertEqual(value,dict(schema='das-discovery-error-v1',ok=False,error='steam_tls_unavailable'))
        report=(await self.call('diagnostic'))['report']
        self.assertIn('discovery',report)
        self.assertTrue(any(e.get('event')=='discovery_error' and e.get('stage')=='steam_chart' for e in report['events']))

    async def test_top_popular_path_survives_a_cold_cache_and_saved_cache(self):
        ranks=dict(response=dict(ranks=[dict(appid=620,rank=1,concurrent_in_game=1000)]))
        names=dict(response=dict(store_items=[dict(appid=620,name='Portal 2',type=0,success=1)]))
        opener=Mock();opener.open.side_effect=[io.BytesIO(json.dumps(v).encode()) for v in (ranks,names)]
        with patch('das.studio.steam_http.build_opener',return_value=opener):
            result=await self.call('browse_top');again=await self.call('browse_top')
        self.assertEqual(result['items'][0]['name'],'Portal 2');self.assertTrue(again['cached'])
        self.assertEqual(opener.open.call_count,2)
        stages={e['stage'] for e in self.plugin.discovery.diagnostic_snapshot()['events']}
        self.assertEqual(stages,{'steam_chart','steam_names'})

    async def test_cold_library_gets_still_and_candidates_before_preparation(self):
        await self.call('workspace_scan')
        page=await self.call('workspace_library',filter='installed')
        portal=next(g for g in page['items'] if g['appid']==620)
        self.assertIn('/620/header.jpg',portal['thumbnail_url']);self.assertFalse(portal.get('media'))
        rows=await self.call('browse_candidates',appid=620,role='animation')
        self.assertEqual(rows[0]['id'],620)
        state=await self.call('workspace_draft',appid=620,patch=dict(choices={'animation':620},collection_member=True,excluded=False))
        self.assertEqual(state['workspace']['draft_count'],1);self.assertFalse(self.service.catalog.get(620).get('media'))

    async def test_collection_rpc_draft_prepare_apply_and_classic_fallback(self):
        state=await self.call('workspace_scan');self.assertEqual(state['workspace']['member_count'],0)
        before=self.service.catalog.path.read_bytes()
        self.service._candidates[(620,'animation')]=self.service._assets(620,'animation')
        state=await self.call('workspace_draft',appid=620,patch=dict(choices={'animation':620},collection_member=True,excluded=False))
        self.assertEqual(state['workspace']['draft_count'],1)
        self.assertEqual(self.service.catalog.path.read_bytes(),before)
        page=await self.call('workspace_library');self.assertEqual(page['total'],1)
        self.assertTrue(page['items'][0]['workspace_draft'])
        with self.assertRaises(ValueError):await self.call('workspace_prepare')
        await self.call('workspace_prepare',confirm=True,language='fr')
        await asyncio.to_thread(self.plugin.workspace.thread.join,4)
        state=await self.call('state')
        self.assertEqual(state['workspace']['task']['state'],'done')
        self.assertEqual(state['installation']['scene_count'],1)
        state=await self.call('workspace_preferences',patch={'mode':'classic'})
        self.assertEqual(state['workspace']['mode'],'classic')
        self.assertEqual((await self.call('library',filter='included'))['total'],1)
        state=await self.call('workspace_preferences',patch={'mode':'collection'})
        self.assertEqual(state['workspace']['mode'],'collection')

    async def test_collection_busy_controls_reject_mutation_but_keep_next_drafts(self):
        await self.call('workspace_scan')
        with patch.object(self.plugin.workspace,'busy',return_value=True):
            for action,payload in [('configure',{'patch':{'scene_seconds':10}}),('remove',{'appid':620,'confirm':True}),('prepare',{}),('update_install',{'confirm':True})]:
                with self.assertRaises(ValueError):await self.call(action,**payload)
            state=await self.call('workspace_draft',appid=620,patch=dict(collection_member=True,excluded=False))
            self.assertEqual(state['workspace']['draft_count'],1)
            await self.call('workspace_preferences',patch={'mode':'classic'})
            await self.call('pause');await self.call('cancel')

    async def test_update_status_is_cached_and_bypasses_library_lock_and_hardware(self):
        expected={'phase':'idle','available':False}
        with patch.object(self.plugin,'_lock') as lock, \
             patch.object(self.plugin,'_status',side_effect=AssertionError('heavy full status forbidden')), \
             patch.object(self.plugin.updater,'status',return_value=expected) as status:
            self.assertEqual(await self.call('update_status'),expected)
            lock.__enter__.assert_not_called();status.assert_called_once_with()
    async def finish(self):
        await asyncio.to_thread(self.service.thread.join,3);self.assertFalse(self.service.thread.is_alive())
        return await self.call('state')

    async def test_local_diagnostic_preserves_safe_frontend_transport_evidence(self):
        relay=dict(schema='das-jsaux-relay-v1',enabled=True,
            iframe=dict(installed=True,received=2,last_error='BACKEND_FAILED',token='do-not-export'),
            storage=dict(available=False,running=False,probes=0),recovery=dict(requested=1,failed=0))
        result=await self.call('diagnostic',relay=relay)
        report=result['report'];local=json.loads(Path(result['path']).read_text())
        self.assertEqual(local,report)
        self.assertEqual(report['relay']['iframe'],dict(installed=True,received=2,last_error='BACKEND_FAILED'))
        self.assertTrue(report['jsaux_delivery']['relay']['iframe']['installed'])
        self.assertNotIn('do-not-export',json.dumps(local))
        self.assertEqual(Path(result['path']).stat().st_mode&0o777,0o600)

    async def test_real_rpc_prepare_install_update_verify_repair_and_coexistence(self):
        self.assertFalse(self.plugin.player_relay.snapshot()['running'])
        for folder in ('animated-screensaver-studio','steam-animated-screensaver'):
            path=self.steam/'config/uioverrides/screensavers'/folder;path.mkdir(parents=True);(path/'keep.txt').write_text('original')
        state=await self.call('scan');self.assertEqual(state['included_count'],2)
        await self.call('prepare');state=await self.finish();self.assertEqual(state['ready_count'],2)
        with self.assertRaises(ValueError):await self.call('install')
        state=await self.call('install',confirm=True,language='fr');self.assertTrue(state['installation']['installed'])
        self.assertFalse(self.plugin.player_relay.snapshot()['running'])
        destination=self.plugin.installer.destination;self.assertEqual(destination.name,'decky-animated-screensaver')
        self.assertTrue((destination/'catalog.js').read_text().startswith('window.SAS_CATALOG='))
        state=await self.call('configure',patch=dict(scene_seconds=30));self.assertTrue(state['installation']['needs_update'])
        await self.call('install',confirm=True)
        receipt=json.loads((destination/MARKER).read_text());media=next(p for p in receipt['files'] if p.startswith('media/'))
        (destination/media).unlink();state=await self.call('inspect_installation');self.assertTrue(state['installation']['needs_repair'])
        self.service._download=Mock(side_effect=AssertionError('No repair download'))
        state=await self.call('repair',confirm=True);self.assertFalse(state['installation']['needs_repair'])
        await self.call('uninstall',confirm=True);self.assertFalse(destination.exists())
        for folder in ('animated-screensaver-studio','steam-animated-screensaver'):
            self.assertEqual((destination.with_name(folder)/'keep.txt').read_text(),'original')

    async def test_pending_replacement_partial_install_retry_only_failed(self):
        await self.call('scan');assets=self.service._assets
        def candidates(number,role):
            if number==730:raise ScreensaverError('Invalid','invalid_media')
            return assets(number,role)
        self.service._assets=candidates
        await self.call('prepare');state=await self.finish();self.assertEqual((state['ready_count'],state['failed_count']),(1,0))
        state=await self.call('install',confirm=True);self.assertEqual(state['installation']['scene_count'],1)
        self.service._assets=assets
        with patch.object(self.service,'_one',wraps=self.service._one) as prepared:
            await self.call('retry');await self.finish();self.assertEqual([row.args[0] for row in prepared.call_args_list],[730])
        self.service._candidates[(620,'animation')]=assets(620,'animation')
        await self.call('choose',appid=620,asset_id=620)
        self.assertEqual((await self.call('state'))['ready_count'],1)
        await self.call('install',confirm=True);self.assertEqual(self.plugin.installer.status()['scene_count'],1)

    async def test_actual_rpc_remove_immediate_details_secret_and_diagnostic(self):
        await self.call('scan');await self.call('prepare');await self.finish()
        with self.assertRaises(ValueError):await self.call('remove',appid=620)
        state=await self.call('remove',appid=620,confirm=True);self.assertEqual(state['game_count'],1)
        self.assertEqual(await self.call('details',appid=620),{})
        diagnostic=await self.call('diagnostic')
        self.assertNotIn(self.provider.key,json.dumps(diagnostic))
        self.assertEqual(self.provider.path.stat().st_mode&0o777,0o600)
        await self.call('save_key',key='');self.assertFalse((await self.call('state'))['key_configured'])

    async def test_idle_status_never_starts_process_network_or_preview(self):
        with patch('subprocess.Popen',side_effect=AssertionError('No idle subprocess')),patch.object(self.provider.opener,'open',side_effect=AssertionError('No idle network')):
            for _ in range(10):await self.call('state')
        self.assertIsNone(self.service.thread);self.assertIsNone(self.plugin.preview.transport.server)

    async def test_connection_retry_forces_metadata_read_without_regenerating_tv(self):
        await self.call('scan')
        await self.call('prepare')
        await self.finish()
        await self.call('install', confirm=True)
        before = self.plugin.installer.status()
        with patch.object(self.plugin.jsaux, 'refresh', return_value=None) as refresh, \
                patch.object(self.plugin.jsaux, 'prepare', side_effect=AssertionError('No faceplate conversion')), \
                patch.object(self.service, 'prepare', side_effect=AssertionError('No TV conversion')):
            state = await self.call('jsaux_refresh', force=True)
            refresh.assert_called_once_with(max_age=0)
            refresh.reset_mock()
            await self.call('jsaux_refresh')
            refresh.assert_called_once_with(max_age=5)
        self.assertEqual(state['ready_count'], 2)
        self.assertEqual(self.plugin.installer.status(), before)

    async def test_old_jsaux_choice_does_not_block_tv_shuffle_when_absent(self):
        self.plugin.jsaux.options.update(configured=True,enabled=True,mode='sync')
        self.plugin.jsaux.detected=False
        state=await self.call('configure',patch={'shuffle':True})
        self.assertTrue(state['options']['shuffle']);self.assertTrue(state['jsaux']['enabled'])

    async def test_game_running_pauses_preparation_suspend_closes_preview(self):
        await self.call('scan');await self.call('session',ids=[620]);await self.call('prepare')
        await asyncio.sleep(.05);self.assertEqual(self.service.job['state'],'paused_game')
        await self.call('suspend');await self.finish();self.assertIsNone(self.plugin.preview.transport.server)
        await self.call('session',ids=[]);await self.call('resume');state=await self.finish();self.assertEqual(state['ready_count'],2)

    async def test_running_game_admission_crosses_rpc_without_an_opaque_exception(self):
        await self.call('session',ids=[620])
        before=self.service.catalog.path.read_bytes()
        for action in ('workspace_prepare','workspace_install'):
            reply=await self.call(action,confirm=True)
            self.assertEqual(reply,dict(schema='das-action-error-v1',ok=False,error='GAME_RUNNING'))
            self.assertFalse(self.plugin.workspace.busy())
            self.assertEqual(self.service.catalog.path.read_bytes(),before)
        await self.call('session',ids=[])
        self.assertEqual((await self.call('state'))['activity']['update_blockers'],[])

    async def test_hardware_settings_and_bad_requests_are_rejected(self):
        for patch_value in ({'prepare_faceplate':True},{'triple_sync':True},{'faceplate_mode':'sync'}):
            with self.assertRaises(ValueError):await self.call('configure',patch=patch_value)
        for number in (True,0,2**40,'620'):
            with self.assertRaises(ValueError):await self.call('game',appid=number,patch={})
        with self.assertRaises(ValueError):await self.plugin.studio('state',[])

class ProviderTests(unittest.TestCase):
    def test_root_backend_keeps_using_the_steam_session_user_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);home=root/'steam-user';steam=home/'.local/share/Steam'
            (steam/'steamapps').mkdir(parents=True)
            (steam/'steamapps/appmanifest_620.acf').write_text('"appid" "620"\n"name" "Portal 2"\n')
            with patch.dict(os.environ,{'DECKY_USER_HOME':str(home),'DAS_STEAM_ROOT':''}), \
                    patch('das.library.os.geteuid',return_value=0),patch('das.library.Path.home',return_value=root/'root-home'):
                self.assertEqual(_steam_home(),steam)
                self.assertEqual(installed_games(),[{'appid':620,'name':'Portal 2'}])

    def test_jsaux_package_declares_approved_root_without_serial_driver(self):
        metadata=json.loads((ROOT/'plugin.json').read_text())
        self.assertEqual(metadata['flags'],['root'])
        package=json.loads((ROOT/'package.json').read_text())
        source=(ROOT/'main.py').read_text()
        self.assertIn("VERSION='"+package['version']+"'",source)
        for path in (ROOT/'py_modules/das/jsaux').glob('*.py'):
            text=path.read_text()
            for forbidden in ('import serial','from serial','/dev/ttyUSB','chmod(0o777','sudo '):
                self.assertNotIn(forbidden,text)

    def test_raw_api_animation_type_and_restricted_urls(self):
        raw=dict(id=1,url='https://cdn.steamgriddb.com/file.webp',type='animated',author=dict(name='Artist'))
        self.assertTrue(Provider._asset(raw,'hero')['animated'])
        for url in ('http://cdn.steamgriddb.com/x','https://steamgriddb.com.evil.test/x','https://user@steamgriddb.com/x','https://cdn.steamgriddb.com:444/x'):
            self.assertFalse(_trusted_url(url))
        self.assertTrue(_trusted_url(raw['url']))

    def test_webp_query_type_is_preserved_without_optional_per_row_animation_flags(self):
        raw=dict(id=91,url='https://cdn.steamgriddb.com/hero/fixture.webp',mime='image/webp',width=1920,height=620,author=dict(name='Artist'))
        self.assertTrue(Provider._asset(raw,'hero','animated')['animated'])
        self.assertFalse(Provider._asset(raw,'hero','static')['animated'])
        # WebP is a container, not proof of animation for unrelated raw rows.
        self.assertFalse(Provider._asset(raw,'hero')['animated'])
        with tempfile.TemporaryDirectory() as temporary:
            provider=Provider(Path(temporary)/'key.json');requested=[]
            provider._json_request=lambda url:requested.append(url) or dict(success=True,data=[raw])
            self.assertTrue(provider._search_kind(620,'hero','','animated')[0]['animated'])
            self.assertIn('types=animated',requested[0])

    def test_actual_candidate_pipeline_keeps_animated_webp_for_steam_and_sgdb_ids(self):
        from urllib.parse import urlsplit,parse_qs
        from das.studio.service import StudioService
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);provider=Provider(root/'key.json');provider.save('fixture-only-not-a-real-key');requested=[]
            def response(url):
                requested.append(url);hero='/heroes/' in url
                return dict(success=True,data=[dict(id=91 if hero else 92,url='https://cdn.steamgriddb.com/fixture.webp',mime='image/webp',
                    width=1920 if hero else 1024,height=620 if hero else 1024,score=1,author=dict(name='Fixture'))])
            provider._json_request=response
            service=StudioService(root/'library',steamgriddb=provider);self.addCleanup(service.shutdown)
            # No throttle needed for a deterministic local API fixture.
            service._request=lambda callback:callback()
            for number in (620,-17830):
                service.catalog.update(number,dict(name='Portal 2',status='pending'))
                assets=service._assets(number,'animation')
                self.assertEqual(len(assets),2);self.assertTrue(all(a['animated'] for a in assets))
                self.assertEqual([a['kind'] for a in assets],['hero','grid'])
            for url in requested:
                query=parse_qs(urlsplit(url).query)
                self.assertEqual(query['types'],['animated']);self.assertNotIn('dimensions',query)
            # Cover/square searches remain static; no animated WebP leaks in.
            for role in ('cover','panel'):
                self.assertTrue(all(not a['animated'] for a in service._assets(620,role)))

    def test_key_persists_privately_and_unknown_length_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider=Provider(Path(tmp)/'key.json');provider.save('test-secret-not-a-real-key')
            self.assertEqual(provider.status(),dict(configured=True));self.assertNotIn('key',provider.status())
            self.assertEqual(Provider._content_length(types.SimpleNamespace(headers={})),0)
            with self.assertRaises(ValueError):provider.save('invalid key')
