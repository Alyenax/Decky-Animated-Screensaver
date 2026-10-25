import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from zipfile import ZipFile,ZipInfo
from urllib.request import Request
from das.github import API,GitHub,Redirect,UpdateError
from das.updates import NAME,Updater,choose_release,release_assets,stage_archive,version,checksum
from das.update_helper import transaction

class Response(io.BytesIO):pass

def package(v):
    files={'main.py':b'# fixture','plugin.json':json.dumps(dict(name=NAME,flags=['root'])).encode(),
        'package.json':json.dumps(dict(version=v)).encode(),'dist/index.js':b'fixture','LICENSE':b'GPLv3','py_modules/das/__init__.py':b''}
    files['manifest.sha256.json']=json.dumps({k:hashlib.sha256(v).hexdigest() for k,v in files.items()}).encode()
    return files

def archive(files):
    out=io.BytesIO()
    with ZipFile(out,'w') as z:
        for k,v in files.items():z.writestr(NAME+'/'+k,v)
    return out.getvalue()

def release(v,prerelease=True):
    return dict(tag_name='v'+v,prerelease=prerelease,html_url='https://github.com/Alyenax/'+NAME+'/releases/tag/v'+v,assets=[
        dict(name=NAME+'-v'+v+'.zip',size=100,url=API+'/releases/assets/1'),dict(name='SHA256SUMS',size=100,url=API+'/releases/assets/2')])


class UpdateTests(unittest.TestCase):
    def test_daily_interval_is_validated_persisted_and_reschedules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);updater=Updater(root/'updates',root/NAME,'0.1.0-alpha.8')
            updater.configure({'interval_minutes':1440,'auto_check':False})
            self.assertTrue(updater.reschedule.is_set())
            again=Updater(root/'updates',root/NAME,'0.1.0-alpha.8')
            self.assertEqual(again.status()['interval_minutes'],1440);self.assertFalse(again.status()['auto_check'])
            for invalid in (True,1,5,15,60,720,'1440'):
                with self.assertRaises(UpdateError):updater.configure({'interval_minutes':invalid})
            updater.shutdown();again.shutdown()

    def test_scheduler_replaces_old_wait_when_interval_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);updater=Updater(root/'updates',root/NAME,'0.1.0-alpha.8');waits=[]
            class Wake:
                def set(self):pass
                def clear(self):pass
                def wait(self,delay):
                    waits.append(delay)
                    if len(waits)==1:
                        updater.configure({'interval_minutes':1440});return True
                    updater.closed.set();return False
            updater.reschedule=Wake();updater.start();updater.scheduler.join(1)
            self.assertFalse(updater.scheduler.is_alive());self.assertEqual(len(waits),2)
            self.assertAlmostEqual(waits[0],86400,delta=.1);self.assertAlmostEqual(waits[1],86400,delta=.1);updater.shutdown()

    def test_channel_parity_and_semver_stable_after_prereleases(self):
        rows=[release('0.1.0-alpha.8'),release('0.1.0-beta.2'),release('0.1.0',False),dict(release('9.0.0',False),draft=True)]
        with self.assertRaises(UpdateError):choose_release(rows,'private')
        self.assertEqual(choose_release(rows,'stable')['tag_name'],'v0.1.0')
        self.assertEqual(choose_release(rows,'beta')['tag_name'],'v0.1.0')
        self.assertGreater(version('0.1.0'),version('0.1.0-beta.999'))
        self.assertIsNone(choose_release([release('0.1.0-alpha.8')],'stable'))
        with self.assertRaises(UpdateError):version('0.1.0; touch /tmp/x')
    def test_repository_assets_and_unique_checksum(self):
        r=release('0.1.0-alpha.8');self.assertEqual(release_assets(r)[0],'0.1.0-alpha.8')
        r['assets'][0]['url']='https://github.com/other/file'
        with self.assertRaises(UpdateError):release_assets(r)
        digest='a'*64;self.assertEqual(checksum((digest+'  file.zip\n').encode(),'file.zip'),digest)
        with self.assertRaises(UpdateError):checksum((digest+'  file.zip\n'+digest+'  file.zip').encode(),'file.zip')
    def test_archive_manifest_identity_extra_files_escape_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);p=root/'update.zip';files=package('0.1.0-alpha.8');p.write_bytes(archive(files))
            staged=stage_archive(p,root/'staged','0.1.0-alpha.8');self.assertEqual(json.loads((staged/'package.json').read_text())['version'],'0.1.0-alpha.8')
            for edits in ({**files,'../escape':b'x'},{**files,'hidden.py':b'x'},{**files,'main.py':b'tampered'}):
                p.write_bytes(archive(edits))
                with self.assertRaises(UpdateError):stage_archive(p,root/'staged','0.1.0-alpha.8')
            with ZipFile(p,'w') as z:
                info=ZipInfo(NAME+'/main.py');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'/etc/passwd')
            with self.assertRaises(UpdateError):stage_archive(p,root/'staged','0.1.0-alpha.8')
            self.assertFalse((root/'escape').exists())
    def test_actual_check_download_checksum_stage_and_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);blob=archive(package('0.1.0'));digest=hashlib.sha256(blob).hexdigest();r=release('0.1.0',False)
            name=r['assets'][0]['name'];r['assets'][0].update(size=len(blob),digest='sha256:'+digest)
            responses={API+'/releases?per_page=50':json.dumps([r]).encode(),API+'/releases/assets/1':blob,API+'/releases/assets/2':(digest+'  '+name+'\n').encode()}
            calls=[]
            def open(req,**kw):calls.append(req.full_url);return Response(responses[req.full_url])
            updater=Updater(root/'updates',root/NAME,'0.1.0-alpha.7',opener=open);self.addCleanup(updater.shutdown)
            updater.configure({'auto_check':False,'interval_minutes':1440})
            self.assertEqual(calls,[])
            updater.check();updater.thread.join(2);self.assertEqual(updater.phase,'available')
            updater.prepare();updater.thread.join(2);self.assertEqual(updater.phase,'ready',updater.error)
            self.assertTrue(updater.staged.is_dir());self.assertTrue(updater.status()['confirmation'])
            with self.assertRaises(UpdateError):updater.install('wrong')
            updater.blocked=lambda:True
            with self.assertRaises(UpdateError):updater.install(updater.confirmation)
            self.assertFalse((root/'updates/transaction.json').exists());self.assertNotIn('ghu_',json.dumps(updater.status()))
    def test_transaction_success_health_failure_rolls_back_and_preserves_settings(self):
        for healthy in (True,False):
            with self.subTest(healthy=healthy),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary).resolve();runtime=root/'updates';runtime.mkdir();active=root/NAME;active.mkdir()
                for relative,data in package('0.1.0-alpha.7').items():
                    path=active/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                archive_path=root/'update.zip';archive_path.write_bytes(archive(package('0.1.0-alpha.8')))
                staged=stage_archive(archive_path,runtime/'staged','0.1.0-alpha.8');settings=root/'library';settings.mkdir();(settings/'keep').write_text('preserved')
                calls=[]
                class Service:
                    def stop(self):calls.append('stop')
                    def start(self):calls.append('start')
                    def wait_inactive(self):return True
                def swap(a,b):
                    temporary_path=root/'swap';os.rename(a,temporary_path);os.rename(b,a);os.rename(temporary_path,b)
                tx=dict(root=str(runtime),active=str(active),staged=str(staged),token='a'*32,from_version='0.1.0-alpha.7',to_version='0.1.0-alpha.8')
                result=transaction(tx,Service(),swap,lambda *a:healthy)
                self.assertEqual(result['phase'],'updated' if healthy else 'rolled_back')
                self.assertEqual(json.loads((active/'package.json').read_text())['version'],'0.1.0-alpha.8' if healthy else '0.1.0-alpha.7')
                self.assertEqual((settings/'keep').read_text(),'preserved');self.assertEqual(calls,['stop','start'] if healthy else ['stop','start','stop','start'])
