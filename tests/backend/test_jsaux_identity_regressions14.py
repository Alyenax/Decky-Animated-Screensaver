"""Regressions for irrelevant preference changes and persisted collection order."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_jsaux as fixtures
from das.jsaux.collection import fingerprint, preparation_spec
from das.studio.storage import Store
from das.studio.service import StudioService
from das.studio.installer import Installer
from das.jsaux.manager import Delegation
from test_studio import ASSETS, FakeMedia, scene


class CollectionIdentityRegressionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ManagerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_sync_does_not_depend_on_unused_independent_duration(self):
        fixture = self.fixture
        fixture.prepare_receipt()
        self.assertTrue(fixture.manager.status()['prepared']['ready'])
        fixture.manager.configure({'page_seconds': 30})
        self.assertTrue(fixture.manager.status()['prepared']['ready'])

    def test_unrendered_game_name_does_not_invalidate_faceplate_content(self):
        fixture = self.fixture
        fixture.prepare_receipt()
        fixture.service.catalog.update(620, {'name': 'Portal 2'})
        self.assertTrue(fixture.manager.status()['prepared']['ready'])

    def test_persisted_store_preserves_prepared_page_order(self):
        fixture = self.fixture
        scene(fixture.service.catalog, 10)
        fixture.prepare_receipt()
        before = fixture.manager.games()
        reloaded = Store(fixture.service.root)
        after = [game for game in reloaded.games() if not game.get('excluded') and reloaded.ready(game)]
        self.assertEqual([game['appid'] for game in before], [game['appid'] for game in after])
        self.assertEqual(fixture.manager.identity(), fingerprint(after, fixture.manager.options, reloaded.options()))

    def test_persisted_order_tracks_exclusion_addition_removal_and_reload(self):
        fixture=self.fixture; store=fixture.service.catalog
        scene(store,10); scene(store,300)
        store.update(10,{'excluded':True})
        self.assertEqual([game['appid'] for game in fixture.manager.games()],[620,300])
        store.data['games'].pop('620'); store.save()
        reloaded=Store(store.root)
        self.assertEqual([game['appid'] for game in reloaded.games()],[10,300])
        reloaded.update(10,{'excluded':False});scene(reloaded,42)
        self.assertEqual([game['appid'] for game in Store(store.root).games()],[10,300,42])

    def test_legacy_order_is_adopted_without_fabricating_an_old_receipt(self):
        fixture=self.fixture;store=fixture.service.catalog
        scene(store,10)
        store.data.pop('game_order',None)
        store.save()
        self.assertEqual(store.data['game_order'],[620,10])
        self.assertNotIn('jsaux_collection',store.data)

    def test_only_consumed_source_and_timing_affect_identity(self):
        fixture=self.fixture
        game=fixture.service.catalog.get(620)
        game['media']['panel_source']='sources/square.png'
        game['sha256']['panel_source']='a'*64
        games=[game]; options={**fixture.manager.options,'mode':'sync'};tv=fixture.service.catalog.options()
        original=fingerprint(games,options,tv)
        irrelevant=copy.deepcopy(game)
        irrelevant['name']='Renamed'
        irrelevant['sha256']['tv']='b'*64
        irrelevant['sha256']['thumbnail']='c'*64
        irrelevant['media']['panel_source']='sources/moved-identical-square.png'
        irrelevant['panel_asset']={'id':77,'url':'https://example.invalid/original.png'}
        self.assertEqual(original,fingerprint([irrelevant],{**options,'enabled':True,'configured':True,'page_seconds':180},tv))
        self.assertEqual(original,fingerprint(games,options,{**tv,'shuffle':False,'show_logo':False,'framing':'16:10'}))
        for patch in ({'faceplate_crop':{'x':25,'y':50}},
                      {'sha256':{**game['sha256'],'panel_source':'d'*64}},
                      {'panel_pending':True,'panel_asset':{'id':99,'url':'https://example.invalid/new.png'}}):
            self.assertNotEqual(original,fingerprint([{**game,**patch}],options,tv),patch)
        self.assertNotEqual(original,fingerprint(games,{**options,'transition':'slide'},tv))
        self.assertNotEqual(original,fingerprint(games,options,{**tv,'scene_seconds':30}))
        async_options={**options,'mode':'async'}
        asynchronous=fingerprint(games,async_options,tv)
        self.assertEqual(asynchronous,fingerprint(games,async_options,{**tv,'scene_seconds':30}))
        self.assertNotEqual(asynchronous,fingerprint(games,{**async_options,'page_seconds':30},tv))
        self.assertEqual(preparation_spec(games,options,tv)['version'],6)

    def test_fallback_source_change_invalidates_without_hash(self):
        fixture=self.fixture;game=fixture.service.catalog.get(620)
        original=fingerprint([game],fixture.manager.options,fixture.service.catalog.options())
        game['media']['cover']='prepared/cover-square.png'
        self.assertNotEqual(original,fingerprint([game],fixture.manager.options,fixture.service.catalog.options()))
        previous=fingerprint([game],fixture.manager.options,fixture.service.catalog.options())
        game['media']['cover']='prepared/cover-replacement.png'
        self.assertNotEqual(previous,fingerprint([game],fixture.manager.options,fixture.service.catalog.options()))

    def test_invalid_digest_uses_source_path_and_bad_order_is_normalized(self):
        fixture=self.fixture;store=fixture.service.catalog
        scene(store,10)
        store.data['game_order']=[True,620,620,99999,'10',None]
        store.save()
        self.assertEqual(store.data['game_order'],[620,10])
        game=store.get(620)
        game['sha256']['thumbnail']='not-a-valid-digest'
        original=fingerprint([game],fixture.manager.options,store.options())
        game['media']['thumbnail']='prepared/new-thumbnail.jpg'
        self.assertNotEqual(original,fingerprint([game],fixture.manager.options,store.options()))

    def test_multigame_prepare_install_restart_accepts_installed_player(self):
        fixture=self.fixture; manager=fixture.manager
        scene(fixture.service.catalog,10)
        fixture.service.compiler.runner=SimpleNamespace(ffmpeg='fixture-not-executed',library_path=None)
        manager.refresh();manager.configure({'enabled':True,'mode':'sync','transition':'none'})
        # Real GIF compilation/receipt/export with a deterministic fake decoder;
        # no API calls, USB device, or physical playback is implied.
        with patch('das.jsaux.manager.capture',side_effect=[bytes(10368),bytes([255])*10368]), \
             patch.object(fixture.service,'_assets',return_value=[]):
            manager._prepare()
        self.assertEqual(manager.reason,'')
        self.assertTrue(manager.status()['prepared']['ready'])
        identity=manager.identity();manager_path=manager.receipt['path']
        gif=fixture.service.catalog.managed(manager_path,True).read_bytes()
        fixture.installer.install();self.assertTrue(manager.status()['installed'])
        manager.shutdown();fixture.service.shutdown()
        service=StudioService(fixture.service.root,media=FakeMedia(),games_provider=lambda:[])
        self.addCleanup(service.shutdown)
        installer=Installer(service.catalog,fixture.root/'Steam',ASSETS)
        self.assertTrue(installer.status(True)['installed'])
        broker=fixtures.FakeClient();again=Delegation(service,installer,broker)
        installer.delegation=again;self.addCleanup(again.shutdown)
        self.assertEqual([game['appid'] for game in again.games()],[620,10])
        self.assertEqual(again.identity(),identity)
        self.assertEqual(service.catalog.managed(again.receipt['path'],True).read_bytes(),gif)
        self.assertTrue(again.status()['installed'])
        opened=again.player(dict(event='open',token=installer.token,collection_id=identity,
                                 session_id='reloaded-player',mode='sync',sequence=1))
        self.assertTrue(opened['accepted'])
        self.assertEqual([call[0] for call in broker.calls],['register','acquire'])

    def test_metadata_change_during_decode_does_not_relabel_old_frames(self):
        fixture=self.fixture; manager=fixture.manager
        fixture.service.compiler.runner=SimpleNamespace(ffmpeg='fixture-not-executed',library_path=None)
        manager.refresh();manager.configure({'enabled':True,'mode':'sync','transition':'none'})
        def decoded_before_change(*args,**kwargs):
            # ffmpeg used the previous crop embedded in args, then another
            # metadata writer changed it before compilation finished.
            fixture.service.catalog.update(620,{'faceplate_crop':{'x':0,'y':50}})
            return bytes(10368)
        with patch('das.jsaux.manager.capture',side_effect=decoded_before_change), \
             patch.object(fixture.service,'_assets',return_value=[]):
            manager._prepare()
        self.assertEqual(manager.reason,'STALE_GENERATION')
        self.assertFalse(manager.status()['prepared']['ready'])
        self.assertEqual(fixture.fake.calls,[])

    def test_prepare_fallback_cover_without_recorded_hash_is_not_stale(self):
        fixture=self.fixture;manager=fixture.manager
        game=fixture.service.catalog.get(620)
        fixture.service.catalog.managed('cover.jpg').write_bytes(b'local-cover')
        fixture.service.catalog.update(620,{'media':{**game['media'],'cover':'cover.jpg'}})
        fixture.service.compiler.runner=SimpleNamespace(ffmpeg='fixture-not-executed',library_path=None)
        manager.refresh();manager.configure({'enabled':True,'mode':'sync','transition':'none'})
        with patch('das.jsaux.manager.capture',return_value=bytes(10368)), \
             patch.object(fixture.service,'_assets',return_value=[]):
            manager._prepare()
        self.assertEqual(manager.reason,'')
        self.assertTrue(manager.status()['prepared']['ready'])

    def test_new_automatic_or_selected_panel_source_matches_decoded_receipt(self):
        fixture=self.fixture;manager=fixture.manager
        panel=fixture.service.catalog.managed('new-panel.png');panel.write_bytes(b'new-panel-input')
        asset={'id':55,'url':'https://example.invalid/new-panel.png'}
        fixture.service.compiler.runner=SimpleNamespace(ffmpeg='fixture-not-executed',library_path=None)
        manager.refresh();manager.configure({'enabled':True,'mode':'sync','transition':'none'})
        for selected in (False,True):
            with self.subTest(selected=selected):
                game=fixture.service.catalog.get(620)
                media={key:value for key,value in game['media'].items() if key!='panel_source'}
                hashes={key:value for key,value in game['sha256'].items() if key!='panel_source'}
                fixture.service.catalog.update(620,{'media':media,'sha256':hashes,'panel_pending':selected,'panel_asset':asset if selected else None})
                with patch('das.jsaux.manager.capture',return_value=bytes(10368)), \
                     patch.object(fixture.service,'_assets',return_value=[asset]), \
                     patch.object(fixture.service,'_download',return_value=panel):
                    manager._prepare()
                self.assertEqual(manager.reason,'')
                self.assertTrue(manager.status()['prepared']['ready'])


if __name__ == '__main__':
    unittest.main()
