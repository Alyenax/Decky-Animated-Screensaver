"""Storage choices reach admission, downloads, derivatives and verified previews."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from das.core.catalog import ScreensaverError,atomic_json,file_sha256
from das.core.preview import PreviewMedia
from das.studio.service import StudioService
from das.studio.storage import Store,validate
from das.studio.installer import Installer
from das.studio.preview import Preview
from test_studio import FakeMedia,Provider,scene,ASSETS
from urllib.request import Request,urlopen
from urllib.parse import urlsplit,urlunsplit

MIB=1024**2

class Storage63Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.service=StudioService(Path(self.tmp.name)/'library',Provider(),media=FakeMedia(),games_provider=lambda:[])
        self.addCleanup(self.service.shutdown);self.store=self.service.catalog

    def test_new_defaults_missing_fields_and_existing_preferences(self):
        self.assertEqual((self.store.options()['storage_mib'],self.store.options()['max_video_mib']),(10240,256))
        self.store.configure(dict(storage_mib=4096,max_video_mib=64))
        restored=Store(self.store.root)
        self.assertEqual((restored.options()['storage_mib'],restored.options()['max_video_mib']),(4096,64))
        with restored.lock:
            restored.data['options'].pop('max_video_mib');restored.save()
        self.assertEqual(Store(self.store.root).options()['max_video_mib'],256)

    def test_requested_quotas_and_unlimited_are_typed_and_persistent(self):
        for value in (10240,12288,15360,0):
            self.store.configure(dict(storage_mib=value))
            self.assertEqual(Store(self.store.root).options()['storage_mib'],value)
        for value in (False,0.0,-1,255,32769,'0'):
            with self.assertRaises(ScreensaverError):validate(dict(storage_mib=value))

    def test_unlimited_quota_keeps_disk_reserve_and_derivative_byte_cap(self):
        source=self.store.managed('sample.gif');source.write_bytes(b'GIF89a')
        self.store.configure(dict(storage_mib=0,max_video_mib=0))
        with patch('das.studio.service.shutil.disk_usage',return_value=SimpleNamespace(free=100*MIB)),patch.object(self.store,'usage',return_value=20*1024*MIB):
            self.service._admit(10*MIB)
            self.assertEqual(self.service._derivative_options(self.store.options(),source)['_storage_output_bytes'],35*MIB)
            with self.assertRaises(ScreensaverError):self.service._admit(37*MIB)
        with patch('das.studio.service.shutil.disk_usage',return_value=SimpleNamespace(free=64*MIB)):
            with self.assertRaises(ScreensaverError):self.service._derivative_options(self.store.options(),source)

    def test_finite_quota_and_per_visual_limit_still_apply(self):
        source=self.store.managed('sample.gif');source.write_bytes(b'GIF89a')
        self.store.configure(dict(storage_mib=10240,max_video_mib=256))
        with patch.object(self.store,'usage',return_value=10*1024*MIB),patch('das.studio.service.shutil.disk_usage',return_value=SimpleNamespace(free=50*1024*MIB)):
            with self.assertRaises(ScreensaverError):self.service._admit(1)
        with patch.object(self.store,'usage',return_value=0),patch('das.studio.service.shutil.disk_usage',return_value=SimpleNamespace(free=50*1024*MIB)):
            self.assertEqual(self.service._derivative_options(self.store.options(),source)['_storage_output_bytes'],256*MIB)

    def test_cached_visual_above_old_128_mib_limit_is_accepted_then_respects_lower_setting(self):
        source=self.store.managed('sources/large.gif');source.parent.mkdir()
        with source.open('wb') as stream:stream.write(b'GIF89a');stream.truncate(129*MIB)
        asset=dict(url='https://cdn.steamgriddb.com/large.gif')
        identity=hashlib.sha256(asset['url'].encode()).hexdigest()
        atomic_json(source.parent/(identity+'.json'),dict(path=str(source.relative_to(self.store.root)),sha256=file_sha256(source)))
        self.assertEqual(self.service._download(asset),source)
        self.store.configure(dict(max_video_mib=128))
        with self.assertRaises(ScreensaverError) as error:self.service._download(asset)
        self.assertEqual(error.exception.code,'visual_size_limit')
        # Studio may register verified large media; other preview users keep their default cap.
        bounded=PreviewMedia(self.store.root)
        with self.assertRaises(ValueError):bounded._safe(source)
        studio=PreviewMedia(self.store.root,maximum_media_bytes=None)
        self.assertEqual(studio._safe(source),source)

    def test_export_over_old_two_gib_limit_uses_selected_quota_and_actual_disk(self):
        # Real export admission with virtual source sizes; stop at the first
        # copy so the test never allocates or hashes several gigabytes.
        sources=[self.store.managed(f'export-{n}.gif') for n in (620,621,622)]
        for source in sources:source.write_bytes(b'GIF89a')
        steam=Path(self.tmp.name)/'Steam';steam.mkdir();installer=Installer(self.store,steam,ASSETS)
        original=Path.stat
        def sized(path,*args,**kw):
            value=original(path,*args,**kw)
            if path not in sources:return value
            fields=list(value);fields[6]=800*MIB;return os.stat_result(fields)
        def catalog(store,resolve):
            for source in sources:resolve(str(source.relative_to(store.root)))
            return dict(games=[dict(id='steam:620')],settings={})
        class Admitted(Exception):pass
        with patch.object(Path,'stat',sized),patch('das.studio.installer.player_catalog',side_effect=catalog),patch('das.studio.installer.shutil.disk_usage',return_value=SimpleNamespace(free=40*1024*MIB)),patch('das.studio.installer.ScreensaverInstaller._copy',side_effect=Admitted):
            for quota in (10240,0):
                self.store.configure(dict(storage_mib=quota))
                with self.assertRaises(Admitted):installer.install()
            self.store.configure(dict(storage_mib=2048))
            with self.assertRaises(ScreensaverError) as error:installer.install()
            self.assertEqual(error.exception.code,'storage_limit')
            self.store.configure(dict(storage_mib=0))
            with patch('das.studio.installer.shutil.disk_usage',return_value=SimpleNamespace(free=2*1024*MIB)):
                with self.assertRaises(ScreensaverError) as error:installer.install()
                self.assertEqual(error.exception.code,'storage_limit')

    def test_installed_visual_above_128_mib_is_served_with_bounded_range_reads(self):
        entry=scene(self.store);source=self.store.managed(entry['media']['tv'])
        with source.open('r+b') as stream:stream.truncate(129*MIB)
        self.store.update(620,dict(sha256={**entry['sha256'],'tv':file_sha256(source)}))
        steam=Path(self.tmp.name)/'Steam';steam.mkdir()
        installer=Installer(self.store,steam,ASSETS);installer.install()
        preview=Preview(self.store,ASSETS,self.service);self.addCleanup(preview.close)
        value=preview.installed(installer)
        catalog=json.loads((preview.code/'catalog.js').read_text().removeprefix('window.SAS_CATALOG=').removesuffix(';\n'))
        origin=urlsplit(value['url']);path=catalog['games'][0]['media']['file']
        url=urlunsplit((origin.scheme,origin.netloc,path,'',''))
        with urlopen(Request(url,headers={'Range':'bytes=0-5'})) as response:
            self.assertEqual(response.status,206);self.assertEqual(response.read(),b'GIF89a')
            self.assertEqual(response.headers['Content-Length'],'6')
