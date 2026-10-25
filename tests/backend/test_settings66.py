import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import test_workspace as fixture
from das.core.catalog import atomic_json,ScreensaverError
from das.settings_backup import SettingsBackup,validate_backup,recover
from das.studio.storage import Store
from das.jsaux.manager import DEFAULTS
from das.github import GitHub,UpdateError,API,REPO
from das.display_name import migrate,DISPLAY,LEGACY

class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.WorkspaceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.panel=SimpleNamespace(options=dict(DEFAULTS),lock=threading.RLock(),display_busy=lambda:False)
        self.b=SettingsBackup(self.f.service,self.f.workspace,self.panel,self.f.root)
    def test_export_roundtrip_private_permissions_and_no_secrets(self):
        self.f.service.catalog.data['private_token']='TOP-SECRET'
        value=self.b.export();p=Path(value['path']);self.assertEqual(p.stat().st_mode&0o777,0o600)
        self.assertEqual(self.b.read(str(p)),self.b.snapshot());self.assertNotIn('SECRET',p.read_text())
        self.assertNotIn('games',self.b.read(str(p)))
    def test_import_persists_all_three_groups_and_keeps_games_credentials_and_installed_files(self):
        raw=self.b.snapshot();raw['options']['shuffle']=False;raw['faceplate']['page_seconds']=42;raw['interface']['layout']='list'
        path=self.f.root/'import.json';atomic_json(path,raw)
        self.f.service.catalog.data['custom_secret']='keep';self.f.service.catalog.save()
        before=copy.deepcopy(self.f.service.catalog.data['games'])
        self.b.restore(str(path));self.assertFalse(self.f.service.catalog.options()['shuffle'])
        loaded=Store(self.f.service.catalog.root);self.assertEqual(loaded.data['jsaux']['page_seconds'],42)
        self.assertEqual(self.f.workspace.data['layout'],'list');self.assertEqual(loaded.data['games'],before)
        self.assertEqual(loaded.data['custom_secret'],'keep');self.assertTrue(list((self.f.root/'Documents/AnimatedScreensaver').glob('*.json')))
        self.assertFalse(self.f.installer.destination.exists())
    def test_invalid_schema_unknown_keys_ranges_and_secrets_never_mutate(self):
        before=self.f.service.catalog.path.read_bytes()
        for change in [lambda x:x.update(secret='no'),lambda x:x['options'].update(scene_seconds=True),lambda x:x['faceplate'].update(page_seconds=0),lambda x:x['interface'].update(layout='invalid'),lambda x:x.update(schema='foreign')]:
            raw=self.b.snapshot();change(raw);path=self.f.root/'invalid.json';atomic_json(path,raw)
            with self.assertRaises((ScreensaverError,ValueError,TypeError)):self.b.restore(str(path))
            self.assertEqual(before,self.f.service.catalog.path.read_bytes())
    def test_failure_between_files_rolls_back_memory_and_disk(self):
        before=self.f.service.catalog.path.read_bytes();raw=self.b.snapshot();raw['options']['shuffle']=False
        path=self.f.root/'import.json';atomic_json(path,raw)
        with patch.object(self.f.workspace,'_save',side_effect=OSError('full')):
            with self.assertRaises(OSError):self.b.restore(str(path))
        self.assertEqual(json.loads(before),json.loads(self.f.service.catalog.path.read_bytes()))
        self.assertEqual(self.f.service.catalog.options(),json.loads(before)['options'])
        self.assertFalse((self.f.service.catalog.root/'settings-import-journal.json').exists())
    def test_startup_journal_recovers_interrupted_import_before_load(self):
        root=self.f.service.catalog.root;old=copy.deepcopy(self.f.service.catalog.data)
        atomic_json(root/'settings-import-journal.json',dict(catalog=old,workspace=None))
        self.f.service.catalog.configure(dict(shuffle=False));recover(root)
        self.assertEqual(json.loads(self.f.service.catalog.path.read_text()),old)
        self.assertFalse((root/'settings-import-journal.json').exists())
    def test_symlinks_external_paths_oversized_and_busy_rejected(self):
        p=self.f.root/'valid.json';atomic_json(p,self.b.snapshot());link=self.f.root/'link.json';link.symlink_to(p)
        for path in (str(link),'/private/tmp/foreign.json'):
            with self.assertRaises(ScreensaverError):self.b.read(path)
        p.write_bytes(b' '*65537)
        with self.assertRaises(ScreensaverError):self.b.read(str(p))
        atomic_json(p,self.b.snapshot());self.f.workspace.data['task']['state']='paused'
        with self.assertRaises(ScreensaverError):self.b.restore(str(p))
    def test_display_name_migration_keeps_folder_and_rehashes_descriptor(self):
        folder=self.f.root/LEGACY;folder.mkdir();atomic_json(folder/'plugin.json',dict(name=LEGACY,flags=['root']))
        digest=hashlib.sha256((folder/'plugin.json').read_bytes()).hexdigest();atomic_json(folder/'manifest.sha256.json',{'plugin.json':digest})
        self.assertTrue(migrate(folder));self.assertEqual(json.loads((folder/'plugin.json').read_text())['name'],DISPLAY)
        self.assertEqual(json.loads((folder/'manifest.sha256.json').read_text())['plugin.json'],hashlib.sha256((folder/'plugin.json').read_bytes()).hexdigest())
        self.assertFalse(migrate(folder));self.assertEqual(folder.name,LEGACY)

import test_plugin as rpc_fixture
class SettingsRPCTests(unittest.IsolatedAsyncioTestCase):
    call=rpc_fixture.PluginTests.call
    async def asyncSetUp(self):
        await rpc_fixture.PluginTests.asyncSetUp(self)
        self.plugin.settings_backup.home=self.root
    async def test_real_rpc_requires_confirmation_and_keeps_secrets_out(self):
        snap=await self.call('settings_snapshot');self.assertEqual(snap['backup']['schema'],'das-settings-v1')
        self.assertNotIn('temporary-test-key',json.dumps(snap));export=await self.call('settings_export')
        before=self.service.catalog.path.read_bytes()
        result=await self.call('settings_import',path=export['path'])
        self.assertEqual(result['error'],'confirmation_required');self.assertEqual(before,self.service.catalog.path.read_bytes())
        result=await self.call('settings_import',path=export['path'],confirm=True);self.assertTrue(result['restored'])
    async def test_rpc_restore_blocked_while_updater_is_installing(self):
        path=(await self.call('settings_export'))['path'];self.plugin.updater.phase='installing'
        self.assertEqual((await self.call('settings_import',path=path,confirm=True))['error'],'busy')
        self.plugin.updater.phase='idle'

class DisplayMigrationFailureTests(unittest.TestCase):
    def test_manifest_failure_restores_both_original_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);atomic_json(root/'plugin.json',dict(name=LEGACY,flags=['root']))
            atomic_json(root/'manifest.sha256.json',{'plugin.json':hashlib.sha256((root/'plugin.json').read_bytes()).hexdigest()})
            before={name:(root/name).read_bytes() for name in ('plugin.json','manifest.sha256.json')}
            calls=[]
            def write(path,value):
                calls.append(path.name)
                if len(calls)==2:raise OSError('full')
                atomic_json(path,value)
            with patch('das.display_name.atomic_json',side_effect=write):
                with self.assertRaises(OSError):migrate(root)
            for name,raw in before.items():self.assertEqual(json.loads((root/name).read_bytes()),json.loads(raw))
