"""Studio contracts: a new engine, old user media untouched, no implicit work."""
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from das.core.catalog import ScreensaverError, atomic_json, file_sha256
from das.studio.storage import Store, crop, validate
from das.studio.service import StudioService
from das.studio.installer import Installer, FOLDER, MARKER, player_catalog
from das.studio.preview import Preview
from das.studio.media import Media, webp_info
from das.studio.account import owned, profile

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'assets/player'

class Provider:
    def status(self): return dict(configured=True)
    def _search_kind(self,*args): return []
    def _json_request(self,*args): return dict(data=[])

class FakeMedia:
    lease_fd=None
    last_failure={}
    def capabilities(self): return dict(ffmpeg=True,ffprobe=True,native_first=True)
    def cancel(self): pass

def scene(store,number=620):
    directory=store.managed('prepared/0123456789abcdef01234567-12345678'); directory.mkdir(parents=True,exist_ok=True)
    media={}
    for key,name,data in [('tv','original.gif',b'GIF89a-owned'),('thumbnail','thumbnail.jpg',b'\xff\xd8owned')]:
        leaf=directory/name; leaf.write_bytes(data); media[key]=str(leaf.relative_to(store.root))
    store.update(number,dict(name='A very long game name · Test',installed=True,excluded=False,status='ready',animated=True,
        media=media,sha256={key:file_sha256(store.managed(value)) for key,value in media.items()},duration=1.5,width=64,height=54,format='gif'))
    return store.get(number)

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.store=Store(self.root/'studio')

    def service(self,**kw):
        result=StudioService(self.store.root,steamgriddb=Provider(),media=FakeMedia(),games_provider=lambda:[],**kw)
        self.addCleanup(result.shutdown); return result

    def test_migration_keeps_legacy_bytes_and_marks_revalidation(self):
        legacy=self.root/'cinema'; legacy.mkdir()
        atomic_json(legacy/'catalog.json',dict(games={'620':dict(appid=620,name='Portal',asset={'id':1},status='ready'),
            '228980':dict(appid=228980,name='Steamworks Common Redistributables')},options=dict(scene_seconds=12)))
        original=(legacy/'catalog.json').read_bytes()
        migrated=Store(self.root/'new',legacy)
        self.assertEqual(migrated.get(620)['status'],'pending')
        self.assertEqual(len(migrated.games()),1)
        self.assertEqual(migrated.options()['scene_seconds'],12)
        self.assertEqual((legacy/'catalog.json').read_bytes(),original)
        self.assertNotEqual(migrated.path,legacy/'catalog.json')

    def test_corrupt_metadata_is_backed_up_unknown_schema_is_preserved(self):
        self.store.path.write_text('{broken')
        recovered=Store(self.store.root)
        self.assertEqual(recovered.warning,'catalog_recovered')
        self.assertEqual(next(self.store.root.glob('studio.json.corrupt-*')).read_text(),'{broken')
        atomic_json(self.store.path,dict(schema=99))
        with self.assertRaises(ScreensaverError): Store(self.store.root)
        self.assertEqual(json.loads(self.store.path.read_text())['schema'],99)

    def test_paths_settings_and_crop_are_strict(self):
        for value in ('..','../x','.','/tmp/a','prepared//x','x/../y','x\\y'):
            with self.assertRaises(ScreensaverError,msg=value): self.store.managed(value)
        (self.store.root/'linked').symlink_to(self.root)
        with self.assertRaises(ScreensaverError): self.store.managed('linked/a')
        for value in ({'scene_seconds':True},{'storage_mib':1},{'framing':'stretch'},{'unknown':1}):
            with self.assertRaises(ScreensaverError): validate(value)
        with self.assertRaises(ScreensaverError): crop(dict(mode='16:9',x=float('nan'),y=50))

    def test_status_and_led_tick_never_touch_disk_network_or_decoder(self):
        service=self.service()
        with patch.object(service.provider,'status',side_effect=AssertionError('disk key lookup')), \
             patch.object(service.catalog,'usage',side_effect=AssertionError('scan')), \
             patch.object(service,'refresh_games',side_effect=AssertionError('scan')), \
             patch.object(service,'_request',side_effect=AssertionError('network')), \
             patch('pathlib.Path.stat',side_effect=AssertionError('filesystem')):
            for _ in range(200):
                self.assertEqual(service.status()['game_count'],0); service.tick()

    def test_scan_preserves_manual_choices_and_filters_runtime(self):
        service=self.service(); service.games_provider=lambda:[dict(appid=620,name='Portal 2'),dict(appid=228980,name='Steamworks Common Redistributables')]
        service.catalog.update(-9,dict(name='Manual',origin='manual',manual=True,status='pending'))
        service.catalog.update(620,dict(name='Portal',manual=True,asset={'id':2},excluded=True,status='pending'))
        service.refresh_games()
        self.assertEqual(service.catalog.get(620)['asset'],{'id':2})
        self.assertTrue(service.catalog.get(620)['excluded'])
        self.assertEqual(service.library(filter='manual')['total'],1)
        self.assertEqual(service.status()['game_count'],2)

    def test_cancel_does_not_poison_later_interactive_search(self):
        service=self.service(); service.control('cancel')
        self.assertEqual(service._request(lambda:'ok'),'ok')

    def test_manual_add_keeps_steam_identity_for_object_and_list_platform_mapping(self):
        for mapping in (dict(id=620),[dict(id=620)]):
            service=self.service()
            service.catalog.data['games']={}; service.catalog.save()
            service.provider._json_request=lambda _url:dict(data=dict(name='Portal',platforms=dict(steam=mapping)))
            service.add(17830)
            self.assertEqual(service.catalog.get(620)['sgdb_id'],17830)

    def test_pause_at_game_start_never_prepares_and_can_cancel(self):
        game={'appid':620}; service=self.service(current_game=lambda:game)
        service.catalog.update(620,dict(name='Portal',status='pending')); service._scanned=True
        with patch.object(service,'_one',side_effect=AssertionError('must wait')):
            service.prepare(); deadline=time.monotonic()+2
            while service.job['state']!='paused_game' and time.monotonic()<deadline: time.sleep(.01)
            self.assertEqual(service.job['state'],'paused_game')
            service.control('cancel'); service.thread.join(2)
            self.assertFalse(service.thread.is_alive()); self.assertEqual(service.job['state'],'cancelled')

    def test_missing_animation_skips_and_failed_replacement_keeps_valid_scene(self):
        entry=scene(self.store); service=self.service(); service._scanned=True
        service.catalog.update(620,dict(pending_change=True)); service.catalog.update(10,dict(name='Missing',status='pending'))
        service.prepare(); service.thread.join(3)
        self.assertEqual(service.job['state'],'complete')
        self.assertEqual(service.catalog.get(10)['status'],'skipped')
        self.assertEqual(service.catalog.get(620)['status'],'ready')
        self.assertEqual(service.catalog.managed(entry['media']['tv']).read_bytes(),b'GIF89a-owned')

    def test_purge_deletes_owned_tree_only_preserves_choices_api_and_foreign_files(self):
        entry=scene(self.store); service=self.service()
        service.catalog.update(620,dict(manual=True,asset={'id':77}))
        foreign=service.catalog.managed('prepared/my-own-image.png'); foreign.write_bytes(b'not Studio owned')
        unrelated=self.root/'cinema'; unrelated.mkdir(); (unrelated/'legacy.gif').write_bytes(b'keep')
        with self.assertRaises(ScreensaverError): service.maintenance('purge')
        service.maintenance('purge',True)
        self.assertFalse(service.catalog.managed(entry['media']['tv']).exists())
        self.assertTrue(foreign.exists()); self.assertTrue((unrelated/'legacy.gif').exists())
        self.assertEqual(service.catalog.get(620)['asset'],{'id':77})
        self.assertTrue(service.status()['key_configured'])

    def test_installer_preserves_old_export_exports_native_bytes_and_common_player(self):
        entry=scene(self.store); steam=self.root/'steam'; steam.mkdir()
        installer=Installer(self.store,steam,ASSETS)
        old=steam/'config/uioverrides/screensavers/gabecubeaura-cinema'; old.mkdir(parents=True); (old/'legacy').write_bytes(b'keep')
        state=installer.install('fr'); self.assertTrue(state['player_current'])
        self.assertEqual(installer.destination.name,FOLDER)
        self.assertEqual((installer.destination/'LICENSE.txt').read_bytes(),(ROOT/'licenses/GabeCubeAura-BSD-3-Clause.txt').read_bytes())
        for name in ('index.html','player.js','player.css'):
            self.assertEqual((ASSETS/name).read_bytes(),(installer.destination/name).read_bytes())
        data=json.loads((installer.destination/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').strip().removesuffix(';'))
        self.assertEqual(data['settings']['language'],'fr')
        self.assertEqual(data['settings']['sceneDuration'],24)
        self.assertEqual((installer.destination/data['games'][0]['media']['file']).read_bytes(),self.store.managed(entry['media']['tv']).read_bytes())
        self.assertEqual((old/'legacy').read_bytes(),b'keep')
        self.assertEqual(installer.destination.stat().st_mode & 0o777,0o755)
        installer.uninstall(); self.assertTrue(old.exists())

    def test_installer_refuses_foreign_and_rolls_back_failed_copy(self):
        scene(self.store); steam=self.root/'steam'; steam.mkdir(); installer=Installer(self.store,steam,ASSETS)
        installer.install(); before=(installer.destination/'catalog.js').read_bytes()
        with patch('das.studio.installer.ScreensaverInstaller._copy',side_effect=OSError('full')):
            with self.assertRaises(OSError): installer.install()
        self.assertEqual((installer.destination/'catalog.js').read_bytes(),before)
        (installer.destination/'personal.txt').write_bytes(b'keep')
        with self.assertRaises(ScreensaverError): installer.uninstall()
        self.assertTrue((installer.destination/'personal.txt').exists())

    def test_preview_serves_actual_same_player_and_media_then_releases_transport(self):
        scene(self.store); preview=Preview(self.store,ASSETS); self.addCleanup(preview.close)
        result=preview.open(); self.assertEqual(result['count'],1)
        with urlopen(result['url'],timeout=3) as response:
            html=response.read().decode(); self.assertIn('frame-ancestors',response.headers['Content-Security-Policy'])
        self.assertIn('Decky Animated Screensaver',html)
        code=[path for path in preview.transport.files.values() if path.name=='player.js'][0]
        self.assertEqual(code.read_bytes(),(ASSETS/'player.js').read_bytes())
        exported=json.loads((preview.code/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').strip().removesuffix(';'))
        self.assertEqual(exported['previewNonce'],result['nonce'])
        path=exported['games'][0]['media']['file']
        with urlopen(result['url'].split('/',3)[0]+'//'+result['url'].split('/')[2]+path,timeout=3) as response:
            self.assertEqual(response.read(),b'GIF89a-owned')
        preview.close(); self.assertFalse(preview.transport.thread.is_alive())
        self.assertFalse(preview.transport.files)

    def test_preview_handles_more_than_64_references_without_eviction(self):
        for number in range(50):
            entry=scene(self.store,number+1)
            leaf=self.store.managed('prepared/'+f'{number:032x}'+'.gif'); leaf.write_bytes(b'GIF89a-'+str(number).encode())
            self.store.update(number+1,dict(media={**entry['media'],'tv':str(leaf.relative_to(self.store.root))}))
        preview=Preview(self.store,ASSETS); self.addCleanup(preview.close)
        self.assertEqual(preview.open()['count'],50)
        self.assertGreater(len(preview.transport.files),50)

    def test_optional_smoothing_never_changes_duration_and_disabled_uses_original(self):
        entry=scene(self.store); smooth=self.store.managed('prepared/'+'a'*32+'.webm'); smooth.write_bytes(b'webm')
        self.store.update(620,dict(media={**entry['media'],'smoothed':str(smooth.relative_to(self.store.root))},smoothing_config=['fast',30]))
        self.store.configure(dict(scene_seconds=12))
        data=player_catalog(self.store); self.assertEqual(data['games'][0]['media']['file'],entry['media']['tv'])
        self.assertEqual(data['settings']['sceneDuration'],12)
        self.store.configure(dict(smoothing=True)); self.assertTrue(player_catalog(self.store)['games'][0]['media']['file'].endswith('.webm'))

    def test_account_key_not_persisted_and_untrusted_profiles_rejected(self):
        for value in ('https://evil.test/id/a','http://steamcommunity.com/id/x','https://steamcommunity.com@evil.test/id/x'):
            with self.assertRaises(ScreensaverError): profile(value)
        self.assertEqual(profile('76561198000000000')['steamid'],'76561198000000000')
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*_): self.close()
        class Opener:
            def open(self,request,timeout): return Response(json.dumps(dict(response=dict(game_count=1,games=[dict(appid=620,name='Portal')]))).encode())
        self.assertEqual(owned('a'*32,'76561198000000000',Opener())[0]['appid'],620)
        class Broken:
            def open(self,*args,**kw): raise OSError('https://example.org/?key='+'a'*32)
        with self.assertRaises(ScreensaverError) as error: owned('a'*32,'76561198000000000',Broken())
        self.assertNotIn('a'*32,str(error.exception))

    def test_malformed_structured_catalog_and_job_do_not_start_work(self):
        atomic_json(self.store.path,dict(schema=1,games={'620':dict(appid=620,name='Portal',media='invalid')},options={}))
        with self.assertRaises(ScreensaverError): Store(self.store.root)
        self.store.path.unlink()
        atomic_json(self.store.managed('job.json'),dict(state='running',stage='queued',history={},queue=[620]))
        service=self.service()
        self.assertEqual(service.job['state'],'idle'); self.assertIsNone(service.thread)

    def test_prepared_cover_and_logo_remain_in_catalog_when_hidden_for_live_preview(self):
        entry=scene(self.store)
        self.store.update(620,dict(media={**entry['media'],'cover':entry['media']['thumbnail'],'logo':entry['media']['thumbnail']}))
        self.store.configure(dict(show_cover=False,show_logo=False))
        game=player_catalog(self.store)['games'][0]
        self.assertIn('cover',game); self.assertIn('logo',game)

    def test_storage_and_export_update_status_survive_metadata_changes(self):
        scene(self.store); service=self.service(); service._measure_usage()
        restarted=self.service(); self.assertEqual(restarted.status()['storage_bytes'],service.status()['storage_bytes'])
        steam=self.root/'steam'; steam.mkdir(); installer=Installer(service.catalog,steam,ASSETS)
        self.assertFalse(installer.install()['needs_update'])
        service.configure(dict(scene_seconds=12))
        self.assertTrue(installer.status()['needs_update'])

class StudioRealMediaTests(unittest.TestCase):
    def test_native_gif_webp_webm_are_identical_after_prepare(self):
        binary=os.environ.get('DAS_TEST_FFMPEG')
        if not binary or not Path(binary).is_file(): self.skipTest('explicit FFmpeg required')
        import subprocess
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); media=Media(binary)
            media._probe=str(ROOT.parent/'Steam-Animated-Screensaver/node_modules/ffprobe-static/bin/darwin/arm64/ffprobe') if os.uname().sysname=='Darwin' else media._probe
            frames=[]
            for index in range(12):
                frame=Image.new('RGB',(64,54),(12,30,55)); ImageDraw.Draw(frame).rectangle((index*3,10,index*3+10,30),fill=(255,30,145)); frames.append(frame)
            for fmt in ('gif','webp'):
                source=directory/('source.'+fmt)
                frames[0].save(source,save_all=True,append_images=frames[1:],duration=100,loop=0)
                result=media.prepare(source,directory/fmt,Store(directory/'store').options(),lambda:None,lambda *_:None)
                self.assertEqual(result['tv'].read_bytes(),source.read_bytes())
                self.assertEqual(result['frames'],12)
                self.assertAlmostEqual(result['duration'],1.2,delta=.12)
            video=directory/'source.webm'
            subprocess.run([binary,'-v','error','-f','lavfi','-i','testsrc2=size=64x54:rate=12','-t','1','-c:v','libvpx-vp9','-threads','2',str(video)],check=True,timeout=20)
            result=media.prepare(video,directory/'webm',Store(directory/'store2').options(),lambda:None,lambda *_:None)
            self.assertEqual(result['tv'].read_bytes(),video.read_bytes())
            self.assertTrue(result['original_preserved'])
