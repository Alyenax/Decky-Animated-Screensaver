import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest
from das.core.catalog import atomic_json
from das.studio.service import StudioService
from das.studio.storage import Store
from das.studio.migration import start
from test_studio import scene,FakeMedia

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.old=Store(self.root/'old');scene(self.old);(self.old.root/'prepare.lock').touch(mode=0o600)
        (self.old.root/'steamgriddb-secret.json').write_text('must-never-copy')
        self.old.configure({'scene_seconds':30,'show_cover':False})
        self.service=StudioService(self.root/'new',media=FakeMedia());self.addCleanup(self.service.shutdown)
    def finish(self):
        self.service.thread.join(3);self.assertFalse(self.service.thread.is_alive())
    def test_unlimited_quota_allows_verified_import_and_remains_unlimited(self):
        self.service.catalog.configure(dict(storage_mib=0));self.old.configure(dict(storage_mib=0))
        start(self.service,self.old.root);self.finish()
        self.assertEqual(self.service.job['state'],'complete')
        self.assertEqual(self.service.catalog.options()['storage_mib'],0)
        self.assertTrue(self.service.catalog.ready(self.service.catalog.get(620),True))
    def test_verified_copy_preserves_old_files_key_export_and_current_choices(self):
        before={str(p.relative_to(self.old.root)):p.read_bytes() for p in self.old.root.rglob('*') if p.is_file()}
        start(self.service,self.old.root);self.finish()
        self.assertEqual(self.service.job['state'],'complete');row=self.service.catalog.get(620)
        self.assertTrue(self.service.catalog.ready(row,True));self.assertEqual(self.service.catalog.options()['scene_seconds'],30)
        for relative,data in before.items():self.assertEqual((self.old.root/relative).read_bytes(),data)
        self.assertFalse((self.service.root/'steamgriddb-secret.json').exists())
        self.service.catalog.update(620,dict(name='DAS choice'));start(self.service,self.old.root);self.finish()
        self.assertEqual(self.service.catalog.get(620)['name'],'DAS choice')
        self.service.maintenance('purge',True);self.assertFalse(list((self.service.root/'imported').rglob('*.gif')))
        for relative,data in before.items():self.assertEqual((self.old.root/relative).read_bytes(),data)
    def test_corrupted_media_never_partially_imports_or_overwrites(self):
        (self.old.root/scene(self.old)['media']['tv']).write_bytes(b'tampered')
        start(self.service,self.old.root);self.finish()
        self.assertEqual(self.service.catalog.games(),[]);self.assertEqual(self.service.job['error'],'import_unverified')
        self.assertEqual(list((self.service.root/'imported').iterdir()),[])
    def test_source_worker_lock_and_links_fail_closed(self):
        fd=os.open(self.old.root/'prepare.lock',os.O_RDONLY)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);start(self.service,self.old.root);self.finish()
            self.assertEqual(self.service.job['error'],'worker_busy');self.assertEqual(self.service.catalog.games(),[])
        finally:os.close(fd)
        target=self.old.managed(self.old.get(620)['media']['tv']);saved=target.read_bytes();target.unlink()
        elsewhere=self.root/'outside.gif';elsewhere.write_bytes(saved);target.symlink_to(elsewhere)
        start(self.service,self.old.root);self.finish();self.assertEqual(self.service.catalog.games(),[])
        self.assertEqual(self.service.job['error'],'missing_media')
