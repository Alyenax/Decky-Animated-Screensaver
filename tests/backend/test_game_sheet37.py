"""Game-specific cover recipe, migration and actual shared export path."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from das.core.catalog import ScreensaverError
from das.studio.storage import Store,validate
from das.studio.service import StudioService
from das.studio.workspace import CollectionWorkspace
from das.studio.installer import Installer,player_catalog
from das.studio.preview import Preview
from test_studio import Provider,scene,ASSETS
from test_plugin import Codec

class GameSheet37Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.service=StudioService(self.root/'library',Provider(),media=Codec(),games_provider=lambda:[])
        self.addCleanup(self.service.shutdown);self.store=self.service.catalog;scene(self.store,620)
        (self.root/'Steam').mkdir();self.installer=Installer(self.store,self.root/'Steam',ASSETS)
        self.delegation=SimpleNamespace(options={},busy=lambda:False)
        self.workspace=CollectionWorkspace(self.service,self.installer,self.delegation)

    def test_four_corners_persist_restart_preview_and_install_without_encoding(self):
        self.store.configure(dict(show_cover=False,name_display='title'))
        self.service.compiler.prepare=lambda *a,**kw: self.fail('No encoding for position changes')
        for corner in ('bottom-left','bottom-right','top-left','top-right'):
            self.workspace.save_draft(620,dict(cover_position=corner))
            restored=CollectionWorkspace(self.service,self.installer,self.delegation)
            self.assertEqual(restored.overlay(self.store.get(620))['cover_position'],corner)
            preview=Preview(self.store,ASSETS,self.service)
            try:
                preview.open(620,restored.draft_patch(620,dict(cover_position=corner)))
                catalog=json.loads((preview.code/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').removesuffix(';\n'))
                self.assertEqual(catalog['games'][0]['coverPosition'],corner)
                self.assertNotIn('cover_position',self.store.get(620)) if corner=='bottom-left' else None
            finally:preview.close()
            restored.commit();self.installer.install()
            catalog=json.loads((self.installer.destination/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').removesuffix(';\n'))
            self.assertEqual(catalog['games'][0]['coverPosition'],corner)

    def test_old_positions_and_saved_drafts_migrate_without_deleting_choices(self):
        self.store.data['options'].update(cover_position='beside-title',logo_position='beside-title')
        self.store.update(620,dict(branding=dict(mode='logo',position='beside-title')))
        reloaded=Store(self.store.root)
        self.assertEqual(reloaded.options()['cover_position'],'bottom-right')
        self.assertEqual(reloaded.options()['logo_position'],'bottom-left')
        self.assertEqual(reloaded.get(620)['branding'],dict(mode='logo',position='inherit'))
        self.workspace.data['drafts']['620']=dict(revision='old',patch=dict(branding=dict(mode='both',position='beside-title')));self.workspace._save()
        restored=CollectionWorkspace(self.service,self.installer,self.delegation)
        self.assertEqual(restored.overlay(self.store.get(620))['branding'],dict(mode='both',position='inherit'))

    def test_all_logo_and_cover_corners_remain_independent_through_export(self):
        corners=('bottom-left','bottom-right','top-left','top-right')
        for cover in corners:
            for logo in corners:
                self.workspace.save_draft(620,dict(cover_position=cover,branding=dict(mode='logo',position=logo)))
                restored=CollectionWorkspace(self.service,self.installer,self.delegation)
                self.assertEqual(restored.overlay(self.store.get(620))['branding']['position'],logo)
                restored.commit();self.installer.install()
                catalog=json.loads((self.installer.destination/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').removesuffix(';\n'))
                self.assertEqual(catalog['games'][0]['coverPosition'],cover)
                self.assertEqual(catalog['games'][0]['branding']['position'],logo)
                # Changing one preference must never rewrite the other.
                self.workspace.save_draft(620,dict(cover_position=corners[(corners.index(cover)+1)%4]))
                self.workspace.commit()
                self.assertEqual(self.store.get(620)['branding']['position'],logo)

    def test_new_requests_expose_only_four_corner_cover_positions(self):
        for value in ('beside-title','middle','inherit',None,[],{}):
            with self.assertRaises(ScreensaverError):self.workspace.draft_patch(620,dict(cover_position=value))
        for key in ('cover_position','logo_position'):
            with self.assertRaises(ScreensaverError):validate({key:'beside-title'})
        self.assertEqual(player_catalog(self.store)['games'][0]['coverPosition'],'bottom-right')
