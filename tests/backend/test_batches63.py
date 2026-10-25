"""Real GIF compilation, preparation/install transaction and multi-lot publication."""
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_jsaux as fixture
from test_studio import scene
from test_plugin import Codec
from das.jsaux.protocol import BrokerError
from das.jsaux.manager import Delegation
from das.jsaux.collection import compile_batches,batch_identity
from das.jsaux.timing import SYNC_MAX_BYTES

class BatchManagerTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ManagerTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.m=self.f.manager;self.store=self.f.service.catalog;self.fake=self.f.fake
        self.fake.hello['capabilities']=dict(autonomous_player=True,autonomous_batches=True)
        self.fake.register=lambda path,collection_id:dict(content_id=hashlib.sha256(Path(path).read_bytes()).hexdigest())
        self.requests=[]
        def request(op,args):
            self.requests.append((op,copy.deepcopy(args)))
            if op=='publish_player_batch':return dict(controller='GabeCubeAura',relay=dict(kind='http-loopback-v1',url='http://127.0.0.1:37680/jsaux/v1/player'),next_index=args['index']+1,published=args['index']==args['count']-1)
            return dict(published=False)
        self.fake.request=request
        codec=Codec();codec.runner=SimpleNamespace(ffmpeg='fixture-ffmpeg',library_path=None)
        self.f.service.compiler=codec;self.f.service._assets=lambda *args:[]
        for n in range(620,636):scene(self.store,n)
        self.m.configure(dict(enabled=True,mode='sync'))

    def prepare(self,force_fallback=True):
        colors=[bytes((n*7%256,n*11%256,n*13%256))*3456 for n in range(16)]
        with patch('das.jsaux.manager.capture',side_effect=colors):
            if force_fallback:
                with patch('das.jsaux.manager.compile_pages',side_effect=BrokerError('JSAUX_SYNC_WINDOW')):self.m._prepare()
            else:self.m._prepare()

    def test_large_sync_preparation_automatically_builds_lots_installs_and_persists(self):
        self.prepare();self.assertEqual(self.m.preparation_error,'')
        self.assertEqual(self.m.options['mode'],'sync');self.assertTrue(self.m.status()['prepared']['ready'])
        self.assertEqual(self.store.data['jsaux']['mode'],'sync')
        self.assertEqual(self.m.status()['prepared']['effective_mode'],'async')
        self.assertFalse(self.m.status()['prepared']['sync_admissible'])
        self.assertEqual(self.m.installation_blocker(),'')
        rows=self.m.receipt['batches'];self.assertEqual(len(rows),2)
        self.assertEqual(sum(r['pages'] for r in rows),16)
        self.assertTrue(all(0<r['bytes']<=SYNC_MAX_BYTES for r in rows))
        identity=self.m.identity();self.assertEqual(identity,batch_identity(self.m.receipt['source_identity'],rows))
        self.f.installer.install()
        publications=[args for op,args in self.requests if op=='publish_player_batch']
        self.assertEqual([p['index'] for p in publications],[0,1]);self.assertTrue(all(p['count']==2 and p['alignment_ms']==0 for p in publications))
        self.assertEqual(self.f.installer.jsaux_export['mode'],'async')
        restored=Delegation(self.f.service,self.f.installer,self.fake);self.addCleanup(restored.shutdown)
        self.assertEqual(restored.identity(),identity);self.assertTrue(restored.readiness()['ready'])
        self.assertEqual(restored.options['mode'],'sync');self.assertEqual(restored.export()['mode'],'async')
        self.assertEqual(self.fake.calls,[],'Compilation/publication never acquires or flashes the display')

    def test_new_settings_default_to_sync_and_saved_explicit_independent_is_preserved(self):
        for saved in ({},dict(enabled=True,mode='async',configured=True)):
            self.store.data['jsaux']=saved
            restored=Delegation(self.f.service,self.f.installer,self.fake);self.addCleanup(restored.shutdown)
            self.assertEqual(restored.options['mode'],saved.get('mode','sync'))
            self.assertEqual(self.store.data['jsaux'],saved,'Loading defaults never rewrites preferences')

    def test_fallback_does_not_requeue_valid_lots_and_next_smaller_preparation_retries_sync(self):
        self.prepare();self.assertTrue(self.m.readiness()['ready'])
        with patch.object(self.m,'prepare') as prepare:
            self.m.after_tv_prepare()
            prepare.assert_not_called()
        for n in range(621,636):self.store.update(n,dict(excluded=True))
        self.prepare(False)
        self.assertEqual(self.m.preparation_error,'');self.assertTrue(self.m.readiness()['ready'])
        self.assertEqual(self.m.options['mode'],'sync');self.assertEqual(self.store.data['jsaux']['mode'],'sync')
        self.assertEqual(self.m.export()['mode'],'sync');self.assertNotIn('batches',self.m.receipt)
        self.assertEqual(self.m.receipt['input_spec']['playback']['page_seconds'],self.store.options()['scene_seconds'])

    def test_lot_duration_change_invalidates_actual_fallback_but_not_single_sync(self):
        self.prepare();self.assertTrue(self.m.readiness()['ready'])
        self.m.configure(dict(page_seconds=30))
        self.assertFalse(self.m.readiness()['ready']);self.assertIn('playback',self.m.readiness()['changed'])
        self.assertEqual(self.m.options['mode'],'sync')

    def test_explicit_mode_change_invalidates_even_when_both_durations_are_equal(self):
        self.m.configure(dict(page_seconds=self.store.options()['scene_seconds']))
        for n in range(621,636):self.store.update(n,dict(excluded=True))
        self.prepare(False);self.assertTrue(self.m.readiness()['ready'])
        self.m.configure(dict(mode='async'));self.assertFalse(self.m.readiness()['ready'])
        self.prepare(False);self.assertTrue(self.m.readiness()['ready'])
        self.assertEqual(self.m.export()['mode'],'async');self.assertEqual(self.store.data['jsaux']['mode'],'async')

    def test_independent_rebuild_keeps_compact_lots_instead_of_one_dense_gif(self):
        self.m.configure(dict(mode='async'));self.prepare()
        self.assertEqual(self.m.preparation_error,'');self.assertEqual(len(self.m.receipt['batches']),2)
        self.assertEqual(self.m.receipt['pages'],16);self.assertEqual(self.m.options['mode'],'async')
        self.assertFalse(self.m.receipt['automatic_independent'])

    def test_small_collection_keeps_single_synchronised_gif(self):
        for n in range(621,636):self.store.update(n,dict(excluded=True))
        self.prepare(False)
        self.assertEqual(self.m.preparation_error,'');self.assertEqual(self.m.options['mode'],'sync')
        self.assertNotIn('batches',self.m.receipt);self.assertFalse(self.m.receipt['automatic_independent'])

    def test_older_gca_is_actionable_and_does_not_silently_publish_only_first_lot(self):
        self.fake.hello['capabilities'].pop('autonomous_batches')
        before=copy.deepcopy(self.m.options);self.prepare()
        self.assertEqual(self.m.preparation_error,'BATCHES_REQUIRE_GCA_UPDATE')
        self.assertEqual(self.m.options,before);self.assertEqual(self.requests,[])

    def test_partial_publication_is_unpublished_and_previous_steam_export_is_kept(self):
        self.prepare();self.f.installer.install();old=(self.f.installer.destination/'catalog.js').read_bytes()
        original=self.fake.request
        def request(op,args):
            if op=='publish_player_batch' and args['index']==1:raise BrokerError('BROKER_UNAVAILABLE')
            return original(op,args)
        self.fake.request=request
        with self.assertRaises(BrokerError):self.f.installer.install()
        self.assertEqual((self.f.installer.destination/'catalog.js').read_bytes(),old)
        self.assertTrue(any(op=='remove_player' for op,_ in self.requests))

    def test_failed_preparation_removes_new_lots_without_changing_saved_mode(self):
        before=copy.deepcopy(self.m.options)
        self.fake.register=lambda *args:(_ for _ in ()).throw(BrokerError('CONTENT_INVALID'))
        self.prepare()
        self.assertEqual(self.m.preparation_error,'CONTENT_INVALID');self.assertEqual(self.m.options,before)
        self.assertEqual(list(self.store.managed('jsaux').glob('*.gif')),[])

    def test_client_retries_only_known_read_or_publication_rate_rejections(self):
        from das.jsaux.client import BrokerClient
        client=BrokerClient()
        with patch.object(client,'_connect'),patch('das.jsaux.client.time.sleep'):
            for operation in ('operation_status','publish_player_batch'):
                with patch.object(client,'_rpc',side_effect=[BrokerError('RATE_LIMITED',50),dict(done=True)]) as rpc:
                    self.assertEqual(client.request(operation,{}),dict(done=True));self.assertEqual(rpc.call_count,2)
            for operation,error in [('acquire_display',BrokerError('RATE_LIMITED')),('publish_player_batch',BrokerError('RATE_LIMITED',uncertain=True)),('publish_player_batch',BrokerError('BROKER_UNAVAILABLE',uncertain=True))]:
                with patch.object(client,'_rpc',side_effect=error) as rpc:
                    with self.assertRaises(BrokerError):client.request(operation,{})
                    self.assertEqual(rpc.call_count,1)

    def test_bad_faceplate_square_tries_next_before_committing_the_source(self):
        for n in range(621,636):self.store.update(n,dict(excluded=True))
        assets=[dict(id=n,animated=False,url=f'https://cdn.steamgriddb.com/{n}.png') for n in (900,901)]
        self.f.service._assets=lambda n,r:assets if r=='panel' else []
        paths={}
        for asset in assets:
            path=self.store.managed('sources/panel-'+str(asset['id'])+'.png');path.parent.mkdir(exist_ok=True);path.write_bytes(str(asset['id']).encode());paths[asset['id']]=path
        self.f.service._download=lambda a:paths[a['id']]
        seen=[]
        def decode(args,**kw):
            source=args[args.index('-i')+1];seen.append(source)
            if source==str(paths[900]):raise BrokerError('CONTENT_INVALID')
            return bytes((0,90,40))*3456
        with patch('das.jsaux.manager.capture',side_effect=decode):self.m._prepare()
        self.assertEqual(self.m.preparation_error,'');self.assertTrue(self.m.readiness()['ready'])
        self.assertEqual(self.store.get(620)['panel_asset']['id'],901)
        self.assertEqual(seen,[str(paths[900]),str(paths[901])])
        self.assertEqual(self.f.service.diagnostic_snapshot()['failures'][-1]['asset']['role'],'panel')
        self.assertFalse(self.fake.calls)

    def test_missing_cached_faceplate_source_uses_valid_thumbnail(self):
        for n in range(621,636):self.store.update(n,dict(excluded=True))
        game=self.store.get(620);game['media']['panel_source']='sources/deleted.png'
        self.store.update(620,dict(media=game['media']))
        with patch('das.jsaux.manager.capture',return_value=bytes((0,90,40))*3456):self.m._prepare()
        self.assertEqual(self.m.preparation_error,'');self.assertTrue(self.m.readiness()['ready'])
        self.assertEqual(self.store.get(620)['media']['panel_source'],game['media']['thumbnail'])

    def test_lot_compiler_preserves_all_pages_and_cancellation(self):
        pages=[bytes((n,))*3456 for n in range(19)]
        output=compile_batches(pages,24,'fade')
        self.assertEqual(sum(details['pages'] for _,details in output),19)
        self.assertTrue(all(len(data)<=SYNC_MAX_BYTES for data,_ in output))
        def cancel():raise BrokerError('PREPARATION_CANCELLED')
        with self.assertRaises(BrokerError) as error:compile_batches(pages,24,'fade',checkpoint=cancel)
        self.assertEqual(error.exception.code,'PREPARATION_CANCELLED')
