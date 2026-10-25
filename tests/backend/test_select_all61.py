"""Complete result selection is metadata-only, scoped and atomic."""
import copy
import unittest
from unittest.mock import patch
import test_workspace as fixture
import test_plugin as rpc_fixture
from das.core.catalog import ScreensaverError
from das.studio.workspace import CollectionWorkspace

class SelectAllTests(unittest.TestCase):
    setUp=fixture.WorkspaceTests.setUp

    def test_complete_installed_scope_preserves_customization_and_unrelated_selection(self):
        self.service.catalog.update(900,dict(name='Online only',installed=False,collection_member=True,excluded=False))
        self.workspace.save_draft(620,dict(crop=dict(mode='16:10',x=35,y=60)))
        for number in range(1000,1025):self.service.catalog.update(number,dict(name='Portal '+str(number),installed=True,collection_member=False,excluded=True))
        before=self.service.catalog.path.read_bytes()
        with patch.object(self.service,'prepare',side_effect=AssertionError('No encoding')),patch.object(self.installer,'install',side_effect=AssertionError('No installation')):
            self.workspace.select_all('pÓrtal')
        rows=[self.workspace.overlay(g) for g in self.service.catalog.games()]
        self.assertEqual(sum(g['collection_member'] and not g['excluded'] for g in rows),27)
        self.assertFalse(self.workspace.overlay(self.service.catalog.get(730))['collection_member'])
        self.assertEqual(self.workspace.overlay(self.service.catalog.get(620))['crop']['x'],35)
        self.assertEqual(before,self.service.catalog.path.read_bytes())
        self.assertEqual(CollectionWorkspace(self.service,self.installer,self.delegation).summary()['included_count'],27)
        with patch.object(self.workspace,'_save',side_effect=AssertionError('Idempotent repeat writes nothing')):self.workspace.select_all('portal')

    def test_failed_write_preserves_drafts_and_undo(self):
        self.workspace.select_all();self.workspace.deselect_all()
        before=copy.deepcopy(self.workspace.data);undo=self.workspace.selection_undo()
        with patch.object(self.workspace,'_save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.workspace.select_all()
        self.assertEqual(before,self.workspace.data);self.assertEqual(undo,self.workspace.selection_undo())
        self.workspace.select_all();self.assertIsNone(self.workspace.selection_undo())

    def test_invalid_or_unknown_ids_and_busy_work_change_nothing(self):
        before=copy.deepcopy(self.workspace.data)
        for ids in ([620,999999],[True],[-1],list(range(101)),'620'):
            with self.assertRaises(ScreensaverError):self.workspace.select_all(appids=ids)
            self.assertEqual(before,self.workspace.data)
        with patch.object(self.delegation,'busy',return_value=True):
            with self.assertRaises(ScreensaverError):self.workspace.select_all()
        self.assertEqual(before,self.workspace.data)

class SelectAllRPCTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=rpc_fixture.PluginTests.asyncSetUp
    call=rpc_fixture.PluginTests.call

    async def test_discovered_results_require_known_ids_and_refresh_membership_without_network(self):
        await self.call('scan')
        rows=[dict(appid=1000+i,name='Discovered '+str(i),installed=False,collection_member=False,excluded=True,status='pending') for i in range(15)]
        self.plugin.discovery._remember(rows)
        with patch.object(self.service,'prepare',side_effect=AssertionError('No preparation')):
            state=await self.call('workspace_select_all',source='top',appids=[g['appid'] for g in rows])
        self.assertEqual(state['workspace']['included_count'],17)
        with patch.object(self.plugin.discovery,'ranking',return_value=dict(items=rows,total=len(rows))):
            result=await self.call('browse_top')
        self.assertTrue(all(g['collection_member'] and not g['excluded'] for g in result['items']))
        self.assertTrue(all(not g['collection_member'] and g['excluded'] for g in rows))
        before=copy.deepcopy(self.plugin.workspace.data)
        state=await self.call('workspace_select_all',source='online',appids=[1000,999999])
        self.assertEqual(state['error'],'not_installed');self.assertEqual(before,self.plugin.workspace.data)

    async def test_installed_query_and_admission_failures_are_actionable(self):
        await self.call('scan')
        await self.call('workspace_deselect_all')
        state=await self.call('workspace_select_all',source='installed',query='Portal')
        self.assertEqual(state['workspace']['included_count'],1)
        before=copy.deepcopy(self.plugin.workspace.data)
        for payload in (dict(source='invalid'),dict(source='top',appids=[True]),dict(source='installed',query=['x'])):
            state=await self.call('workspace_select_all',**payload);self.assertEqual(state['error'],'invalid_setting')
        with patch.object(self.plugin.workspace,'_save',side_effect=OSError('disk full')):
            state=await self.call('workspace_select_all',source='installed');self.assertEqual(state['error'],'collection_change_failed')
        self.assertEqual(before,self.plugin.workspace.data)
        with patch.object(self.plugin.workspace,'busy',return_value=True):
            state=await self.call('workspace_select_all',source='installed');self.assertEqual(state['error'],'busy')
