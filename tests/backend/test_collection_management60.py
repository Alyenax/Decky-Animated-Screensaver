"""Real global draft/undo and owned-export deletion. No USB/optical claim."""
import copy
import json
from pathlib import Path
from unittest.mock import patch,Mock
from das.core.catalog import ScreensaverError
from das.studio.workspace import CollectionWorkspace
from test_workspace import WorkspaceTests
from test_plugin import PluginTests

class CollectionManagementTests(WorkspaceTests):
    # Inherit fixtures only, not the complete parent's tests a second time.
    def ready(self):
        super().ready();self.service.catalog.update(620,dict(collection_member=True,excluded=False))
        return self.service.catalog.get(620)
    def test_bulk_clear_ignores_filters_preserves_installed_and_restores_exact_drafts(self):
        self.ready();self.installer.install()
        self.workspace.save_draft(620,dict(crop=dict(mode='16:10',x=35,y=60)))
        self.workspace.save_draft(730,dict(collection_member=True,excluded=False),True)
        before=copy.deepcopy(self.workspace.data['drafts']);catalog=self.service.catalog.path.read_bytes()
        export={str(p.relative_to(self.installer.destination)):p.read_bytes() for p in self.installer.destination.rglob('*') if p.is_file()}
        self.workspace.deselect_all()
        self.assertEqual(self.workspace.summary()['included_count'],0)
        undo=self.workspace.summary()['selection_undo'];self.assertEqual(undo['count'],2)
        self.workspace.deselect_all();self.assertEqual(self.workspace.summary()['selection_undo'],undo)
        self.assertEqual(catalog,self.service.catalog.path.read_bytes())
        self.assertEqual(export,{str(p.relative_to(self.installer.destination)):p.read_bytes() for p in self.installer.destination.rglob('*') if p.is_file()})
        self.workspace.undo_selection(undo['token']);self.assertEqual(self.workspace.data['drafts'],before)
        self.assertEqual(self.workspace.summary()['included_count'],2)
        self.assertIsNone(self.workspace.summary()['selection_undo'])

    def test_undo_rejects_stale_token_and_new_edit_without_overwriting_it(self):
        self.ready();self.workspace.deselect_all();token=self.workspace.summary()['selection_undo']['token']
        with self.assertRaises(ScreensaverError):self.workspace.undo_selection('wrong')
        self.workspace.save_draft(730,dict(collection_member=True,excluded=False),True)
        before=copy.deepcopy(self.workspace.data)
        with self.assertRaises(ScreensaverError):self.workspace.undo_selection(token)
        self.assertEqual(before,self.workspace.data)

    def test_failed_draft_save_is_atomic_and_successful_clear_survives_restart(self):
        self.ready();before=copy.deepcopy(self.workspace.data)
        with patch.object(self.workspace,'_save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.workspace.deselect_all()
        self.assertEqual(before,self.workspace.data)
        self.workspace.deselect_all();loaded=CollectionWorkspace(self.service,self.installer,self.delegation)
        self.assertEqual(loaded.summary()['included_count'],0);self.assertIsNone(loaded.summary()['selection_undo'])

    def test_legacy_membership_and_hidden_games_are_all_explicitly_deselected(self):
        for n in (620,730):
            self.service.catalog.data['games'][str(n)].pop('collection_member',None)
            self.service.catalog.data['games'][str(n)]['excluded']=False
        self.service.catalog.save();self.workspace.deselect_all()
        self.assertEqual(self.workspace.summary()['included_count'],0)
        self.workspace.commit();self.assertEqual(self.workspace.summary()['included_count'],0)
        self.assertTrue(all(not g['collection_member'] for g in self.service.catalog.games()))

    def test_delete_only_owned_export_keeps_cached_media_options_and_game_choices(self):
        game=self.ready();self.installer.install();self.workspace.save_draft(730,dict(collection_member=True),True)
        media={str(p.relative_to(self.service.root)):p.read_bytes() for p in self.service.root.rglob('*') if p.is_file() and p.suffix in {'.gif','.jpg','.png'}}
        options=self.service.catalog.options();self.workspace.delete_collection()
        self.assertFalse(self.installer.destination.exists());self.assertEqual(self.workspace.summary()['included_count'],0)
        self.assertEqual(self.workspace.summary()['draft_count'],0);self.assertEqual(self.workspace.summary()['task']['state'],'idle')
        self.assertEqual(options,self.service.catalog.options())
        self.assertEqual(media,{str(p.relative_to(self.service.root)):p.read_bytes() for p in self.service.root.rglob('*') if p.is_file() and p.suffix in {'.gif','.jpg','.png'}})
        self.assertEqual(game['media'],self.service.catalog.get(620)['media'])
        self.workspace.save_draft(620,dict(collection_member=True,excluded=False),True)
        self.assertEqual(self.workspace.summary()['included_count'],1)

    def test_foreign_destination_prevents_even_metadata_deletion(self):
        self.ready();self.installer.destination.mkdir(parents=True);(self.installer.destination/'personal.txt').write_bytes(b'keep')
        before=self.service.catalog.path.read_bytes();drafts=copy.deepcopy(self.workspace.data)
        with self.assertRaises(ScreensaverError):self.workspace.delete_collection()
        self.assertEqual(before,self.service.catalog.path.read_bytes());self.assertEqual(drafts,self.workspace.data)
        self.assertEqual((self.installer.destination/'personal.txt').read_bytes(),b'keep')

    def test_failed_export_rename_restores_catalog_workspace_and_export(self):
        self.ready();self.installer.install();self.workspace.save_draft(730,dict(collection_member=True),True)
        before=self.service.catalog.path.read_bytes();drafts=self.workspace.path.read_bytes();selection=copy.deepcopy(self.workspace.data)
        original=Path.rename
        def fail_export(path,target):
            if path==self.installer.destination:raise OSError('rename failed')
            return original(path,target)
        with patch.object(Path,'rename',fail_export):
            with self.assertRaises(OSError):self.workspace.delete_collection()
        self.assertEqual(before,self.service.catalog.path.read_bytes());self.assertEqual(drafts,self.workspace.path.read_bytes())
        self.assertEqual(selection,self.workspace.data);self.assertTrue(self.installer.status(True)['installed'])

    def test_delete_metadata_failure_preserves_export_and_catalog(self):
        self.ready();self.installer.install();before=self.service.catalog.path.read_bytes()
        with patch.object(self.workspace,'_save',side_effect=OSError('write failed')):
            with self.assertRaises(OSError):self.workspace.delete_collection()
        self.assertEqual(before,self.service.catalog.path.read_bytes());self.assertTrue(self.installer.status(True)['installed'])

    def test_owned_autonomous_binding_is_removed_once_after_export_commit(self):
        self.ready();self.installer.install();marker=self.installer.destination/'.decky-animated-screensaver.json'
        value=json.loads(marker.read_text());value['jsaux']={'controller':'GabeCubeAura'};token=value['bridge_token'];marker.write_text(json.dumps(value))
        remove=Mock();self.installer.delegation=type('Binding',(),{'remove_installed_player':staticmethod(remove)})()
        self.workspace.delete_collection();remove.assert_called_once_with(token)
        self.workspace.delete_collection();remove.assert_called_once_with(token)

    def test_bulk_actions_refuse_preparation_and_paused_work(self):
        self.ready();before=copy.deepcopy(self.workspace.data)
        for target in (self.service,self.delegation):
            method='_busy' if target is self.service else 'busy'
            with patch.object(target,method,return_value=True):
                for action in (self.workspace.deselect_all,self.workspace.delete_collection):
                    with self.assertRaises(ScreensaverError):action()
        self.workspace.data['task']['state']='paused'
        with self.assertRaises(ScreensaverError):self.workspace.deselect_all()
        self.workspace.data['task']=before['task'];self.assertEqual(before,self.workspace.data)

class CollectionManagementRPCTests(PluginTests):
    async def test_real_rpc_confirmation_roundtrip_and_no_cleanup_or_prepare_for_clear(self):
        await self.call('scan');await self.call('prepare');await self.finish();await self.call('install',confirm=True)
        original=self.provider.path.read_bytes() if hasattr(self.provider,'path') else None
        export=self.plugin.installer.destination
        reply=await self.call('workspace_delete_collection');self.assertEqual(reply['error'],'confirmation_required');self.assertTrue(export.exists())
        state=await self.call('workspace_deselect_all');self.assertEqual(state['workspace']['included_count'],0);self.assertTrue(export.exists())
        undo=state['workspace']['selection_undo'];state=await self.call('workspace_undo_selection',token=undo['token']);self.assertEqual(state['workspace']['included_count'],2)
        stop=Mock(wraps=self.plugin.jsaux.stop)
        with patch.object(self.plugin.jsaux,'stop',stop):state=await self.call('workspace_delete_collection',confirm=True)
        stop.assert_called_once();self.assertFalse(export.exists());self.assertFalse(state['installation']['installed']);self.assertEqual(state['workspace']['included_count'],0)
        self.assertTrue(state['key_configured']);self.assertEqual(state['ready_count'],0)
        if original is not None:self.assertEqual(original,self.provider.path.read_bytes())

    async def test_real_rpc_busy_and_update_refusal_are_readable_data(self):
        self.plugin.updater.phase='installing'
        for name in ('workspace_deselect_all','workspace_undo_selection','workspace_delete_collection'):
            result=await self.call(name,confirm=True);self.assertEqual(result['schema'],'das-action-error-v1');self.assertEqual(result['error'],'update_busy')
        self.plugin.updater.phase='idle';self.plugin.workspace.data['task']['state']='paused'
        result=await self.call('workspace_deselect_all');self.assertEqual(result['error'],'busy')
        self.plugin.workspace.data['task']['state']='idle'

# Avoid rediscovering the imported parent classes and duplicating their suites.
for cls,parent in ((CollectionManagementTests,WorkspaceTests),(CollectionManagementRPCTests,PluginTests)):
    for name in dir(parent):
        if name.startswith('test_') and name not in cls.__dict__:setattr(cls,name,None)
del WorkspaceTests,PluginTests,cls,parent
