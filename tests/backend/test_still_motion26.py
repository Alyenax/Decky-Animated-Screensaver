"""Original-only still rendering, metadata migration and legacy tool boundaries."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from das.core.catalog import file_sha256
from das.studio.media import Media, still_motion_path, still_motion_spec
from das.studio.installer import Installer, player_catalog
from das.studio.service import StudioService
from das.studio.workspace import CollectionWorkspace
from das.studio.problems import game_problem
from test_studio import ASSETS, Provider, FakeMedia, scene


class MotionMedia(FakeMedia):
    def animate_still(self,*args,**kwargs):
        raise AssertionError('Production still preparation must not encode a video')


class StillMotion26Tests(unittest.TestCase):
    def service(self,root):
        service=StudioService(Path(root)/'studio',steamgriddb=Provider(),media=MotionMedia(),games_provider=lambda:[])
        self.addCleanup(service.shutdown)
        entry=scene(service.catalog)
        original=service.catalog.managed('prepared/retained-original.png')
        original.write_bytes(b'\x89PNG\r\n\x1a\n-retained-original')
        media={**entry['media'],'tv':str(original.relative_to(service.root))}
        service.catalog.update(620,dict(animated=False,format='png',duration=0,width=640,height=400,
            media=media,sha256={key:file_sha256(service.catalog.managed(value)) for key,value in media.items()}))
        service.catalog.configure(dict(static_fallback=True,show_cover=False,show_logo=False))
        return service

    def legacy(self,service):
        entry=service.catalog.get(620);media=dict(entry['media']);hashes=dict(entry['sha256'])
        for key in ('still_motion','smoothed'):
            leaf=service.catalog.managed('prepared/legacy-'+key+'.webm');leaf.write_bytes(b'legacy-'+key.encode())
            media[key]=str(leaf.relative_to(service.root));hashes[key]=file_sha256(leaf)
        service.catalog.update(620,dict(media=media,sha256=hashes,still_motion_config=dict(version=4,seconds=40),
            still_motion_info=dict(width=1280,height=720,duration=40),motion_error='static_motion_failed',
            smoothing_config=['fast',30]))
        return service.catalog.get(620)

    def test_encoder_progress_accepts_unknown_partial_or_nonfinite_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);compiler=Media();compiler.runner.ffmpeg='fixture';samples=[]
            def run(command,directory,check,timeout):
                for value in ('N/A','','NaN','inf','-1','0','1500000','999999999'):
                    (directory/'.progress').write_text('out_time_us='+value+'\nprogress=continue\n');check()
            with patch.object(compiler.runner,'_run',side_effect=run):compiler.run([],root,lambda:None,samples.append,duration=3)
            self.assertEqual(samples,[None,None,None,None,None,0,.5,.99]);self.assertFalse((root/'.progress').exists())

    def test_legacy_tool_trajectory_remains_closed_but_is_not_the_production_renderer(self):
        frames=1200;anchor=(.28,.68)
        for start,end in zip(still_motion_path(0,frames,anchor),still_motion_path(frames,frames,anchor)):
            self.assertAlmostEqual(start,end,places=12)
        self.assertAlmostEqual(still_motion_path(frames//2,frames,anchor)[0],1.10)
        self.assertEqual(still_motion_spec({})['renderer'],'transform')

    def test_transform_recipe_is_gentle_and_independent_of_scene_calendar(self):
        for seconds in (8,12,13,19,20,24,60,180):
            options=dict(scene_seconds=seconds)
            self.assertEqual(still_motion_spec(options),dict(version=8,renderer='transform',seconds=60,max_scale=1.18,pan_x=.06))
            self.assertEqual(options,dict(scene_seconds=seconds))

    def test_cached_original_prepares_without_download_encoder_or_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=self.service(tmp);entry=service.catalog.get(620)
            original=file_sha256(service.catalog.managed(entry['media']['tv']));schedule=player_catalog(service.catalog)['presentation']
            with (patch.object(service,'_download',side_effect=AssertionError('No redownload')),
                  patch.object(service.compiler,'inspect',create=True,side_effect=AssertionError('Cached original is already validated')),
                  patch.object(service.compiler,'animate_still',side_effect=AssertionError('No encoder')),
                  patch.object(service.compiler,'smooth',create=True,side_effect=AssertionError('No smoothing of stills'))):
                service._one(620);service._one(620)
            current=service.catalog.get(620)
            self.assertEqual(current['media'],entry['media']);self.assertEqual(current['sha256'],entry['sha256'])
            self.assertEqual(file_sha256(service.catalog.managed(entry['media']['tv'])),original)
            self.assertEqual(current['still_motion_config'],still_motion_spec(service.catalog.options()))
            self.assertEqual(current.get('motion_error'),'')
            exported=player_catalog(service.catalog)
            self.assertEqual(exported['presentation'],schedule);self.assertEqual(exported['settings']['sceneDuration'],24)
            game=exported['games'][0];self.assertEqual(game['stillMotion'],'gentle')
            self.assertEqual(game['media']['file'],entry['media']['tv']);self.assertFalse(game['media']['animated'])
            self.assertEqual((game['media']['format'],game['media']['width'],game['media']['height'],game['media']['duration']),('png',640,400,0))

    def test_actual_legacy_encoder_is_only_an_explicit_tool(self):
        binary=os.environ.get('DAS_TEST_FFMPEG');probe=os.environ.get('DAS_TEST_FFPROBE')
        if not binary or not probe:self.skipTest('Explicit isolated legacy video tools required')
        from PIL import Image
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'still.png';Image.new('RGB',(320,200),'#284452').save(source);before=file_sha256(source)
            compiler=Media(binary);compiler._probe=probe
            result=compiler.animate_still(source,root/'out',dict(scene_seconds=8,max_video_mib=32),lambda:None,lambda *_:None)
            self.assertEqual(file_sha256(source),before);self.assertEqual((result['width'],result['height']),(320,200))
            self.assertEqual(result['frames'],1800);self.assertFalse(result['audio']);self.assertAlmostEqual(result['duration'],60,delta=.1)
            decoded=subprocess.run([binary,'-v','error','-xerror','-i',str(result['tv']),'-f','null','-'],capture_output=True,text=True,check=True,timeout=30)
            self.assertEqual(decoded.stderr,'')

    def test_normal_update_migrates_legacy_recipe_once_without_render_or_full_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);service=self.service(root);entry=self.legacy(service);service._scanned=True
            original=file_sha256(service.catalog.managed(entry['media']['tv']))
            steam=root/'Steam';steam.mkdir();installer=Installer(service.catalog,steam,ASSETS)
            workspace=CollectionWorkspace(service,installer,SimpleNamespace(busy=lambda:False,options={'enabled':False}))
            self.addCleanup(workspace.shutdown)
            schedule=player_catalog(service.catalog)['presentation']
            with (patch.object(service,'_download',side_effect=AssertionError('Reuse original')),
                  patch.object(service.compiler,'animate_still',side_effect=AssertionError('No encoder')) as encode):
                self.assertEqual(workspace.summary()['pending_ids'],[620])
                self.assertEqual(workspace.summary()['issues_count'],0)
                self.assertEqual(service.status()['issues_count'],0)
                workspace.start(mode='missing');workspace.thread.join(5)
                self.assertFalse(workspace.busy());self.assertEqual(workspace.data['task']['state'],'done')
                self.assertEqual(workspace.data['task']['outcome'],'installed');self.assertEqual(encode.call_count,0)
                self.assertFalse(service.job['force']);self.assertEqual(workspace.summary()['pending_ids'],[])
                # No encoded derivative metadata/file is required by recipe7.
                current=service.catalog.get(620)
                self.assertEqual(current['media'],entry['media']);self.assertEqual(current['motion_error'],'')
                self.assertEqual(current['still_motion_config'],still_motion_spec(service.catalog.options()))
                revision=service.catalog.revision;service._one(620);self.assertEqual(service.catalog.revision,revision)
            self.assertEqual(file_sha256(service.catalog.managed(entry['media']['tv'])),original)
            self.assertEqual(player_catalog(service.catalog)['presentation'],schedule)
            for key in ('still_motion','smoothed'):
                self.assertEqual(file_sha256(service.catalog.managed(entry['media'][key])),entry['sha256'][key])
            service.catalog.configure(dict(reduced_motion=True));service.catalog.update(620,dict(still_motion_config=dict(version=4,seconds=40)))
            self.assertEqual(workspace.summary()['pending_ids'],[])
            service.catalog.configure(dict(reduced_motion=False));service.catalog.update(620,dict(still_mode='fixed'))
            self.assertEqual(workspace.summary()['pending_ids'],[])

    def test_legacy_failure_and_derivatives_are_never_exported_for_stills(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=self.service(tmp);entry=self.legacy(service);service.catalog.configure(dict(smoothing=True))
            # Even before migration, ignore the failed obsolete video and a
            # matching smoothing derivative; both stay recoverable on disk.
            game=player_catalog(service.catalog)['games'][0]
            self.assertEqual(game['media']['file'],entry['media']['tv']);self.assertEqual(game['stillMotion'],'gentle')
            with patch.object(service.compiler,'animate_still',side_effect=AssertionError('Obsolete renderer must not be retried')) as encode:
                service._one(620)
            self.assertEqual(encode.call_count,0);self.assertEqual(service.catalog.get(620)['motion_error'],'')
            self.assertEqual(service.status()['ready_count'],1)
            for key in ('tv','still_motion','smoothed'):
                self.assertEqual(file_sha256(service.catalog.managed(entry['media'][key])),entry['sha256'][key])

    def test_fixed_and_reduced_export_original_and_explicit_rendering_without_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=self.service(tmp);entry=self.legacy(service)
            for mode,reduced,expected in [('inherit',False,'gentle'),('motion',False,'gentle'),('fixed',False,'fixed'),('motion',True,'fixed')]:
                service.catalog.configure(dict(reduced_motion=reduced));service.catalog.update(620,dict(still_mode=mode))
                with patch.object(service.compiler,'animate_still',side_effect=AssertionError('No encoder')):service._one(620)
                game=player_catalog(service.catalog)['games'][0]
                self.assertEqual(game['stillMotion'],expected);self.assertFalse(game['media']['animated'])
                self.assertEqual(game['media']['file'],entry['media']['tv'])
                self.assertEqual((game['media']['width'],game['media']['height']),(640,400))

    def test_only_obsolete_still_encoder_error_is_retired_from_recovery(self):
        game=dict(appid=620,animated=False,motion_error='static_motion_failed')
        self.assertIsNone(game_problem(game,True))
        self.assertEqual(game_problem({**game,'cover_error':'decode_failed'},True)['code'],'decode_failed')
        self.assertEqual(game_problem({**game,'motion_error':'unexpected_motion_error'},True)['code'],'unexpected_motion_error')
        self.assertEqual(game_problem({**game,'animated':True},True)['code'],'static_motion_failed')

    def test_no_static_warning_is_in_shipped_player(self):
        player=(Path(__file__).resolve().parents[2]/'assets/player/player.js').read_text()
        for text in ('Illustration statique','Optional fallback','static-note'):self.assertNotIn(text,player)
