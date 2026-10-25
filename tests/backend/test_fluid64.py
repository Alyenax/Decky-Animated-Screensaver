"""Real queue/workspace/export; decoder and network fixtures only."""
import copy
from pathlib import Path
from unittest.mock import patch
import unittest
from das.core.catalog import ScreensaverError
from das.studio.service import StudioService
from test_plugin import Codec,GIF
import test_workspace as fixture
from test_workspace import ASSET

class Fluid64Tests(unittest.TestCase):
    setUp=fixture.WorkspaceTests.setUp;finish=fixture.WorkspaceTests.finish
    def setup_assets(self,animated=4,stills=2):
        self.service.catalog.update(620,dict(collection_member=True,excluded=False))
        self.service._scanned=True;self.attempts=[];self.bad=set()
        self.assets={r:[{**ASSET,'id':start+i,'animated':r=='animation','url':f'https://cdn.steamgriddb.com/{start+i}.gif'} for i in range(count)] for r,start,count in [('animation',100,animated),('still_tv',200,stills),('cover',300,3),('logo',400,3)]}
        self.service._assets=lambda n,r:copy.deepcopy(self.assets.get(r,[]))
        def download(asset):
            path=self.service.catalog.managed('sources/'+str(asset['id'])+'.gif');path.write_bytes(GIF);return path
        self.service._download=download;self.service._local_artwork=lambda n:None
        original=self.service.compiler.prepare
        def prepare(source,*args,**kw):
            number=int(Path(source).stem);self.attempts.append(number)
            if number in self.bad:raise ScreensaverError('Fixture image failed','worker_signal')
            value=original(source,*args,**kw);value['animated']=not kw.get('static');return value
        self.service.compiler.prepare=prepare

    def test_fourth_animation_is_chosen_after_three_failed_workers_and_survives_restart(self):
        self.setup_assets();self.bad={100,101,102};self.workspace.start();self.finish()
        self.assertEqual(self.attempts,[100,101,102,103]);self.assertEqual(self.workspace.summary()['installed_count'],1)
        self.assertEqual(self.service.catalog.get(620)['asset']['id'],103)
        self.assertEqual(self.workspace.summary()['issues_count'],0);self.assertIsNone(self.service.game_details(620)['problem'])
        self.assertEqual(len(self.service.diagnostic_snapshot()['failures']),3)
        self.workspace.start();self.finish();self.assertEqual(self.attempts,[100,101,102,103])
        loaded=StudioService(self.service.root,media=Codec(),games_provider=lambda:[]);self.addCleanup(loaded.shutdown)
        self.assertEqual(loaded.catalog.get(620)['asset']['id'],103);self.assertTrue(loaded.catalog.ready(loaded.catalog.get(620),True))

    def test_exhausted_animations_try_next_fixed_image_only_with_global_consent(self):
        self.setup_assets();self.bad={100,101,102,103,200}
        self.service.configure(dict(static_fallback=True));self.workspace.start();self.finish()
        self.assertEqual(self.attempts,[100,101,102,103,200,201])
        game=self.service.catalog.get(620);self.assertFalse(game['animated']);self.assertTrue(game['animation_unavailable'])
        self.assertEqual(game['asset']['id'],201);self.assertEqual(self.workspace.summary()['issues_count'],0)
        self.assertEqual(self.workspace.summary()['installed_count'],1)

    def test_unchecked_static_option_skips_neutrally_then_checked_option_prepares_fixed(self):
        self.setup_assets();self.bad={100,101,102,103}
        self.workspace.start();self.finish();game=self.service.catalog.get(620)
        self.assertEqual(game['status'],'skipped');self.assertEqual(game['skip_reason'],'no_animation')
        self.assertEqual(self.workspace.summary()['issues_count'],0);self.assertEqual(self.workspace.summary()['skipped_count'],1)
        self.assertNotIn(200,self.attempts);self.assertFalse(self.installer.destination.exists())
        self.service.configure(dict(static_fallback=True))
        self.assertEqual(self.workspace.summary()['pending_count'],1)
        self.workspace.start();self.finish()
        self.assertEqual(self.attempts,[100,101,102,103,200]);self.assertEqual(self.workspace.summary()['installed_count'],1)

    def test_failed_manual_animation_uses_automatic_alternative(self):
        self.setup_assets();self.bad={100};self.service.catalog.update(620,dict(asset=self.assets['animation'][0],manual=True,pending_change=True))
        self.workspace.start();self.finish();self.assertEqual(self.attempts,[100,101])
        self.assertFalse(self.service.catalog.get(620)['manual']);self.assertEqual(self.workspace.summary()['issues_count'],0)

    def test_failed_optional_cover_and_logo_use_next_and_never_request_attention(self):
        self.setup_assets();self.bad={300,301,400}
        self.service.configure(dict(show_cover=True,name_display='logo'));self.workspace.start();self.finish()
        self.assertEqual(self.attempts,[100,300,301,302,400,401])
        game=self.service.catalog.get(620);self.assertIn('cover',game['media']);self.assertIn('logo',game['media'])
        self.assertEqual(self.workspace.summary()['issues_count'],0)

    def test_no_readable_artwork_preserves_previous_export_without_repeated_candidates(self):
        self.setup_assets();self.workspace.start();self.finish();old=(self.installer.destination/'catalog.js').read_bytes()
        self.bad={100,101,102,103,200,201};self.service.catalog.update(620,dict(pending_change=True));self.service.configure(dict(static_fallback=True))
        self.workspace.start();self.finish();attempts=list(self.attempts)
        self.assertEqual(self.workspace.summary()['issues_count'],0)
        self.assertIn(b'620',(self.installer.destination/'catalog.js').read_bytes())
        self.assertTrue(self.service.catalog.ready(self.service.catalog.get(620),True))
        self.workspace.start();self.finish();self.assertEqual(self.attempts,attempts)

    def test_old_image_failure_does_not_hide_a_different_global_error(self):
        from das.studio.problems import game_problem
        game=dict(appid=620,status='error',error='steamgriddb_unauthorized',media_failures=dict(background=dict(disposition='skipped',code='decode_failed')))
        self.assertEqual(game_problem(game)['code'],'steamgriddb_unauthorized')

    def test_storage_and_runtime_failures_still_pause_without_consuming_queue(self):
        for code in ('storage_limit','runtime_isolation','python_missing'):
            with self.subTest(code=code):
                self.setup_assets()
                with patch.object(self.service.compiler,'prepare',side_effect=ScreensaverError('Cannot prepare',code)):
                    self.service.prepare(force=True);self.service.thread.join(4)
                self.assertEqual(self.service.job['state'],'paused');self.assertEqual(self.service.job['completed'],0)
                self.assertEqual(self.service.job['error'],code)
