"""Alpha57 selection/export and primary/optional GCA recovery regressions.

Uses the real workspace, catalog, delegation and transactional installer. Broker
and codec fixtures confer no USB/controller/physical playback evidence.
"""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from das.core.catalog import ScreensaverError, file_sha256
from das.jsaux.manager import Delegation
from das.jsaux.protocol import BrokerError
from das.studio.installer import Installer, player_catalog
from das.studio.membership import included, member
from das.studio.service import StudioService
from das.studio.workspace import CollectionWorkspace
from test_studio import ASSETS, FakeMedia, Provider, scene
import test_jsaux as jsaux_fixtures


class SelectionRecovery57Tests(unittest.TestCase):
    def selection_fixture(self,count=16):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        service=StudioService(root/'studio',steamgriddb=Provider(),media=FakeMedia(),games_provider=lambda:[])
        self.addCleanup(service.shutdown);service._scanned=True
        service.catalog.configure(dict(show_cover=False,show_logo=False,shuffle=False))
        for appid in range(1,count+1):
            scene(service.catalog,appid);service.catalog.update(appid,dict(collection_member=True));service._ready.add(appid)
        steam=root/'Steam';steam.mkdir();installer=Installer(service.catalog,steam,ASSETS)
        delegation=Delegation(service,installer,jsaux_fixtures.FakeClient());self.addCleanup(delegation.shutdown)
        workspace=CollectionWorkspace(service,installer,delegation);self.addCleanup(workspace.shutdown)
        return service,installer,delegation,workspace

    def manager_fixture(self):
        fixture=jsaux_fixtures.ManagerTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        return fixture

    def installed_catalog(self,installer):
        raw=(installer.destination/'catalog.js').read_text()
        self.assertTrue(raw.startswith('window.SAS_CATALOG='))
        return json.loads(raw[len('window.SAS_CATALOG='):-2])

    def test_sixteen_minus_five_is_eleven_in_queue_both_outputs_and_real_export(self):
        service,installer,delegation,workspace=self.selection_fixture()
        files={path:file_sha256(service.catalog.managed(path)) for game in service.catalog.games() for path in game['media'].values()}
        removed={1,4,8,12,16};expected=[i for i in range(1,17) if i not in removed]
        for appid in removed:workspace.save_draft(appid,dict(collection_member=False,excluded=False),reconcile_membership=True)
        self.assertEqual(workspace.summary()['included_count'],11)
        self.assertEqual(workspace.summary()['draft_count'],5)
        workspace.commit()
        self.assertEqual(service.status()['ready_count'],11)
        service._reset_preparation(None,False,False)
        self.assertEqual(service.job['queue'],expected)
        self.assertEqual([g['appid'] for g in delegation.games()],expected)
        catalog=player_catalog(service.catalog)
        self.assertEqual([g['steamAppId'] for g in catalog['games']],expected)
        self.assertEqual(catalog['presentation']['order'],expected)
        self.assertEqual(workspace.summary()['preview_count'],11)
        installer.install();installed=self.installed_catalog(installer)
        self.assertEqual(installed['presentation']['order'],expected)
        self.assertEqual([g['steamAppId'] for g in installed['games']],expected)
        self.assertEqual(installer.status()['scene_count'],11)
        for path,digest in files.items():self.assertEqual(file_sha256(service.catalog.managed(path)),digest)
        self.assertEqual(len(service.catalog.games()),16,'Deselecting retains working artwork records')

    def test_legacy_fallback_exclusion_and_explicit_false_have_one_contract(self):
        cases=[({'media':{'tv':'old.gif'},'excluded':False},True,True),
               ({'media':{'tv':'old.gif'},'excluded':True},True,False),
               ({'excluded':True},False,False),
               ({'collection_member':False,'excluded':False,'media':{'tv':'old.gif'}},False,False),
               ({'collection_member':True,'excluded':True},True,False)]
        for game,want_member,want_included in cases:
            with self.subTest(game=game):
                self.assertEqual(member(game),want_member);self.assertEqual(included(game),want_included)
        service,installer,delegation,workspace=self.selection_fixture(3)
        with service.catalog.lock:
            service.catalog.data['games']['1'].pop('collection_member')
            service.catalog.data['games']['2'].pop('collection_member');service.catalog.data['games']['2']['excluded']=True
            service.catalog.data['games']['3']['collection_member']=False
            service.catalog.save()
        self.assertEqual(workspace.summary()['included_count'],1)
        self.assertEqual([g['appid'] for g in delegation.games()],[1])
        installer.install();self.assertEqual(self.installed_catalog(installer)['presentation']['order'],[1])

    def test_all_removed_retains_previous_export_and_new_empty_export_is_refused(self):
        service,installer,delegation,workspace=self.selection_fixture(3)
        installer.install();before=(installer.destination/'catalog.js').read_bytes()
        for appid in range(1,4):workspace.save_draft(appid,dict(collection_member=False,excluded=False),reconcile_membership=True)
        workspace.start();workspace.thread.join(4)
        self.assertFalse(workspace.busy());self.assertEqual(workspace.summary()['included_count'],0)
        self.assertEqual(service.status()['ready_count'],0);self.assertEqual(delegation.games(),[])
        self.assertEqual(workspace.data['task']['outcome'],'unchanged')
        self.assertEqual((installer.destination/'catalog.js').read_bytes(),before)
        with self.assertRaises(ScreensaverError) as error:installer.install()
        self.assertEqual(error.exception.code,'not_ready')
        self.assertEqual((installer.destination/'catalog.js').read_bytes(),before)

    def test_cancel_after_membership_commit_preserves_installed_snapshot_and_saved_choices(self):
        service,installer,delegation,workspace=self.selection_fixture(3)
        installer.install();before=(installer.destination/'catalog.js').read_bytes()
        workspace.save_draft(1,dict(collection_member=False,excluded=False),reconcile_membership=True)
        entered=threading.Event();release=threading.Event()
        def prepare(*args,**kwargs):entered.set();release.wait(2)
        with patch.object(service,'prepare',side_effect=prepare),patch.object(installer,'install',side_effect=AssertionError('Cancelled workflow cannot install')):
            workspace.start();self.assertTrue(entered.wait(1));workspace.cancel();release.set();workspace.thread.join(3)
        self.assertFalse(workspace.busy());self.assertEqual(workspace.data['task']['state'],'cancelled')
        self.assertEqual(workspace.summary()['included_count'],2)
        self.assertEqual((installer.destination/'catalog.js').read_bytes(),before)
        self.assertFalse(included(service.catalog.get(1)))

    def test_optional_player_status_failure_preserves_fresh_hardware_without_stale_playback(self):
        f=self.manager_fixture();f.prepare_receipt();m=f.manager
        f.installer.jsaux_export={**f.installer.jsaux_export,'controller':'GabeCubeAura',
            'relay':{'kind':'http-loopback-v1','url':'http://127.0.0.1:37680/jsaux/v1/player'}}
        f.fake.hello['capabilities']={'autonomous_player':True}
        m.controller_state={'phase':'active','first_player':True,'last_transfer':'usb-confirmed'}
        receipt=copy.deepcopy(m.receipt);export=copy.deepcopy(f.installer.jsaux_export)
        with patch.object(f.fake,'request',create=True,side_effect=BrokerError('AUTH_DENIED')) as request:
            self.assertEqual(m.refresh()['hardware'],'available')
        request.assert_called_once_with('player_status',dict(token=f.installer.token))
        status=m.status();self.assertTrue(status['detected']);self.assertTrue(status['compatible'])
        self.assertEqual(status['hardware'],'available');self.assertEqual(status['controller_status_error'],'AUTH_DENIED')
        self.assertEqual(m.controller_state,{},'Unavailable optional status cannot preserve a stale active phase')
        self.assertEqual(m.receipt,receipt);self.assertEqual(f.installer.jsaux_export,export)
        self.assertNotIn('acquire',[name for name,*_ in f.fake.calls])
        with patch.object(f.fake,'request',create=True,return_value={'phase':'waiting','reason':''}):m.refresh()
        self.assertEqual(m.status()['controller_status_error'],'');self.assertTrue(m.status()['detected'])

    def test_primary_discovery_failure_clears_detection_and_never_queries_optional_status(self):
        f=self.manager_fixture();f.prepare_receipt();m=f.manager
        f.installer.jsaux_export={**f.installer.jsaux_export,'controller':'GabeCubeAura',
            'relay':{'kind':'http-loopback-v1','url':'http://127.0.0.1:37680/jsaux/v1/player'}}
        f.fake.hello['capabilities']={'autonomous_player':True}
        with patch.object(f.fake,'discover',side_effect=BrokerError('BROKER_UNAVAILABLE')),patch.object(f.fake,'request',create=True,side_effect=AssertionError('No optional read after primary failure')):
            self.assertIsNone(m.refresh())
        status=m.status();self.assertFalse(status['detected']);self.assertFalse(status['compatible'])
        self.assertEqual(status['hardware'],'unknown');self.assertEqual(status['reason'],'BROKER_UNAVAILABLE')
        self.assertTrue(m.receipt['path']);self.assertTrue(m.options['enabled'])

    def test_legacy_broker_without_autonomous_capability_never_gets_player_status(self):
        f=self.manager_fixture();f.prepare_receipt();m=f.manager
        f.installer.jsaux_export={**f.installer.jsaux_export,'controller':'GabeCubeAura',
            'relay':{'kind':'http-loopback-v1','url':'http://127.0.0.1:37680/jsaux/v1/player'}}
        self.assertNotIn('autonomous_player',f.fake.hello.get('capabilities',{}))
        with patch.object(f.fake,'request',create=True,side_effect=AssertionError('Legacy broker has no optional player_status operation')):
            self.assertEqual(m.refresh()['hardware'],'available')
        self.assertTrue(m.status()['detected']);self.assertTrue(m.status()['compatible'])
        self.assertEqual(m.status()['controller_status_error'],'')

    def test_compile_failure_remains_current_across_successful_discovery(self):
        f=self.manager_fixture();f.prepare_receipt();m=f.manager;before=copy.deepcopy(m.receipt)
        # Exercise the real preparation error handler at the codec-lease boundary.
        with patch.object(f.service,'lease',side_effect=BrokerError('CONTENT_TOO_LARGE')):m._prepare()
        self.assertEqual(m.status()['preparation_error'],'CONTENT_TOO_LARGE')
        for _ in range(3):
            self.assertEqual(m.refresh()['hardware'],'available')
            self.assertEqual(m.status()['preparation_error'],'CONTENT_TOO_LARGE')
            self.assertEqual(m.status()['reason'],'CONTENT_TOO_LARGE')
        self.assertEqual(m.receipt,before)
        self.assertTrue(m.status()['detected']);self.assertTrue(m.status()['compatible'])

    def test_independent_change_is_explicit_and_uses_normal_installation_without_usb(self):
        f=self.manager_fixture();f.prepare_receipt();m=f.manager
        f.service._scanned=True;f.service._ready.add(620)
        f.service.catalog.configure(dict(show_cover=False,show_logo=False))
        # Keep this selection's current receipt identity after the visual options.
        m.receipt['collection_id']=m.identity();m.receipt['bytes']=80*1024
        self.assertEqual(m.installation_blocker(),'JSAUX_SYNC_WINDOW')
        workspace=CollectionWorkspace(f.service,f.installer,m);self.addCleanup(workspace.shutdown)
        with patch.object(m,'configure',wraps=m.configure) as configure:
            for _ in range(3):workspace.summary();m.status()
            configure.assert_not_called()
            with patch.object(f.service,'_playing',return_value=True):
                with self.assertRaises(ScreensaverError):workspace.start(independent=True)
            configure.assert_not_called();self.assertEqual(m.options['mode'],'sync')
            with patch.object(m,'busy',return_value=True):
                with self.assertRaises(ScreensaverError):workspace.start(independent=True)
            configure.assert_not_called();self.assertEqual(m.options['mode'],'sync')
            def cached_prepare():
                # Stand in only for the GIF compiler; all mode/identity/export
                # and installation behavior remains real production code.
                m.receipt['collection_id']=m.identity();m.preparation_error='';m.reason=''
            with patch.object(m,'prepare',side_effect=cached_prepare):
                workspace.start(independent=True);workspace.thread.join(4)
            self.assertFalse(workspace.busy());configure.assert_called_once_with(dict(mode='async'))
        self.assertEqual(workspace.data['task']['outcome'],'installed')
        self.assertEqual(m.options['mode'],'async');self.assertEqual(self.installed_catalog(f.installer)['jsaux']['mode'],'async')
        self.assertEqual(self.installed_catalog(f.installer)['settings']['sceneDuration'],24)
        self.assertNotIn('acquire',[name for name,*_ in f.fake.calls])

    def test_new_preparation_progress_does_not_reuse_or_mutate_previous_receipt_percent(self):
        f=self.manager_fixture();m=f.manager
        f.prepare_receipt()
        m.receipt['percent']=100  # Previous completed preparation.
        before=copy.deepcopy(m.receipt)
        entered=threading.Event();release=threading.Event()
        def pending_worker():entered.set();release.wait(2)
        with patch.object(m,'_prepare',side_effect=pending_worker):
            m.prepare();self.assertTrue(entered.wait(1))
            try:
                self.assertTrue(m.busy());self.assertEqual(m.status()['prepared']['percent'],0)
                self.assertEqual(m.receipt,before)
            finally:release.set();m.thread.join(3)

    def test_legacy_installed_selection_requires_one_normal_update_without_rebuild(self):
        service,installer,delegation,workspace=self.selection_fixture()
        for appid in range(12,17):workspace.save_draft(appid,dict(collection_member=False,excluded=False),reconcile_membership=True)
        workspace.commit()
        with patch('das.studio.installer.ready_games',return_value=service.catalog.games()):installer.install()
        # Simulate an alpha56/57 export whose revision matches the working
        # store but whose catalog was produced by the old selection contract.
        marker=installer.destination/'.decky-animated-screensaver.json'
        metadata=json.loads(marker.read_text());metadata.pop('selection_contract',None)
        marker.write_text(json.dumps(metadata))
        self.assertEqual(installer.status(refresh=True)['scene_count'],16)
        self.assertTrue(installer.status()['needs_update'])
        with patch('pathlib.Path.stat',side_effect=AssertionError('Cached status is metadata-only')):
            self.assertTrue(installer.status()['needs_update'])
        with patch.object(service,'prepare',side_effect=AssertionError('No TV rebuild')):
            workspace.start(install_only=True);workspace.thread.join(4)
        self.assertFalse(workspace.busy());self.assertEqual(workspace.data['task']['outcome'],'installed')
        self.assertEqual(installer.status()['scene_count'],11);self.assertFalse(installer.status()['needs_update'])
        self.assertEqual(json.loads(marker.read_text())['selection_contract'],1)

    def test_repeated_native_setting_values_do_not_stop_or_dirty_prepared_playback(self):
        f=self.manager_fixture();f.prepare_receipt();m=f.manager
        before=copy.deepcopy(m.receipt);revision=f.service.catalog.revision
        events=copy.deepcopy(m.events)
        m.preparation_error='CONTENT_INVALID';m.reason='CONTENT_INVALID'
        with patch.object(m,'stop',side_effect=AssertionError('No stop for unchanged settings')),patch.object(m,'_save_options',side_effect=AssertionError('No write for unchanged settings')):
            for option in ('enabled','mode','transition','page_seconds','framing'):
                m.configure({option:m.options[option]})
        self.assertEqual(m.receipt,before);self.assertEqual(m.events,events)
        self.assertEqual(f.service.catalog.revision,revision)
        self.assertEqual(m.preparation_error,'CONTENT_INVALID');self.assertEqual(m.reason,'CONTENT_INVALID')
