"""Persisted exact order, atomicity, stale protection and both real exports."""
import copy
import json
import unittest
from unittest.mock import patch
import test_workspace as fixture
from test_studio import scene
from das.core.catalog import ScreensaverError
from das.studio.storage import Store
from das.jsaux.collection import fingerprint
from das.jsaux.manager import DEFAULTS
from das.studio.installer import player_catalog

class ReorderTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.w=self.f.workspace;self.s=self.f.service.catalog
        for n in (620,730,10,42):scene(self.s,n)
        self.s.update(730,dict(collection_member=False))
        self.s.update(42,dict(collection_member=True,excluded=True))
        self.s.configure(dict(shuffle=False))

    def test_read_lists_all_members_and_drafts_without_mutation_or_media_work(self):
        self.w.save_draft(730,dict(collection_member=True,excluded=False))
        before=self.s.path.read_bytes();drafts=copy.deepcopy(self.w.data)
        snap=self.w.order_snapshot()
        self.assertEqual([g['appid'] for g in snap['items']],[620,730,10,42])
        self.assertEqual(self.s.path.read_bytes(),before);self.assertEqual(self.w.data,drafts)
        self.assertTrue(all(set(g)=={'appid','name','thumbnail_url'} for g in snap['items']))

    def test_exact_order_survives_restart_and_controls_collection_and_both_outputs(self):
        snap=self.w.order_snapshot();old=fingerprint(self.f.installer.store.games(),DEFAULTS,self.s.options())
        self.f.installer.install();export=(self.f.installer.destination/'catalog.js').read_bytes()
        self.w.reorder([42,10,620],snap['revision'])
        self.assertEqual([g['appid'] for g in Store(self.s.root).games()],[42,730,10,620])
        self.assertEqual([g['appid'] for g in self.w.library()['items']],[42,10,620])
        self.assertEqual([g['appid'] for g in self.w.library(query='0')['items']],[])
        from das.studio.presentation import ready_games
        self.assertEqual([g['appid'] for g in ready_games(self.s)],[10,620])
        catalog=player_catalog(self.s,lambda path:path)
        self.assertEqual([g['id'] for g in catalog['games']],['steam:10','steam:620'])
        self.assertNotEqual(old,fingerprint(self.s.games(),DEFAULTS,self.s.options()))
        self.assertEqual(export,(self.f.installer.destination/'catalog.js').read_bytes())
        self.assertTrue(self.f.installer.status()['needs_update'])

    def test_exact_permutation_rejects_omissions_duplicates_foreign_ids_and_bad_types(self):
        snap=self.w.order_snapshot();before=copy.deepcopy(self.s.data)
        for value in ([620,10],[620,10,42,730],[620,10,10],[True,10,42],['620',10,42],None,{}):
            with self.assertRaises(ScreensaverError):self.w.reorder(value,snap['revision'])
            self.assertEqual(self.s.data,before)

    def test_stale_order_or_membership_never_overwrites_new_state(self):
        snap=self.w.order_snapshot();self.w.save_draft(730,dict(collection_member=True,excluded=False))
        with self.assertRaises(ScreensaverError) as e:self.w.reorder([42,10,620],snap['revision'])
        self.assertEqual(e.exception.code,'collection_order_changed')
        snap=self.w.order_snapshot();ids=[g['appid'] for g in snap['items']]
        self.w.reorder(ids[::-1],snap['revision'])
        with self.assertRaises(ScreensaverError):self.w.reorder(ids,snap['revision'])

    def test_failed_save_rolls_back_and_noop_keeps_revision(self):
        snap=self.w.order_snapshot();before=copy.deepcopy(self.s.data);revision=self.s.revision;disk=self.s.path.read_bytes()
        self.w.reorder([620,10,42],snap['revision']);self.assertEqual(self.s.revision,revision)
        with patch('das.studio.storage.atomic_json',side_effect=OSError('full')):
            with self.assertRaises(OSError):self.w.reorder([42,10,620],snap['revision'])
        self.assertEqual(self.s.data,before);self.assertEqual(self.s.revision,revision);self.assertEqual(self.s.path.read_bytes(),disk)

    def test_drafts_preferences_and_nonmembers_are_preserved_and_busy_is_rejected(self):
        self.w.save_draft(620,dict(crop=dict(mode='16:10',x=35,y=60)))
        before=copy.deepcopy(self.w.data);options=self.s.options();snap=self.w.order_snapshot()
        self.w.reorder([42,10,620],snap['revision'])
        self.assertEqual(self.w.data,before);self.assertEqual(self.s.options(),options)
        self.assertEqual(self.s.games()[1]['appid'],730)
        self.w.data['task']['state']='paused'
        with self.assertRaises(ScreensaverError):self.w.reorder([620,10,42],self.w.order_snapshot()['revision'])

import test_plugin as plugin_fixture
class ReorderRPCTests(plugin_fixture.PluginTests):
    async def test_real_rpc_save_marks_update_and_invalid_requests_cross_as_user_errors(self):
        await self.call('scan');await self.call('prepare');await self.finish();await self.call('install',confirm=True)
        snapshot=await self.call('workspace_order');ids=[g['appid'] for g in snapshot['items']]
        old=(self.plugin.installer.destination/'catalog.js').read_bytes()
        with patch.object(self.plugin.jsaux,'stop') as stop,patch.object(self.service,'prepare') as prepare:
            result=await self.call('workspace_reorder',appids=ids[::-1],revision=snapshot['revision'])
            self.assertTrue(result['installation']['needs_update']);stop.assert_not_called();prepare.assert_not_called()
        self.assertEqual(old,(self.plugin.installer.destination/'catalog.js').read_bytes())
        result=await self.call('workspace_reorder',appids=ids,revision=snapshot['revision'])
        self.assertEqual(result['schema'],'das-action-error-v1');self.assertEqual(result['error'],'collection_order_changed')
        snapshot=await self.call('workspace_order')
        with patch.object(self.service.catalog,'save',side_effect=OSError('full')):
            result=await self.call('workspace_reorder',appids=ids,revision=snapshot['revision'])
        self.assertEqual(result['error'],'collection_change_failed')
        self.plugin.updater.phase='installing'
        result=await self.call('workspace_reorder',appids=ids,revision=snapshot['revision'])
        self.assertEqual(result['error'],'update_busy');self.plugin.updater.phase='idle'

for name in dir(plugin_fixture.PluginTests):
    if name.startswith('test_') and name not in ReorderRPCTests.__dict__:setattr(ReorderRPCTests,name,None)
