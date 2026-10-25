"""Real workspace/service/installer. Fixtures are not USB or optical evidence."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from das.core.catalog import ScreensaverError
from das.studio.service import StudioService
from das.studio.installer import Installer
from das.studio.workspace import CollectionWorkspace
from test_studio import Provider, scene, ASSETS
from test_plugin import Codec, GIF

ASSET=dict(id=123,animated=True,kind='hero',width=460,height=215,
           url='https://cdn.steamgriddb.com/test.gif',author='Fixture')

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.service=StudioService(self.root/'library',Provider(),media=Codec(),
            games_provider=lambda:[dict(appid=620,name='Portal'),dict(appid=730,name='Counter Strike')])
        self.service.catalog.configure(dict(show_cover=False,name_display='title'))
        (self.root/'Steam').mkdir()
        self.installer=Installer(self.service.catalog,self.root/'Steam',ASSETS)
        self.delegation=SimpleNamespace(busy=lambda:False,options={'enabled':False})
        self.workspace=CollectionWorkspace(self.service,self.installer,self.delegation)
        self.addCleanup(self.service.shutdown);self.addCleanup(self.workspace.shutdown)
        self.service.refresh_games(include_new=False)
        source=self.service.catalog.managed('sources/test.gif');source.parent.mkdir();source.write_bytes(GIF)
        self.service._download=lambda asset:source
        self.service._assets=lambda n,r:[copy.deepcopy(ASSET)] if r=='animation' else []
        self.service._candidates={(620,r):[copy.deepcopy(ASSET)] for r in ('animation','cover','logo','panel','still_tv')}

    def ready(self):
        value=scene(self.service.catalog);self.service._ready.add(620);return value

    def finish(self):
        self.workspace.thread.join(4)
        self.assertFalse(self.workspace.busy())

    def test_new_scan_does_not_select_all_games(self):
        self.assertEqual(self.workspace.library()['total'],0)
        self.assertEqual(self.workspace.library(filter='installed')['total'],2)
        self.assertEqual(self.workspace.summary()['included_count'],0)

    def test_drafts_persist_and_merge_without_encoding_catalog_or_install_writes(self):
        before=self.service.catalog.path.read_bytes()
        with patch.object(self.service,'prepare',side_effect=AssertionError('No conversion')),patch.object(self.installer,'install',side_effect=AssertionError('No install')):
            self.workspace.save_draft(620,dict(choices={'animation':123},collection_member=True,excluded=False))
            self.workspace.save_draft(620,dict(choices={'cover':123}))
            self.workspace.save_draft(620,dict(choices={'logo':123},crop=dict(mode='16:10',x=35,y=60)))
        self.assertEqual(before,self.service.catalog.path.read_bytes())
        self.assertFalse(self.installer.destination.exists())
        other=CollectionWorkspace(self.service,self.installer,self.delegation)
        draft=other.overlay(self.service.catalog.get(620))
        for field in ('asset','cover_asset','logo_asset'):self.assertEqual(draft[field]['id'],123)
        self.assertEqual(other.library()['total'],1)
        self.assertEqual(other.summary()['pending_ids'],[620])
        self.assertEqual(self.workspace.path.stat().st_mode&0o777,0o600)

    def test_direct_selection_reversal_preserves_artwork_and_removes_only_noop_membership(self):
        self.workspace.save_draft(620,dict(choices={'cover':123}))
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False),reconcile_membership=True)
        self.workspace.save_draft(620,dict(collection_member=False,excluded=False),reconcile_membership=True)
        patch=self.workspace.data['drafts']['620']['patch']
        self.assertEqual(patch['cover_asset']['id'],123)
        self.assertNotIn('collection_member',patch)
        self.assertNotIn('excluded',patch)
        self.workspace.save_draft(730,dict(collection_member=True,excluded=False),reconcile_membership=True)
        self.workspace.save_draft(730,dict(collection_member=False,excluded=False),reconcile_membership=True)
        self.assertNotIn('730',self.workspace.data['drafts'])
        self.assertEqual(self.workspace.library()['total'],0)

    def test_list_prefix_is_bounded_fresh_and_never_changes_catalog(self):
        before=self.service.catalog.path.read_bytes()
        page=self.workspace.library(filter='installed',limit=10)
        self.assertEqual(len(page['items']),2)
        self.workspace.save_draft(620,dict(collection_member=True),reconcile_membership=True)
        self.assertTrue(next(g for g in self.workspace.library(filter='installed',limit=20)['items'] if g['appid']==620)['collection_member'])
        for limit in (0,11,2001,True,'10'):
            with self.assertRaises(ScreensaverError):self.workspace.library(filter='installed',limit=limit)
        self.assertEqual(before,self.service.catalog.path.read_bytes())

    def test_classic_switch_preserves_everything_and_legacy_data_remains_readable(self):
        self.ready();before=self.service.catalog.path.read_bytes()
        self.workspace.save_draft(620,dict(crop=dict(mode='16:9',x=50,y=50)))
        self.workspace.preferences({'mode':'classic','layout':'compact'})
        other=CollectionWorkspace(self.service,self.installer,self.delegation)
        self.assertEqual(other.summary()['mode'],'classic')
        self.assertEqual(other.summary()['draft_count'],1)
        self.assertEqual(before,self.service.catalog.path.read_bytes())
        self.assertTrue(self.service.catalog.ready(self.service.catalog.get(620),True))

    def test_only_cached_candidates_and_typed_whitelisted_drafts_are_accepted(self):
        for payload in ({'shell':'bad'},{'choices':{'animation':444}},{'choices':{'animation':'123'}},
                        {'excluded':1},{'still_mode':'bad'},{'crop':dict(mode='16:9',x=float('nan'),y=50)},
                        {'faceplate_crop':dict(x=50,y=float('inf'))}):
            with self.assertRaises(ScreensaverError):self.workspace.save_draft(620,payload)
        self.assertEqual(self.workspace.summary()['draft_count'],0)
        self.workspace.save_draft(620,dict(choices={'animation':123}))
        self.workspace.data['drafts']['620']['patch']['asset']['url']='file:///etc/passwd'
        before=self.service.catalog.path.read_bytes()
        with self.assertRaises(ScreensaverError):self.workspace.commit()
        self.assertEqual(before,self.service.catalog.path.read_bytes())

    def test_commit_rolls_back_on_save_failure_and_keeps_drafts(self):
        before=copy.deepcopy(self.service.catalog.data)
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False))
        with patch.object(self.service.catalog,'save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.workspace.commit()
        self.assertEqual(before,self.service.catalog.data)
        self.assertEqual(self.workspace.summary()['draft_count'],1)

    def test_real_prepare_installs_atomically_and_new_edits_wait_for_next_run(self):
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False))
        entered=threading.Event();release=threading.Event();original=self.service._one
        def one(number):
            entered.set();release.wait(2);original(number)
        with patch.object(self.service,'_one',side_effect=one):
            self.workspace.start('fr');self.assertTrue(entered.wait(1))
            self.workspace.save_draft(620,dict(crop=dict(mode='16:10',x=35,y=60)))
            with self.assertRaises(ScreensaverError):self.workspace.start()
            with self.assertRaises(ScreensaverError):self.workspace.commit()
            release.set();self.finish()
        self.assertEqual(self.workspace.summary()['task']['state'],'done')
        self.assertEqual(self.workspace.summary()['task']['outcome'],'installed')
        self.assertEqual(self.workspace.summary()['installed_count'],1)
        self.assertTrue(self.installer.destination.exists())
        self.assertNotEqual(self.service.catalog.get(620).get('crop',{}).get('mode'),'16:10')
        self.assertEqual(self.workspace.summary()['draft_count'],1)
        self.workspace.start('fr');self.finish()
        self.assertEqual(self.workspace.summary()['draft_count'],0)
        self.assertEqual(self.service.catalog.get(620)['crop']['mode'],'16:10')

    def test_failed_preparation_keeps_installed_snapshot_and_is_actionable(self):
        self.ready();self.installer.install();before=(self.installer.destination/'catalog.js').read_bytes()
        self.workspace.save_draft(620,dict(choices={'animation':123}))
        with patch.object(self.service,'_one',side_effect=ScreensaverError('Bad image','decode_failed')):
            self.workspace.start();self.finish()
        self.assertEqual(self.workspace.summary()['task']['state'],'done')
        self.assertEqual(self.workspace.summary()['task']['outcome'],'installed')
        self.assertEqual(self.workspace.summary()['issues_count'],0)
        self.assertEqual(self.workspace.summary()['pending_count'],0)
        self.assertEqual(before,(self.installer.destination/'catalog.js').read_bytes())
        self.workspace.save_draft(620,dict(choices={'animation':123}))
        self.assertEqual(self.workspace.summary()['pending_count'],1)

    def test_hidden_optional_choices_do_not_create_endless_work(self):
        self.ready()
        self.workspace.save_draft(620,dict(choices={'cover':123,'logo':123,'panel':123}))
        self.workspace.commit()
        self.assertEqual(self.workspace.summary()['pending_count'],0)
        self.assertTrue(self.service.catalog.get(620)['cover_pending'])

    def test_install_cannot_silently_export_an_unprepared_subset(self):
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False))
        with self.assertRaises(ScreensaverError):self.workspace.start(install_only=True)
        self.assertFalse(self.installer.destination.exists())

    def test_waits_for_after_prepare_callback_even_when_busy_flag_cleared(self):
        callback=threading.Event();release=threading.Event()
        def after():callback.set();release.wait(2)
        self.service.after_prepare=after
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False))
        self.workspace.start();self.assertTrue(callback.wait(2))
        self.assertFalse(self.service._busy())
        self.assertFalse(self.installer.destination.exists())
        release.set();self.finish();self.assertEqual(self.workspace.summary()['task']['state'],'done')

    def test_install_ready_collection_without_reencoding_and_then_unchanged(self):
        self.ready()
        with patch.object(self.service,'prepare',side_effect=AssertionError('No TV encode')):
            self.workspace.start(install_only=True);self.finish()
            self.assertEqual(self.workspace.data['task']['outcome'],'installed')
            with patch.object(self.installer,'install',side_effect=AssertionError('No duplicate install')):
                self.workspace.start(install_only=True);self.finish()
        self.assertEqual(self.workspace.data['task']['outcome'],'unchanged')
        self.assertEqual(self.workspace.summary()['installed_count'],1)

    def test_empty_collection_cannot_claim_installed_or_replace_old_snapshot(self):
        self.ready();self.installer.install();before=(self.installer.destination/'catalog.js').read_bytes()
        self.service.catalog.update(620,dict(excluded=True))
        with patch.object(self.installer,'install',side_effect=AssertionError('No empty export')):
            self.workspace.start();self.finish()
        self.assertEqual(self.workspace.data['task']['state'],'done')
        self.assertEqual(self.workspace.data['task']['outcome'],'unchanged')
        self.assertEqual(self.workspace.data['task']['tv_state'],'unchanged')
        self.assertEqual(self.workspace.summary()['installed_count'],1)
        self.assertEqual((self.installer.destination/'catalog.js').read_bytes(),before)

    def test_all_skipped_preserves_old_installed_collection_and_reports_unchanged(self):
        self.ready();self.installer.install();before=(self.installer.destination/'catalog.js').read_bytes()
        self.service.catalog.update(620,dict(excluded=True))
        self.service.catalog.update(730,dict(excluded=False,collection_member=True))
        self.service._assets=lambda *args:[]
        with patch.object(self.installer,'install',side_effect=AssertionError('No empty export')):
            self.workspace.start();self.finish()
        summary=self.workspace.summary()
        self.assertEqual(summary['skipped_count'],1)
        self.assertEqual(summary['task']['outcome'],'unchanged')
        self.assertEqual(summary['installed_count'],1)
        self.assertEqual((self.installer.destination/'catalog.js').read_bytes(),before)

    def test_truly_empty_collection_reports_empty_not_installed(self):
        self.workspace.start();self.finish()
        self.assertEqual(self.workspace.data['task']['outcome'],'empty')
        self.assertEqual(self.workspace.summary()['installed_count'],0)
        self.assertFalse(self.installer.destination.exists())

    def faceplate(self,ready=False,failure=''):
        owner=self
        class Panel:
            options={'enabled':True,'mode':'async'};detected=True;compatible=True;reason='';player_relay=None
            def __init__(self):self.thread=None;self.cancelled=threading.Event();self.ready=ready;self.started=threading.Event();self.release=threading.Event();self.calls=0
            def busy(self):return bool(self.thread and self.thread.is_alive())
            def status(self):return dict(prepared={'ready':self.ready},installed=bool(self.ready and owner.installer.jsaux_export))
            def prepare(self):
                self.calls+=1;self.started.set()
                def run():
                    self.release.wait(2)
                    self.reason=failure;self.ready=not failure
                self.thread=threading.Thread(target=run);self.thread.start()
            def installation_blocker(self):return '' if self.ready or not self.detected or not self.compatible else 'JSAUX_PREPARATION_REQUIRED'
            def installation_event(self,*args):pass
            def export(self):return dict(enabled=True,mode='async',collection_id='a'*64) if self.ready else None
        panel=Panel();self.workspace.delegation=panel;self.installer.delegation=panel
        self.addCleanup(panel.release.set)
        return panel

    def test_repair_faceplate_waits_then_installs_without_tv_preparation(self):
        self.ready();self.service.catalog.update(620,dict(panel_pending=True))
        panel=self.faceplate()
        with patch.object(self.service,'prepare',side_effect=AssertionError('No TV encode')):
            self.workspace.start(install_only=True)
            self.assertTrue(panel.started.wait(1));self.assertFalse(self.installer.destination.exists())
            self.assertEqual(self.workspace.data['task']['stage'],'faceplate')
            panel.release.set();self.finish()
        self.assertEqual(panel.calls,1)
        self.assertEqual(self.workspace.data['task']['outcome'],'installed')
        self.assertEqual(self.workspace.data['task']['faceplate_state'],'installed')

    def test_explicit_faceplate_repair_rebuilds_even_if_old_receipt_is_ready(self):
        self.ready();panel=self.faceplate(ready=True);self.installer.install();panel.reason='CONTENT_INVALID'
        panel.release.set()
        with patch.object(self.service,'prepare',side_effect=AssertionError('No TV encode')),patch.object(self.installer,'install',wraps=self.installer.install) as install:
            self.workspace.start(install_only=True,repair_faceplate=True);self.finish()
        self.assertEqual(panel.calls,1);self.assertEqual(install.call_count,1)
        self.assertEqual(self.workspace.data['task']['outcome'],'installed')
        self.assertEqual(self.workspace.data['task']['faceplate_state'],'installed')

    def test_normal_update_automatically_repairs_rejected_receipt_even_after_rediscovery(self):
        self.ready();panel=self.faceplate(ready=True);self.installer.install();panel.reason='CONTENT_INVALID'
        original=panel.status
        panel.status=lambda:{**original(),'reason':panel.reason}
        panel.refresh=lambda:setattr(panel,'reason','')
        panel.release.set()
        with patch.object(self.service,'prepare',side_effect=AssertionError('No TV re-encode')):
            self.workspace.start(install_only=True);self.finish()
        self.assertEqual(panel.calls,1);self.assertEqual(self.workspace.data['task']['outcome'],'installed')

    def test_collection_update_rediscovers_faceplate_before_automatic_preparation(self):
        self.ready();panel=self.faceplate();panel.detected=False;panel.compatible=False;panel.release.set()
        def refresh():panel.detected=True;panel.compatible=True
        panel.refresh=refresh
        self.workspace.start(install_only=True);self.finish()
        self.assertEqual(panel.calls,1);self.assertEqual(self.workspace.data['task']['faceplate_state'],'installed')

    def test_combined_workflow_fills_missing_faceplate_stage_without_legacy_callback(self):
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False))
        panel=self.faceplate();panel.release.set()
        self.workspace.start();self.finish()
        self.assertEqual(panel.calls,1);self.assertEqual(self.workspace.data['task']['outcome'],'installed')

    def test_current_collection_update_does_not_rebuild_faceplate_or_tv(self):
        self.ready();panel=self.faceplate(ready=True);self.installer.install()
        with patch.object(self.service,'prepare',side_effect=AssertionError('No TV re-encode')):
            self.workspace.start(install_only=True);self.finish()
        self.assertEqual(panel.calls,0);self.assertEqual(self.workspace.data['task']['outcome'],'unchanged')

    def test_faceplate_repair_flag_is_strict_and_never_implies_tv_preparation(self):
        for options in ({'repair_faceplate':True},{'install_only':True,'repair_faceplate':1},{'install_only':True,'repair_faceplate':'yes'}):
            with self.assertRaises(ScreensaverError) as error:self.workspace.start(**options)
            self.assertEqual(error.exception.code,'invalid_setting')

    def test_restart_during_explicit_faceplate_repair_preserves_the_rebuild_intent(self):
        self.ready();panel=self.faceplate(ready=True);self.installer.install();panel.release.set()
        self.workspace.task('preparing',operation='install',stage='faceplate',repair_faceplate=True)
        other=CollectionWorkspace(self.service,self.installer,panel);self.addCleanup(other.shutdown)
        self.assertTrue(other.resume());other.thread.join(3)
        self.assertEqual(panel.calls,1)
        self.assertEqual(other.data['task']['outcome'],'installed')

    def test_faceplate_failure_preserves_installed_tv_and_reports_repair(self):
        self.ready();self.installer.install();before=(self.installer.destination/'catalog.js').read_bytes()
        panel=self.faceplate(failure='CONTENT_TOO_LARGE');panel.release.set()
        self.workspace.start(install_only=True);self.finish()
        self.assertEqual(self.workspace.data['task']['state'],'partial')
        self.assertEqual(self.workspace.data['task']['error'],'CONTENT_TOO_LARGE')
        self.assertEqual(self.workspace.data['task']['tv_state'],'prepared')
        self.assertEqual(self.workspace.data['task']['faceplate_state'],'repair_required')
        self.assertNotIn('outcome',self.workspace.data['task'])
        self.assertEqual((self.installer.destination/'catalog.js').read_bytes(),before)

    def test_combined_preparation_waits_for_faceplate_callback_then_installs(self):
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False))
        panel=self.faceplate();self.service.after_prepare=panel.prepare
        self.workspace.start();self.assertTrue(panel.started.wait(2))
        self.assertFalse(self.installer.destination.exists())
        panel.release.set();self.finish()
        self.assertEqual(panel.calls,1)
        self.assertEqual(self.workspace.data['task']['outcome'],'installed')
        self.assertEqual(self.workspace.data['task']['faceplate_state'],'installed')

    def test_unavailable_faceplate_does_not_block_tv_only_installation(self):
        self.ready();panel=self.faceplate();panel.detected=False;panel.compatible=False
        with patch.object(panel,'prepare',side_effect=AssertionError('No absent device preparation')):
            self.workspace.start(install_only=True);self.finish()
        self.assertEqual(self.workspace.data['task']['outcome'],'installed')
        self.assertEqual(self.workspace.data['task']['faceplate_state'],'unavailable')

    def test_faceplate_protection_refusal_is_actionable_without_install(self):
        self.ready();panel=self.faceplate()
        with patch.object(panel,'prepare',side_effect=ScreensaverError('Active owner preserved','PREPARATION_BUSY')):
            self.workspace.start(install_only=True);self.finish()
        self.assertEqual(self.workspace.data['task']['state'],'partial')
        self.assertEqual(self.workspace.data['task']['error'],'PREPARATION_BUSY')
        self.assertEqual(self.workspace.data['task']['tv_state'],'prepared')
        self.assertFalse(self.installer.destination.exists())

    def test_done_outcome_recovers_but_legacy_done_is_not_invented_success(self):
        self.workspace.task('done',outcome='installed',tv_state='installed',faceplate_state='disabled')
        other=CollectionWorkspace(self.service,self.installer,self.delegation)
        self.assertEqual(other.summary()['task']['outcome'],'installed')
        self.workspace.path.write_text(json.dumps(dict(schema=1,task=dict(state='done',error=''))))
        legacy=CollectionWorkspace(self.service,self.installer,self.delegation)
        self.assertEqual(legacy.summary()['task']['state'],'done')
        self.assertNotIn('outcome',legacy.summary()['task'])

    def test_restart_during_installation_can_resume_without_new_tv_job(self):
        self.ready();self.workspace.task('applying',operation='install',stage='installation',tv_state='prepared')
        other=CollectionWorkspace(self.service,self.installer,self.delegation);self.addCleanup(other.shutdown)
        with patch.object(self.service,'prepare',side_effect=AssertionError('No TV restart')):
            self.assertTrue(other.resume('fr'));other.thread.join(3)
        self.assertEqual(other.data['task']['outcome'],'installed')

    def test_post_prepare_game_pause_resumes_installation_without_committing_new_drafts(self):
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False))
        playing=threading.Event()
        self.service.after_prepare=playing.set
        with patch.object(self.service,'_playing',side_effect=playing.is_set):
            self.workspace.start();self.finish()
            self.assertEqual(self.workspace.data['task']['state'],'paused')
            self.assertEqual(self.workspace.data['task']['error'],'GAME_RUNNING')
            self.assertFalse(self.installer.destination.exists())
            self.workspace.save_draft(620,dict(crop=dict(mode='16:10',x=35,y=60)))
            playing.clear();self.assertTrue(self.workspace.resume('fr'));self.finish()
        self.assertEqual(self.workspace.data['task']['outcome'],'installed')
        self.assertEqual(self.workspace.summary()['draft_count'],1)
        self.assertNotEqual(self.service.catalog.get(620).get('crop',{}).get('mode'),'16:10')

    def test_install_protection_error_is_not_success(self):
        self.ready()
        with patch.object(self.installer,'install',side_effect=ScreensaverError('Protected destination','installation_conflict')):
            self.workspace.start(install_only=True);self.finish()
        self.assertEqual(self.workspace.data['task']['state'],'error')
        self.assertEqual(self.workspace.data['task']['error'],'installation_conflict')
        self.assertNotIn('outcome',self.workspace.data['task'])

    def test_cancel_does_not_apply_and_paused_status_has_no_disk_churn(self):
        entered=threading.Event();release=threading.Event();original=self.service._one
        def one(n):entered.set();release.wait(2);self.service.checkpoint();original(n)
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False))
        with patch.object(self.service,'_one',side_effect=one):
            self.workspace.start();self.assertTrue(entered.wait(1))
            self.service.control('cancel');self.workspace.cancel();release.set();self.finish()
        self.assertFalse(self.installer.destination.exists())
        self.assertEqual(self.workspace.summary()['task']['state'],'cancelled')
        self.workspace.task('paused')
        with patch.object(self.workspace,'_save') as save:
            for _ in range(50):self.workspace.task('paused')
            save.assert_not_called()

    def test_restart_recovers_interrupted_work_as_paused_not_auto_started(self):
        self.workspace.task('applying')
        other=CollectionWorkspace(self.service,self.installer,self.delegation)
        self.assertEqual(other.summary()['task']['state'],'paused')
        self.assertFalse(other.busy());self.assertFalse(self.installer.destination.exists())

    def test_restart_resume_finishes_old_recipe_and_keeps_new_drafts(self):
        self.service.catalog.update(620,dict(excluded=False,collection_member=True))
        self.service._save_job(state='paused',stage='interrupted',queue=[620],total=1,completed=0)
        self.workspace.task('preparing')
        other=CollectionWorkspace(self.service,self.installer,self.delegation);self.addCleanup(other.shutdown)
        other.save_draft(620,dict(crop=dict(mode='16:10',x=40,y=50)))
        self.assertTrue(other.resume('fr'));other.thread.join(4)
        self.assertEqual(other.summary()['task']['state'],'done')
        self.assertNotEqual(self.service.catalog.get(620).get('crop',{}).get('mode'),'16:10')
        self.assertEqual(other.summary()['draft_count'],1)

    def test_corrupt_draft_cannot_break_optional_ui_status_or_classic_recovery(self):
        self.workspace.path.write_text(json.dumps(dict(schema=1,mode='classic',drafts={'620':dict(revision='x',patch={'appid':[]})})))
        other=CollectionWorkspace(self.service,self.installer,self.delegation)
        self.assertEqual(other.summary()['mode'],'classic');self.assertEqual(other.summary()['draft_count'],0)
        self.assertIn('appid',self.workspace.path.read_text()) # Original file preserved until an explicit edit.

    def test_disk_failure_does_not_report_an_unsaved_draft_or_preference_as_saved(self):
        with patch.object(self.workspace,'_save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.workspace.save_draft(620,dict(excluded=False,collection_member=True))
            with self.assertRaises(OSError):self.workspace.preferences({'mode':'classic'})
        self.assertEqual(self.workspace.summary()['draft_count'],0)
        self.assertEqual(self.workspace.summary()['mode'],'collection')

    def test_status_never_prepares_opens_usb_or_changes_metadata(self):
        before=self.service.catalog.path.read_bytes()
        with patch.object(self.service,'prepare',side_effect=AssertionError('No work')),patch.object(self.installer,'install',side_effect=AssertionError('No install')):
            for _ in range(20):self.workspace.summary();self.workspace.library()
        self.assertEqual(before,self.service.catalog.path.read_bytes())

    def test_per_game_still_is_ready_without_enabling_global_static_fallback(self):
        self.ready();self.service.catalog.update(620,dict(animated=False,still_mode='fixed'))
        self.assertFalse(self.service.catalog.options()['static_fallback'])
        self.assertEqual(self.service.status()['ready_count'],1)
        self.assertTrue(self.service.catalog.ready(self.service.catalog.get(620),True))
        from das.studio.installer import player_catalog
        exported=player_catalog(self.service.catalog,lambda p:p)
        self.assertFalse(exported['settings']['staticFallback'])
        self.assertTrue(exported['games'][0]['explicitStill'])

if __name__=='__main__':unittest.main()
