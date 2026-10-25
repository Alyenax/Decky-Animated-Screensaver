"""Public-only release access, legacy preferences and manual installation boundaries."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError
from urllib.request import Request
from das.github import API,GitHub,Redirect,UpdateError,save
from das.updates import Updater,UnavailableUpdater,choose_release
from test_updates import release

class PublicDistributionTests(unittest.TestCase):
    def test_client_only_performs_anonymous_gets_on_pinned_release_endpoints(self):
        calls=[]
        def open(req,**kwargs):calls.append(req);return io.BytesIO(b'[]')
        github=GitHub(opener=open)
        for url,asset in ((API+'/releases?per_page=50',False),(API+'/releases/assets/1',True)):
            github.fetch(url,100,asset)
        for req in calls:
            self.assertEqual(req.get_method(),'GET');self.assertIsNone(req.data)
            self.assertIsNone(req.get_header('Authorization'));self.assertIsNone(req.get_header('Cookie'))
        for url in (API,API+'/contents/reports/x.json',API+'/contents/settings-backups/x.json',API+'/releases/assets/1?x=2','https://evil.test'):
            with self.assertRaises(UpdateError):github.request(url)
        self.assertFalse(hasattr(github,'upload_diagnostic'));self.assertFalse(hasattr(github,'upload_settings'))
    def test_private_repository_denial_does_not_attempt_login_or_fallback(self):
        for code in (401,403,404):
            calls=[]
            def open(req,**kwargs):calls.append(req);raise HTTPError(req.full_url,code,'private-body',{},None)
            with self.assertRaises(UpdateError) as error:GitHub(opener=open).fetch(API+'/releases?per_page=50',100)
            self.assertEqual(error.exception.code,'update_repository_access');self.assertEqual(len(calls),1)
            self.assertNotIn('private-body',str(error.exception))
    def test_redirects_reject_foreign_hosts_and_strip_cross_host_auth(self):
        req=Request(API+'/releases/assets/1',headers={'Authorization':'Bearer old-token'})
        redirect=Redirect().redirect_request(req,None,302,'Found',{},'https://release-assets.githubusercontent.com/release')
        self.assertIsNone(redirect.get_header('Authorization'))
        for url in ('https://evil.test/release','http://github.com/release','https://github.com@evil.test/release'):
            with self.assertRaises(UpdateError):Redirect().redirect_request(req,None,302,'Found',{},url)
    def test_legacy_private_auth_and_automation_are_ignored_without_mutating_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);updates=root/'updates';updates.mkdir()
            auth=updates/'github-auth.json';auth.write_text('invalid-private-data-must-not-be-read')
            save(updates/'preferences.json',dict(channel='private',auto_check=True,auto_install=True,interval_minutes=5))
            opener=Mock(side_effect=AssertionError('No startup network'))
            updater=Updater(updates,root/'plugin','0.1.0',opener=opener);self.addCleanup(updater.shutdown)
            self.assertEqual(updater.preferences,dict(channel='stable',auto_check=True,interval_minutes=1440))
            self.assertFalse(hasattr(updater,'auth'));self.assertFalse(hasattr(updater,'automatic_step'))
            for patch_value in ({'auto_install':True},{'auto_install':False},{'interval_minutes':5},{'interval_minutes':60},{'channel':'private'}):
                with self.assertRaises(UpdateError):updater.configure(patch_value)
            self.assertEqual(auth.read_text(),'invalid-private-data-must-not-be-read');opener.assert_not_called()
            self.assertNotIn('private-data',json.dumps(updater.status()))
    def test_scheduler_checks_only_daily_and_never_downloads_or_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);updater=Updater(root/'updates',root/'plugin','0.1.0');self.addCleanup(updater.shutdown)
            updater.release=release('0.2.0',False);updater.phase='available'
            clock=[0];waits=[];updater.check=Mock();updater.prepare=Mock();updater.install=Mock()
            class Wake:
                def set(self):pass
                def clear(self):pass
                def wait(self,delay):
                    waits.append(delay)
                    if len(waits)==3:updater.closed.set();return False
                    clock[0]+=delay;return False
            updater.reschedule=Wake()
            with patch('das.updates.time.monotonic',side_effect=lambda:clock[0]):
                updater.start();updater.scheduler.join(2)
            self.assertFalse(updater.scheduler.is_alive());self.assertEqual(waits,[86400]*3)
            self.assertEqual(updater.check.call_count,2);updater.prepare.assert_not_called();updater.install.assert_not_called()
    def test_public_channels_never_select_private_alpha_releases(self):
        rows=[release('99.0.0-alpha.99'),release('0.2.0-beta.1'),release('0.1.0',False)]
        self.assertEqual(choose_release(rows,'stable')['tag_name'],'v0.1.0')
        self.assertEqual(choose_release(rows,'beta')['tag_name'],'v0.2.0-beta.1')
        self.assertEqual(UnavailableUpdater('0.1.0').status()['interval_minutes'],1440)
