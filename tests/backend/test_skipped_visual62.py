"""Per-artwork failure isolation through the real queue, workspace and installer."""
import copy
import os
import signal
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

from das.core.catalog import ScreensaverError
from das.core.process_guard import capture
from das.studio.presentation import ready_games
from das.studio.service import StudioService
from test_plugin import Codec
import test_workspace as fixture
from test_workspace import ASSET
from test_plugin import GIF


class SkippedVisualTests(unittest.TestCase):
    setUp=fixture.WorkspaceTests.setUp
    finish=fixture.WorkspaceTests.finish

    def select(self,ids=(620,730,322170)):
        for number in ids:
            self.service.catalog.update(number,dict(name=str(number),excluded=False,collection_member=True))
        self.service._scanned=True
        self.service._assets=lambda n,r:[{**ASSET,'id':n}] if r=='animation' else []
        source=self.service.catalog.managed('sources/bad.gif');source.write_bytes(GIF)
        healthy=self.service.catalog.managed('sources/test.gif')
        self.service._download=lambda asset:source if asset['id']==730 else healthy
        return source

    def fail_source(self,bad,code='worker_signal',real=False):
        original=self.service.compiler.prepare;calls=[]
        def prepare(source,*args,**kw):
            calls.append(Path(source).name)
            if Path(source)==bad:
                if real:
                    capture([sys.executable,'-c','import os,signal;os.kill(os.getpid(),signal.SIGTERM)'],environment=os.environ,timeout=5,maximum=4096)
                raise ScreensaverError('Bad artwork',code)
            return original(source,*args,**kw)
        return prepare,calls

    def test_real_signalled_middle_source_is_traced_skipped_and_healthy_subset_installed(self):
        bad=self.select();prepare,calls=self.fail_source(bad,real=True)
        with patch.object(self.service.compiler,'prepare',side_effect=prepare):
            self.workspace.start();self.finish()
        self.assertEqual(calls,['test.gif','bad.gif','test.gif'])
        self.assertEqual(self.service.job['state'],'complete');self.assertEqual(self.service.job['completed'],3)
        self.assertEqual(self.service.job['skipped_count'],1)
        summary=self.workspace.summary();self.assertEqual(summary['task']['state'],'done')
        self.assertEqual(summary['task']['outcome'],'installed');self.assertEqual(summary['installed_count'],2)
        self.assertEqual(summary['pending_count'],0)
        # Both export paths use this shared presentation set and order.
        self.assertEqual([g['appid'] for g in ready_games(self.service.catalog)],[620,322170])
        payload=(self.installer.destination/'catalog.js').read_text()
        self.assertNotIn('"appid":730',payload)
        report=self.service.diagnostic_snapshot();failure=report['failures'][-1]
        self.assertEqual(failure['appid'],730);self.assertEqual(failure['asset']['id'],730)
        self.assertEqual(failure['disposition'],'skipped');self.assertEqual(failure['process']['exit_code'],-signal.SIGTERM)
        self.assertIsNone(self.service.game_details(730)['problem'])

    def test_known_bad_source_not_retried_until_manual_replacement_then_error_clears(self):
        bad=self.select();prepare,calls=self.fail_source(bad,'resource_limit')
        with patch.object(self.service.compiler,'prepare',side_effect=prepare):
            self.workspace.start();self.finish();self.workspace.start();self.finish()
        self.assertEqual(calls.count('bad.gif'),1)
        loaded=StudioService(self.service.root,media=Codec(),games_provider=lambda:[]);self.addCleanup(loaded.shutdown)
        loaded._scanned=True
        with patch.object(loaded,'_download',side_effect=AssertionError('No retry after restart')):
            loaded.prepare();loaded.thread.join(3)
        self.assertEqual(loaded.job['state'],'complete');self.assertEqual(loaded.job['skipped_count'],1)
        # Optional flags cannot make an unrenderable background perpetually pending.
        self.service.catalog.configure(dict(show_cover=True))
        self.service.catalog.update(730,dict(cover_pending=True))
        self.assertEqual(self.workspace.summary()['pending_count'],0)
        replacement={**ASSET,'id':999};self.service._candidates[(730,'animation')]=[replacement]
        self.workspace.save_draft(730,dict(choices={'animation':999}))
        self.assertEqual(self.workspace.summary()['pending_count'],1)
        self.workspace.start();self.finish()
        self.assertFalse(self.service.game_details(730)['problem'])
        self.assertEqual(self.service.catalog.get(730)['asset']['id'],999)
        self.assertEqual(self.workspace.summary()['installed_count'],3)
        self.assertEqual(self.service.job['skipped_count'],0)

    def test_explicit_full_rebuild_can_retry_failed_source(self):
        bad=self.select();prepare,calls=self.fail_source(bad)
        with patch.object(self.service.compiler,'prepare',side_effect=prepare):
            self.workspace.start();self.finish();self.workspace.start(mode='all');self.finish()
        self.assertEqual(calls.count('bad.gif'),2)

    def test_failed_replacement_keeps_verified_previous_visual_and_installs_other_games(self):
        self.select();self.workspace.start();self.finish()
        old=copy.deepcopy(self.service.catalog.get(730)['media'])
        self.service._candidates[(730,'animation')]=[{**ASSET,'id':730}]
        self.workspace.save_draft(730,dict(choices={'animation':730}))
        bad=self.service.catalog.managed('sources/bad.gif');prepare,_=self.fail_source(bad)
        with patch.object(self.service.compiler,'prepare',side_effect=prepare):
            self.workspace.start();self.finish()
        self.assertEqual(self.service.catalog.get(730)['media'],old)
        self.assertTrue(self.service.catalog.ready(self.service.catalog.get(730),True))
        self.assertEqual(self.workspace.summary()['installed_count'],3)
        self.assertIsNone(self.service.game_details(730)['problem'])

    def test_optional_cover_signal_retains_background_and_processes_following_games(self):
        self.select();self.service.catalog.configure(dict(show_cover=True))
        self.service._assets=lambda n,r:[{**ASSET,'id':n if r=='animation' else 730,'animated':r=='animation'}] if r in {'animation','cover'} else []
        original=self.service.compiler.prepare
        def prepare(source,*args,**kw):
            if kw.get('static'):raise ScreensaverError('Cover stopped','worker_signal')
            return original(source,*args,**kw)
        with patch.object(self.service.compiler,'prepare',side_effect=prepare) as work:
            self.workspace.start();self.finish();before=work.call_count
            self.workspace.start();self.finish();self.assertEqual(work.call_count,before)
        self.assertEqual(self.workspace.summary()['installed_count'],3)
        self.assertTrue(all(g['problem'] is None for g in map(self.service.game_details,[620,730,322170])))
        self.assertEqual(self.service.diagnostic_snapshot()['last_failure']['asset']['role'],'cover')

    def test_all_new_sources_fail_without_installing_empty_collection(self):
        self.select(ids=(730,));bad=self.service.catalog.managed('sources/bad.gif');prepare,_=self.fail_source(bad)
        with patch.object(self.service.compiler,'prepare',side_effect=prepare),patch.object(self.installer,'install',side_effect=AssertionError('No empty export')):
            self.workspace.start();self.finish()
        self.assertEqual(self.workspace.summary()['task']['outcome'],'empty')
        self.assertFalse(self.installer.destination.exists())

    def test_optional_logo_signal_keeps_tv_sources_and_offers_logo_replacement(self):
        self.select();self.service.catalog.configure(dict(name_display='logo'))
        self.service._assets=lambda n,r:[{**ASSET,'id':n,'animated':r=='animation'}] if r in {'animation','logo'} else []
        original=self.service.compiler.prepare
        def prepare(source,*args,**kw):
            if kw.get('static'):raise ScreensaverError('Logo stopped','worker_signal')
            return original(source,*args,**kw)
        with patch.object(self.service.compiler,'prepare',side_effect=prepare):
            self.workspace.start();self.finish()
        self.assertEqual(self.workspace.summary()['installed_count'],3)
        self.assertIsNone(self.service.game_details(730)['problem'])
        self.assertIsNone(self.service.game_details(730)['problem'])

    def test_optional_smoothing_signal_keeps_original_and_does_not_retry(self):
        self.select();self.service.catalog.configure(dict(smoothing=True))
        with patch.object(self.service.compiler,'smooth',side_effect=ScreensaverError('Smoothing stopped','worker_signal'),create=True) as smooth:
            self.workspace.start();self.finish();before=smooth.call_count
            self.workspace.start();self.finish();self.assertEqual(smooth.call_count,before)
        self.assertEqual(self.workspace.summary()['installed_count'],3)
        self.assertIsNone(self.service.game_details(730)['problem'])
        self.assertIsNone(self.service.game_details(730)['problem'])

    def test_global_runtime_failure_still_pauses_without_consuming_queue(self):
        self.select()
        with patch.object(self.service.compiler,'prepare',side_effect=ScreensaverError('Cannot isolate','runtime_isolation')):
            self.service.prepare();self.service.thread.join(3)
        self.assertEqual(self.service.job['state'],'paused');self.assertEqual(self.service.job['completed'],0)
        self.assertEqual(self.service.job['queue'],[620,730,322170])
        self.assertEqual(self.service.job['skipped_count'],0)
