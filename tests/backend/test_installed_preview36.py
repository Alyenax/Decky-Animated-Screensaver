"""Real immutable export preview; software transport, not optical/USB evidence."""
import copy
import errno
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import os
from types import SimpleNamespace
import unittest
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen
from unittest.mock import patch

from das.core.catalog import ScreensaverError, atomic_json, file_sha256
from das.studio.installer import Installer, MARKER, catalog_script
from das.studio.preview import Preview
from das.studio.service import StudioService
from das.studio.workspace import CollectionWorkspace
from test_plugin import Codec
from test_studio import Provider, scene, ASSETS


class InstalledPreview36Tests(unittest.TestCase):
    def test_cancel_at_final_return_boundary_still_removes_private_snapshot(self):
        self.install();release=self.preview._release
        def cancel_then_release():
            self.preview.close(request_id='r'*32);release()
        with patch.object(self.preview,'_release',side_effect=cancel_then_release):
            self.preview.installed(self.installer,request_id='r'*32)
        self.assertIsNone(self.preview.snapshot);self.assertFalse(self.preview.transport.files)
        self.assertEqual(list(self.store.managed('preview-snapshots').iterdir()),[])
    def test_snapshot_admission_respects_export_write_lock(self):
        import fcntl
        self.install()
        fd=os.open(self.installer.destination.parent/'.decky-animated-screensaver.lock',os.O_RDWR)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(ScreensaverError) as error:self.preview.installed(self.installer)
            self.assertEqual(error.exception.code,'busy')
            self.assertIsNone(self.preview.snapshot);self.assertFalse(self.preview.transport.files)
        finally:os.close(fd)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.service=StudioService(self.root/'library',Provider(),media=Codec(),games_provider=lambda:[])
        self.addCleanup(self.service.shutdown);self.store=self.service.catalog
        self.store.configure(dict(show_cover=False,name_display='title',scene_seconds=12,framing='16:10'))
        (self.root/'Steam').mkdir()
        self.installer=Installer(self.store,self.root/'Steam',ASSETS)
        self.preview=Preview(self.store,ASSETS,self.service);self.addCleanup(self.preview.close)

    def install(self):
        scene(self.store,620);self.store.update(620,dict(name='Installed Portal'))
        scene(self.store,730);self.store.update(730,dict(name='Installed Counter Strike'))
        self.installer.install('fr')
        self.export=json.loads((self.installer.destination/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').removesuffix(';\n'))
        return copy.deepcopy(self.export)

    def catalog(self):
        return json.loads((self.preview.code/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').removesuffix(';\n'))

    def media_url(self,value,path):
        parsed=urlsplit(value['url'])
        return urlunsplit((parsed.scheme,parsed.netloc,path,'',''))

    def update_export_catalog(self,catalog):
        """Test-only damaged owned receipt, retaining its otherwise valid hashes."""
        path=self.installer.destination/'catalog.js';path.write_bytes(catalog_script(catalog))
        marker=self.installer.destination/MARKER;owned=json.loads(marker.read_text())
        owned['files']['catalog.js']=dict(size=path.stat().st_size,sha256=file_sha256(path));atomic_json(marker,owned)

    def assert_conflict(self):
        with self.assertRaises(ScreensaverError) as failure:self.preview.installed(self.installer,request_id='a'*32)
        self.assertEqual(failure.exception.code,'installation_conflict')
        self.assertIsNone(self.preview.snapshot);self.assertFalse(self.preview.transport.files)

    def test_installed_selection_parameters_and_original_bytes_ignore_working_edits(self):
        original=self.install()
        media={g['id']:{k:(self.installer.destination/g['media'][k]).read_bytes() for k in ('file','thumbnail')} for g in original['games']}
        self.store.configure(dict(scene_seconds=48,framing='16:9',name_display='hidden'))
        self.store.update(620,dict(name='Pending edited name',excluded=True,pending_change=True,crop=dict(mode='16:9',x=5,y=95)))
        scene(self.store,999);self.store.update(999,dict(name='New game not installed'))
        self.store.managed(self.store.get(620)['media']['tv']).write_bytes(b'GIF89a-new-working-cache-bytes')
        workspace=CollectionWorkspace(self.service,self.installer,SimpleNamespace(options={},busy=lambda:False))
        workspace.save_draft(730,dict(crop=dict(mode='16:9',x=10,y=90)))
        drafts=workspace.path.read_bytes()
        before=self.store.path.read_bytes();receipt=(self.installer.destination/MARKER).read_bytes()
        with patch.object(self.store,'save',side_effect=AssertionError('No catalog save')),patch.object(self.service,'_download',side_effect=AssertionError('No API/download')),patch.object(self.service,'_assets',side_effect=AssertionError('No API discovery')),patch.object(self.service.compiler,'prepare',side_effect=AssertionError('No encode')),patch.object(self.service.compiler,'inspect',side_effect=AssertionError('No decoder'),create=True),patch.object(self.installer,'install',side_effect=AssertionError('No install')):
            value=self.preview.installed(self.installer,request_id='b'*32)
        actual=self.catalog()
        self.assertEqual(value['count'],2);self.assertTrue(value['installed'])
        self.assertEqual(actual['settings'],original['settings'])
        self.assertEqual([g['id'] for g in actual['games']],['steam:620','steam:730'])
        self.assertEqual([g['name'] for g in actual['games']],['Installed Portal','Installed Counter Strike'])
        self.assertEqual(self.store.path.read_bytes(),before);self.assertEqual((self.installer.destination/MARKER).read_bytes(),receipt)
        self.assertEqual(workspace.path.read_bytes(),drafts)
        for game in actual['games']:
            for key in ('file','thumbnail'):
                url=self.media_url(value,game['media'][key]);self.assertEqual(urlsplit(url).hostname,'127.0.0.1')
                with urlopen(url) as response:raw=response.read()
                self.assertEqual(hashlib.sha256(raw).digest(),hashlib.sha256(media[game['id']][key]).digest())

    def test_single_installed_game_is_selectable_even_when_removed_from_working_store(self):
        self.install();self.store.data['games'].pop('620');self.store.save()
        value=self.preview.installed(self.installer,620,request_id='c'*32)
        self.assertEqual(value['count'],1);self.assertEqual(self.catalog()['games'][0]['name'],'Installed Portal')
        with self.assertRaises(ScreensaverError) as error:self.preview.installed(self.installer,999)
        self.assertEqual(error.exception.code,'not_ready')

    def test_delegation_credentials_are_removed_and_preview_nonce_is_fresh(self):
        catalog=self.install();catalog.update(jsaux=dict(enabled=True,collection_id='f'*64,relay={'token':'private-jsaux-secret'}),bridge_token='private-steam-secret')
        self.update_export_catalog(catalog)
        first=self.preview.installed(self.installer,request_id='d'*32);actual=self.catalog()
        self.assertNotIn('jsaux',actual);self.assertNotIn('bridge_token',actual)
        self.assertEqual(actual['previewNonce'],first['nonce'])
        self.assertNotIn('private-',(self.preview.code/'catalog.js').read_text())
        self.assertIn("connect-src 'none';",(self.preview.code/'index.html').read_text())
        second=self.preview.installed(self.installer,request_id='e'*32)
        self.assertNotEqual(first['nonce'],second['nonce'])
        self.assertEqual((self.preview.code/'diagnostic-config.js').read_bytes(),(ASSETS/'diagnostic-config.js').read_bytes())

    def test_private_hardlinks_keep_snapshot_alive_across_atomic_export_replacement(self):
        self.install();value=self.preview.installed(self.installer,request_id='f'*32)
        game=self.catalog()['games'][0];url=self.media_url(value,game['media']['file'])
        leaf=next(p for p in Path(self.preview.snapshot.name).iterdir() if p.suffix=='.gif')
        installed=next(self.installer.destination.glob('media/*.gif'))
        self.assertEqual(leaf.stat().st_ino,installed.stat().st_ino)
        raw=installed.read_bytes();scene(self.store,999);self.installer.install('en')
        with urlopen(url) as response:self.assertEqual(response.read(),raw)
        self.preview.close(request_id='f'*32);self.assertFalse(leaf.exists())

    def test_cross_filesystem_fallback_copies_verified_bytes_and_cleans_on_close(self):
        self.install()
        with patch('das.studio.preview.os.link',side_effect=OSError(errno.EXDEV,'Cross-device link')):
            value=self.preview.installed(self.installer,request_id='g'*32)
        game=self.catalog()['games'][0];snapshot=Path(self.preview.snapshot.name)
        leaf=next(p for p in snapshot.iterdir() if p.suffix=='.gif');installed=next(self.installer.destination.glob('media/*.gif'))
        self.assertNotEqual(leaf.stat().st_ino,installed.stat().st_ino)
        with urlopen(self.media_url(value,game['media']['file'])) as response:self.assertEqual(response.read(),installed.read_bytes())
        self.preview.close();self.assertFalse(snapshot.exists())

    def test_closed_request_and_late_cleanup_do_not_close_current_snapshot(self):
        self.install();self.preview.close(request_id='h'*32)
        with self.assertRaises(ScreensaverError) as error:self.preview.installed(self.installer,request_id='h'*32)
        self.assertEqual(error.exception.code,'preview_cancelled')
        old=self.preview.installed(self.installer,request_id='i'*32)
        current=self.preview.installed(self.installer,request_id='j'*32)
        self.preview.close(request_id='i'*32);self.preview.close(nonce=old['nonce'])
        with urlopen(current['url']) as response:self.assertEqual(response.status,200)
        self.assertEqual(self.preview.nonce,current['nonce'])
        self.preview.close(request_id='j'*32);self.assertFalse(self.preview.transport.files)

    def test_close_during_copy_cancels_and_removes_partial_snapshot(self):
        self.install();entered=threading.Event();release=threading.Event();errors=[]
        def link(*args,**kwargs):entered.set();release.wait(2);raise OSError(errno.EXDEV,'Cross-device link')
        def open_snapshot():
            try:self.preview.installed(self.installer,request_id='k'*32)
            except ScreensaverError as error:errors.append(error.code)
        with patch('das.studio.preview.os.link',side_effect=link):
            worker=threading.Thread(target=open_snapshot);worker.start();self.assertTrue(entered.wait(1))
            self.preview.close(request_id='k'*32);release.set();worker.join(3)
        self.assertFalse(worker.is_alive());self.assertEqual(errors,['preview_cancelled'])
        self.assertIsNone(self.preview.snapshot);self.assertFalse(self.preview.transport.files)
        self.assertEqual(list(self.store.managed('preview-snapshots').iterdir()),[])

    def test_modified_media_hash_is_rejected_not_served(self):
        self.install();path=next(self.installer.destination.glob('media/*.gif'));raw=path.read_bytes()
        path.write_bytes(bytes([raw[0]^1])+raw[1:]);self.assert_conflict()

    def test_modified_catalog_hash_is_rejected_before_snapshot(self):
        self.install();path=self.installer.destination/'catalog.js';path.write_bytes(path.read_bytes()+b' ')
        self.assert_conflict()

    def test_symlink_media_is_rejected_without_following_it(self):
        self.install();path=next(self.installer.destination.glob('media/*.gif'))
        other=self.root/'foreign.gif';other.write_bytes(path.read_bytes());path.unlink();path.symlink_to(other)
        self.assert_conflict();self.assertTrue(other.exists())

    def test_traversal_media_reference_is_rejected_with_matching_catalog_hash(self):
        catalog=self.install();catalog['games'][0]['media']['file']='media/../../foreign.gif'
        self.update_export_catalog(catalog);self.assert_conflict()

    def test_missing_or_structured_media_reference_is_rejected_as_a_snapshot_error(self):
        original=self.install()
        for value in (None,[],{},['media/0000.gif'],{'path':'media/0000.gif'}):
            with self.subTest(value=value):
                catalog=copy.deepcopy(original);catalog['games'][0]['media']['file']=value
                self.update_export_catalog(catalog);self.assert_conflict()

    def test_optional_cover_and_logo_are_rewritten_into_verified_local_capabilities(self):
        catalog=self.install();game=catalog['games'][0]
        game['cover']=dict(file=game['media']['thumbnail'],animated=False)
        game['logo']=dict(file=game['media']['thumbnail'],animated=False)
        self.update_export_catalog(catalog);value=self.preview.installed(self.installer)
        actual=self.catalog()['games'][0]
        for key in ('cover','logo'):
            self.assertEqual(actual[key]['file'],actual['media']['thumbnail'])
            with urlopen(self.media_url(value,actual[key]['file'])) as response:self.assertTrue(response.read())

    def test_cross_filesystem_copy_refuses_insufficient_space_and_cleans_up(self):
        self.install()
        with patch('das.studio.preview.os.link',side_effect=OSError(errno.EXDEV,'Cross-device link')),patch('das.studio.preview.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaises(ScreensaverError) as error:self.preview.installed(self.installer)
        self.assertEqual(error.exception.code,'storage_limit')
        self.assertIsNone(self.preview.snapshot);self.assertFalse(self.preview.transport.files)

    def test_no_installation_is_not_ready_and_never_prepares(self):
        scene(self.store)
        with patch.object(self.service,'prepare',side_effect=AssertionError('No preparation')):
            with self.assertRaises(ScreensaverError) as error:self.preview.installed(self.installer)
        self.assertEqual(error.exception.code,'not_ready')
        self.assertIsNone(self.preview.snapshot);self.assertFalse(self.installer.destination.exists())


if __name__=='__main__':unittest.main()
