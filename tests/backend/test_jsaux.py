"""Real Unix client against bounded fake broker; no physical device claims."""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from das.jsaux.client import BrokerClient
from das.jsaux.protocol import (BrokerError,LIMITS,OPERATIONS,PROFILE,decode,validate_hello)
from das.jsaux.collection import compile_pages,PALETTE,index_rgb
from das.jsaux.manager import Delegation
from das.studio.service import StudioService
from das.studio.installer import Installer,MARKER
from das.studio.media import Media
from test_studio import scene,ASSETS,FakeMedia

def state():
    return dict(hardware='available',policy=dict(faceplate_enabled=True,display_on=True,suspended=False,
        thermal_blocked=False,priority_active=False,reason=None),steam=dict(observed='active',observation_age_ms=0,
        activation_id='activation1',activation_closed=False),ownership=dict(logical_owner='GabeCubeAura',serial_busy=False,device_key='panel'),
        flash=dict(allowed=True,retry_after_ms=0,policy_revision='policy1',receipt_state='known'),lease=None,
        cache=dict(completed_count=0,completed_bytes=0,staging_bytes=0,evictable_count=0))

def hello():
    return dict(negotiated_version='1.0',contract_revision=4,connection_id='connection1',broker_mono_ms=time.monotonic_ns()//1000000,
        clock_domain='linux-host-clock-monotonic',capabilities=dict(operations=list(OPERATIONS),content_profiles=[PROFILE],
        modes=['sync','async'],serial_owner='GabeCubeAura',tv_only_independent=True,hardware_fallback=False,
        software_coordinated_start=True,physical_alignment_measured=False,content_registration_without_usb=True),limits=dict(LIMITS),state=state())

class Endpoint:
    def __init__(self,root):
        self.root=root;root.mkdir(mode=0o700);self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.socket.bind(str(root/'control.sock'));(root/'control.sock').chmod(0o600);self.socket.listen(2);self.socket.settimeout(.05)
        self.secret='b'*64;self.calls=[];self.hook=None;self.closed=False;self.peers=[]
        (root/'credential.json').write_text(json.dumps(dict(protocol='jsaux-broker',major=1,boot_id='boot1',socket_path=str(root/'control.sock'),capability=self.secret)))
        (root/'credential.json').chmod(0o600)
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while not self.closed:
            try:peer,_=self.socket.accept()
            except socket.timeout:continue
            except OSError:return
            self.peers.append(peer)
            threading.Thread(target=self.serve,args=(peer,),daemon=True).start()
    def serve(self,peer):
        try:
            with peer,peer.makefile('rb') as stream:
                for line in stream:
                    p=json.loads(line);self.calls.append(p)
                    value=self.hook(p) if self.hook else None
                    if value is False:return
                    if value is None:
                        value=hello() if p['op']=='hello' else state() if p['op']=='status' else {'closed':True}
                    reply=dict(protocol='jsaux-broker',version='1.0',boot_id='boot1',request_id=p['request_id'],ok=not isinstance(value,BrokerError))
                    if isinstance(value,BrokerError):reply['error']={'code':value.code}
                    else:reply['result']=value
                    peer.sendall(json.dumps(reply).encode()+b'\n')
        except (OSError,ValueError):pass
    def close(self):
        self.closed=True;self.socket.close()
        for peer in self.peers:
            try:peer.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.thread.join(1)

class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.endpoint=Endpoint(self.root/'runtime');self.addCleanup(self.endpoint.close)
        self.client=BrokerClient(self.endpoint.root);self.addCleanup(self.client.close)
    def test_real_handshake_private_credentials_no_idle_worker(self):
        self.assertEqual(self.client.discover()['hardware'],'available')
        self.assertEqual([p['op'] for p in self.endpoint.calls],['hello'])
        self.assertNotIn(self.endpoint.secret,json.dumps(self.client.cached))
        self.client.status();self.assertEqual(self.endpoint.calls[-1]['op'],'status')
    def test_unsafe_permissions_symlink_credential_and_wrong_uid(self):
        credential=self.endpoint.root/'credential.json';credential.chmod(0o644)
        with self.assertRaises(BrokerError):self.client.discover()
        credential.chmod(0o600);other=self.root/'saved';credential.rename(other);credential.symlink_to(other)
        with self.assertRaises(BrokerError):BrokerClient(self.endpoint.root).discover()
        credential.unlink();other.rename(credential)
        with self.assertRaises(BrokerError):BrokerClient(self.endpoint.root,expected_uid=os.geteuid()+1).discover()
    def test_unknown_contract_and_duplicate_json_fail_closed(self):
        h=hello();h['contract_revision']=5
        with self.assertRaises(BrokerError):validate_hello(h)
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":9007199254740992}'):
            with self.assertRaises(BrokerError):decode(raw)
    def test_registration_chunk_bound_validation_and_no_display_call(self):
        data=b'GIF89a'+b'x'*50000;path=self.root/'input.gif';path.write_bytes(data)
        def respond(p):
            if p['op']=='register_content':return {'upload_id':'upload1','next_offset':0,'limits':dict(LIMITS)}
            if p['op']=='content_chunk':
                import base64
                block=base64.b64decode(p['args']['data_base64']);self.assertLessEqual(len(block),24576)
                return dict(next_offset=p['args']['offset']+len(block))
            if p['op']=='commit_content':return {'validation_id':'validation1'}
        self.endpoint.hook=respond
        self.assertEqual(self.client.register(path,'a'*64),{'validation_id':'validation1'})
        self.assertNotIn('acquire_display',[p['op'] for p in self.endpoint.calls])
        self.assertEqual([p['args']['offset'] for p in self.endpoint.calls if p['op']=='content_chunk'],[0,24576,49152])
    def test_lost_mutation_reply_is_uncertain_no_resend_or_fallback(self):
        self.client.discover();self.endpoint.hook=lambda p:False
        with self.assertRaises(BrokerError) as raised:self.client.acquire(activation_id='a',session_id='s',content_id='c',collection_id='a'*64,mode='sync')
        self.assertTrue(raised.exception.uncertain)
        self.assertEqual(sum(p['op']=='acquire_display' for p in self.endpoint.calls),1)
        with self.assertRaises(BrokerError):self.client.status()

class FakeClient:
    def __init__(self):self.calls=[];self.hello={'limits':dict(LIMITS)};self.current=state()
    def discover(self,refresh=False):return copy.deepcopy(self.current)
    def register(self,path,collection_id):self.calls.append(('register',collection_id));return {'content_id':'content1'}
    def acquire(self,**p):self.calls.append(('acquire',p));return dict(lease_id='lease1',generation=1,operation_id='operation1',alignment_attempt_id='align1',expires_in_ms=8000)
    def ready(self,**p):self.calls.append(('ready',p));return dict(gate_accepted=True)
    def renew(self,**p):self.calls.append(('renew',p));return dict(expires_in_ms=8000)
    def operation(self,**p):return dict(lease_state='active',reason=None,candidate=None,expires_in_ms=8000)
    def tv_started(self,**p):self.calls.append(('started',p));return {}
    def release(self,**p):self.calls.append(('release',p));return {'state':'release-pending'}
    def close(self):pass

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.service=StudioService(self.root/'library',media=FakeMedia(),games_provider=lambda:[])
        self.addCleanup(self.service.shutdown);scene(self.service.catalog)
        (self.root/'Steam').mkdir()
        self.installer=Installer(self.service.catalog,self.root/'Steam',ASSETS)
        self.fake=FakeClient();self.manager=Delegation(self.service,self.installer,self.fake)
        self.installer.delegation=self.manager;self.addCleanup(self.manager.shutdown)
    def prepare_receipt(self):
        # Explicit tiny legacy-window fixture. Fade's 18 frames no longer fit
        # the conservative 2.5s envelope; production preparation uses 15s.
        self.manager.refresh();self.manager.configure(dict(enabled=True,mode='sync',transition='none'));data,details=compile_pages([bytes(3456),bytes([1])*3456],24,'none')
        path=self.service.catalog.managed('identities.gif');path.write_bytes(data)
        self.manager.receipt=dict(details,collection_id=self.manager.identity(),path='identities.gif',content_id='content1')
        self.installer.install()
    def message(self,event='open',sequence=1,**extra):
        return dict(event=event,token=self.installer.token,collection_id=self.manager.identity(),session_id='session1',mode='sync',sequence=sequence,**extra)
    def test_detect_requires_explicit_consent_and_preserves_tv_shuffle(self):
        self.manager.refresh();self.assertFalse(self.manager.options['enabled']);self.assertTrue(self.service.catalog.options()['shuffle'])
        self.manager.configure({'enabled':False,'mode':'async'});self.manager.refresh();self.assertFalse(self.manager.options['enabled'])
        again=Delegation(self.service,self.installer,self.fake);self.assertFalse(again.options['enabled'])
    def test_status_and_preview_have_no_broker_or_hardware_effects(self):
        self.prepare_receipt();self.fake.calls.clear()
        with patch.object(self.fake,'discover',side_effect=AssertionError('No discovery')):
            for _ in range(40):self.manager.status()
            self.assertTrue(self.manager.preview()['data_url'].startswith('data:image/gif;base64,'))
        self.assertEqual(self.fake.calls,[])
    def test_current_faceplate_is_not_recompiled_after_unchanged_tv_preparation(self):
        self.prepare_receipt();self.fake.calls.clear()
        with patch.object(self.manager,'prepare',side_effect=AssertionError('No duplicate GIF preparation')):
            self.manager.after_tv_prepare()
        self.assertEqual(self.fake.calls,[])

    def test_changed_faceplate_is_prepared_by_tv_completion_without_manual_repair(self):
        self.prepare_receipt();self.fake.calls.clear()
        self.manager.configure({'transition':'slide'});self.fake.calls.clear()
        self.assertFalse(self.manager.readiness()['ready'])
        with patch.object(self.manager,'prepare',return_value=None) as prepare:
            self.manager.after_tv_prepare();prepare.assert_called_once_with()
        self.assertEqual(self.fake.calls,[])
    def test_disconnect_hides_hardware_but_preserves_preferences_and_tv_shuffle(self):
        self.prepare_receipt();saved=dict(self.manager.options)
        self.fake.current['hardware']='absent';self.manager.refresh()
        self.assertFalse(self.manager.status()['detected']);self.assertEqual(self.manager.options,saved)
        self.assertIsNotNone(self.manager.export()) # installed listener survives USB loss; backend still refuses hardware
        self.service.configure({'shuffle':True})
        self.manager.configure({'transition':'wipe'})
        self.assertTrue(self.service.catalog.options()['shuffle'])
        with patch.object(self.manager,'prepare',side_effect=AssertionError('No hidden JSAUX preparation')):
            self.manager.after_tv_prepare()
        self.fake.current['hardware']='available';self.manager.refresh()
        self.assertTrue(self.manager.status()['detected']);self.assertTrue(self.manager.options['enabled'])
        self.assertEqual(self.manager.options['transition'],'wipe');self.assertTrue(self.service.catalog.options()['shuffle'])
        self.manager.configure({'enabled':False});self.fake.current['hardware']='absent';self.manager.refresh()
        self.fake.current['hardware']='available';self.manager.refresh();self.assertFalse(self.manager.options['enabled'])
    def test_broker_failure_clears_detection_and_ui_reads_are_coalesced(self):
        self.manager.refresh();self.manager.configure({'enabled':True})
        with patch.object(self.fake,'discover',side_effect=BrokerError('BROKER_UNAVAILABLE')) as discover:
            self.manager.refresh(max_age=5);discover.assert_not_called()
            self.manager.refresh();self.assertFalse(self.manager.status()['detected'])
            self.assertFalse(self.manager.status()['compatible']);self.assertTrue(self.manager.options['enabled'])
            self.manager.refresh(max_age=5);self.assertEqual(discover.call_count,1)
        self.manager.refresh();self.assertTrue(self.manager.status()['detected'])
    def test_stop_still_releases_installed_lease_after_disconnection(self):
        self.prepare_receipt();self.assertTrue(self.manager.player(self.message())['accepted'])
        self.fake.current['hardware']='absent';self.manager.refresh()
        self.assertTrue(self.manager.player(self.message('stop',2,reason='player-ended'))['accepted'])
        self.assertEqual(self.fake.calls[-1][0],'release')
    def test_installed_export_only_and_ready_gate_release_current_owner(self):
        self.prepare_receipt();self.assertEqual(self.installer.jsaux_export['mode'],'sync')
        value=self.manager.player(self.message());self.assertTrue(value['accepted'])
        self.assertEqual([c[0] for c in self.fake.calls],['register','acquire'])
        now=time.monotonic_ns()//1000000
        self.manager.player(self.message('ready',2,ready_mono_ms=now,deadline_mono_ms=now+2500,clock_uncertainty_ms=1))
        self.assertEqual(self.fake.calls[-1][0],'ready')
        self.manager.player(self.message('stop',3,reason='player-ended'));self.assertEqual(self.fake.calls[-1][0],'release')
        self.assertFalse(self.manager.player(self.message())['accepted'])
    def test_wrong_export_token_stale_collection_and_gca_steam_refusal(self):
        self.prepare_receipt();p=self.message();p['token']='wrong';self.assertFalse(self.manager.player(p)['accepted'])
        self.assertEqual(self.fake.calls,[])
        self.fake.current['steam']['observed']='inactive';self.assertFalse(self.manager.player(self.message())['accepted'])
        self.assertEqual(self.fake.calls,[])
    def test_setting_change_requires_new_preparation_never_uses_old_gif(self):
        self.prepare_receipt();self.manager.configure({'transition':'slide'})
        self.assertFalse(self.manager.status()['prepared']['ready']);self.assertIsNone(self.manager.export())

    def test_full_purge_removes_generated_identities_receipt_and_player_readiness(self):
        self.prepare_receipt();directory=self.service.catalog.managed('jsaux');directory.mkdir()
        path=directory/('a'*64+'.gif');path.write_bytes(b'generated')
        foreign=directory/'user.gif';foreign.write_bytes(b'preserved')
        self.manager.receipt['path']=str(path.relative_to(self.service.root))
        self.service.catalog.data['jsaux_collection']=dict(self.manager.receipt);self.service.catalog.save()
        self.assertEqual(self.manager.purge()['files'],1);self.service.maintenance('purge',True)
        self.assertFalse(path.exists());self.assertEqual(foreign.read_bytes(),b'preserved')
        self.assertFalse(self.manager.status()['prepared']['ready']);self.assertNotIn('jsaux_collection',self.service.catalog.data)
        self.assertEqual(self.service.job['history'],[])

    def test_common_preparation_releases_tv_lease_then_queues_identities_and_keeps_details(self):
        self.manager.refresh();self.service._scanned=True;self.service.configure(dict(show_cover=False,show_logo=False))
        observed=[]
        def after():
            with self.service.lease():observed.append(self.service._busy())
        self.service.after_prepare=after
        self.service.prepare();self.service.thread.join(3)
        self.assertEqual(observed,[False]);self.assertEqual(self.service.job['state'],'complete')
        self.assertIn('cache_ready',[h['stage'] for h in self.service.job['history']])
        self.assertIn('complete',[h['stage'] for h in self.service.job['history']])

    def test_stop_during_acquisition_releases_late_lease_without_ready(self):
        self.prepare_receipt();entered=threading.Event();resume=threading.Event();original=self.fake.acquire
        def acquire(**args):
            entered.set();resume.wait(1);return original(**args)
        self.fake.acquire=acquire
        worker=threading.Thread(target=lambda:self.manager.player(self.message()))
        worker.start();self.assertTrue(entered.wait(1));self.manager.stop();resume.set();worker.join(2)
        self.assertFalse(worker.is_alive());self.assertIsNone(self.manager.session)
        self.assertEqual([x[0] for x in self.fake.calls],['register','acquire','release'])

    def test_thirty_cycles_keep_metadata_bounded_and_preview_never_acquires(self):
        self.prepare_receipt()
        for n in range(30):
            p=self.message();p['session_id']='session'+str(n)
            self.assertTrue(self.manager.player(p)['accepted'])
            self.manager.preview();p.update(event='stop',sequence=2,reason='player-ended')
            self.manager.player(p);self.assertIsNone(self.manager.session)
        self.assertLessEqual(len(self.manager.seen),64)
        self.assertEqual(sum(x[0]=='acquire' for x in self.fake.calls),30)
        self.assertEqual(sum(x[0]=='release' for x in self.fake.calls),30)
        self.assertFalse(self.manager.busy())

    @unittest.skipUnless(os.environ.get('DAS_TEST_FFMPEG'),'explicit FFmpeg required')
    def test_actual_isolated_identity_preparation_and_cached_export(self):
        from PIL import Image
        binary=str(Path(os.environ['DAS_TEST_FFMPEG']).resolve())
        self.service.compiler=Media(binary)
        source=self.service.catalog.managed('square.png');Image.new('RGB',(96,96),(245,110,170)).save(source)
        game=self.service.catalog.get(620);game['media']['panel_source']='square.png'
        self.service.catalog.update(620,dict(media=game['media']))
        self.manager.refresh();self.manager.configure({'enabled':True});self.manager.prepare();self.manager.thread.join(15)
        self.assertFalse(self.manager.busy());self.assertEqual(self.manager.reason,'')
        self.assertTrue(self.manager.status()['prepared']['ready'])
        self.assertEqual(self.manager.receipt['duration_cs'],2400)
        self.assertEqual([x[0] for x in self.fake.calls],['register'])
        self.assertIsNotNone(self.manager.export())
        self.assertTrue(self.manager.preview()['data_url'].startswith('data:image/gif;'))

class EncodingTests(unittest.TestCase):
    def test_all_transitions_opaque_native_palette_and_exact_duration(self):
        for kind in ('fade','slide','wipe','dissolve','none'):
            data,receipt=compile_pages([bytes(3456),bytes([255])*3456],8,kind)
            self.assertLessEqual(len(data),196608);self.assertEqual(receipt['duration_cs'],1600)
            self.assertEqual(data[:6],b'GIF89a');self.assertEqual(data[6:10],b'@\x006\x00')
            self.assertEqual(data[13:781],bytes(v for rgb in PALETTE for v in rgb))
            self.assertEqual(data.count(b'NETSCAPE2.0'),1);self.assertEqual(data[-1],59)
    def test_size_limits_no_page_split_or_altered_timing(self):
        with self.assertRaises(BrokerError):compile_pages([bytes(3456)],8,'fade',maximum=10)
        self.assertEqual(index_rgb(bytes([255])*10368),bytes([255])*3456)
        with self.assertRaises(BrokerError):index_rgb(bytes(10))
