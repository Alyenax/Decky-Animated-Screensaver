"""Optional cross-check against actual GCA source. Never shipped/imported at runtime."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from das.jsaux.client import BrokerClient
from das.jsaux.collection import compile_pages
from das.jsaux.protocol import BrokerError
from test_jsaux import state

GCA=os.environ.get('DAS_TEST_GCA_ROOT')

class Hardware:
    def __init__(self):self.commands=[];self.state=state()
    def snapshot(self):return self.state
    def reserve(self,job):self.commands.append(('reserve',job['operation_id']));return True
    def submit(self,job,report):
        self.commands.append(('submit',job['operation_id']))
        report(job['operation_id'],transfer_state='confirmed',fresh_ack=True)
    def cancel(self,operation):self.commands.append(('cancel',operation));return True
    def restore(self,operation,report):
        self.commands.append(('restore',operation));report(operation,restore_state='confirmed')

@unittest.skipUnless(GCA,'explicit DAS_TEST_GCA_ROOT required; no runtime dependency')
class InteropTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0,str(Path(GCA)/'py_modules'))
        self.addCleanup(lambda:sys.path.remove(str(Path(GCA)/'py_modules')))
        from signalbar.jsaux_broker.core import Broker
        from signalbar.jsaux_broker.server import BrokerServer
        self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.hardware=Hardware()
        self.broker=Broker(self.root/'cache',self.hardware)
        self.server=BrokerServer(self.broker,self.root/'runtime');self.server.start()
        self.addCleanup(self.broker.stop);self.addCleanup(self.server.stop)
        self.client=BrokerClient(self.root/'runtime');self.addCleanup(self.client.close)

    def test_actual_gca_hello_auth_refusal_is_distinct_from_local_permissions(self):
        credential = self.server.credential_path
        data = json.loads(credential.read_text())
        data['capability'] = '0' * 64
        credential.write_text(json.dumps(data))
        with self.assertRaises(BrokerError) as raised:
            self.client.discover()
        self.assertEqual(raised.exception.code, 'AUTH_DENIED')
        snapshot = self.client.diagnostic_snapshot()
        self.assertEqual(snapshot['reason'], 'remote-auth-denied')
        self.assertEqual(snapshot['stage'], 'hello')
        self.assertEqual(snapshot['component'], 'control-socket')
        for secret in (str(self.root), data['capability'], self.broker.capability, self.broker.boot_id):
            self.assertNotIn(secret, json.dumps(snapshot))
        self.assertEqual(self.hardware.commands, [])

    def test_canonical_legacy_runtime_recovers_same_client_without_replacing_ownership_lock(self):
        from signalbar.faceplate import runtime
        from signalbar.faceplate.transport import PhysicalOwnership
        from signalbar.jsaux_broker.server import BrokerServer

        self.server.stop()
        endpoint = self.root / 'run/decky/jsaux-broker/v1'
        endpoint.mkdir(parents=True, mode=0o755)
        parents = (self.root / 'run', endpoint.parent.parent, endpoint.parent)
        for directory in (*parents, endpoint):
            directory.chmod(0o755)
        owner = PhysicalOwnership(endpoint / 'ownership')
        contender = PhysicalOwnership(endpoint / 'ownership')
        self.addCleanup(owner.close)
        self.addCleanup(contender.close)
        port = str(self.root / 'metadata-only-fixture-device')
        now = [0.]
        client = BrokerClient(endpoint, monotonic=lambda: now[0])
        self.addCleanup(client.close)

        with patch.object(runtime, 'CANONICAL_RUNTIME', endpoint):
            # Use the actual cooperative ownership lock, not a mocked claim.
            self.assertTrue(owner.claim(port))
            descriptor = owner.descriptors[owner.key(port)]
            lock_path = endpoint / 'ownership' / (owner.key(port) + '.lock')
            lock_inode = os.fstat(descriptor).st_ino
            directory_inode = endpoint.stat().st_ino
            # Model the inherited Lab138 leaf while ownership is still held.
            endpoint.chmod(0o755)
            with self.assertRaises(BrokerError) as raised:
                client.discover()
            self.assertEqual(raised.exception.code, 'AUTH_DENIED')
            self.assertEqual(client.diagnostic_snapshot()['reason'], 'local-mode')
            self.assertEqual(client.diagnostic_snapshot()['observed_mode'], '0755')

            server = BrokerServer(self.broker, runtime_dir=endpoint)
            self.addCleanup(server.stop)
            server.start()
            self.assertEqual(stat.S_IMODE(endpoint.stat().st_mode), 0o700)
            self.assertEqual(endpoint.stat().st_ino, directory_inode)
            for directory in parents:
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
            for path in (server.socket_path, server.credential_path):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(lock_path.stat().st_ino, lock_inode)
            self.assertEqual(os.fstat(descriptor).st_ino, lock_inode)
            self.assertFalse(contender.claim(port))
            # No restart or new client: backoff expires, then handshake works.
            now[0] = 2.
            self.assertEqual(client.status()['hardware'], 'available')
            self.assertEqual(client.diagnostic_snapshot(), {'state': 'connected'})
            self.assertFalse(contender.claim(port))
            owner.close()
            self.assertTrue(contender.claim(port))
            self.assertEqual(lock_path.stat().st_ino, lock_inode)
            self.assertEqual(self.hardware.commands, [])
    def register(self):
        data,_=compile_pages([bytes(3456),bytes([0xe0])*3456],8,'fade')
        path=self.root/'collection.gif';path.write_bytes(data)
        initial=self.client.register(path,'c'*64)
        if 'content_id' in initial:return initial['content_id']
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            result=self.client.operation(validation_id=initial['validation_id'])
            if result['state']=='ready':return result['content_id']
            self.assertNotEqual(result['state'],'rejected',result)
            time.sleep(.05)
        self.fail('actual bounded GIF validator timeout')
    def test_actual_wire_validator_gate_candidate_and_restore(self):
        snapshot=self.client.discover();self.assertEqual(snapshot['hardware'],'available')
        content=self.register();self.assertEqual(self.hardware.commands,[])
        lease=self.client.acquire(activation_id='activation1',session_id='session1',content_id=content,collection_id='c'*64,mode='sync')
        self.assertEqual([x[0] for x in self.hardware.commands],['reserve'])
        now=time.monotonic_ns()//1000000;common=dict(lease_id=lease['lease_id'],generation=lease['generation'])
        ready=dict(**common,alignment_attempt_id=lease['alignment_attempt_id'],ready_mono_ms=now,deadline_mono_ms=now+15000,clock_uncertainty_ms=2)
        self.client.ready(**ready);self.client.ready(**ready)
        self.assertEqual([x[0] for x in self.hardware.commands].count('submit'),1)
        receipt=self.client.operation(operation_id=lease['operation_id'])
        self.assertEqual(receipt['candidate']['optical_alignment'],'unknown')
        self.client.tv_started(**common,alignment_attempt_id=lease['alignment_attempt_id'],started_mono_ms=time.monotonic_ns()//1000000,
            outcome='software-coordinated',candidate_id=receipt['candidate']['candidate_id'])
        self.client.release(**common,reason='player-ended')
        status=self.client.operation(operation_id=lease['operation_id']);self.assertEqual(status['restore_state'],'confirmed')
        self.assertEqual(status['reason'],'PLAYER_ENDED')
        self.assertEqual(self.client.discover(True)['hardware'],'available')
        self.assertEqual([x[0] for x in self.hardware.commands][-2:],['cancel','restore'])
        with self.assertRaises(BrokerError):
            self.client.acquire(activation_id='activation1',session_id='another',content_id=content,collection_id='c'*64,mode='sync')
    def test_actual_policy_off_and_expired_gate_never_submit(self):
        content=self.register();self.hardware.state['policy']['display_on']=False
        with self.assertRaises(BrokerError) as error:
            self.client.acquire(activation_id='activation1',session_id='s',content_id=content,collection_id='c'*64,mode='sync')
        self.assertEqual(error.exception.code,'DISPLAY_OFF');self.assertEqual(self.hardware.commands,[])
        self.hardware.state['policy']['display_on']=True
        lease=self.client.acquire(activation_id='activation1',session_id='s',content_id=content,collection_id='c'*64,mode='sync')
        now=time.monotonic_ns()//1000000
        with self.assertRaises(BrokerError):
            self.client.ready(lease_id=lease['lease_id'],generation=lease['generation'],alignment_attempt_id=lease['alignment_attempt_id'],
                ready_mono_ms=now-3000,deadline_mono_ms=now-500,clock_uncertainty_ms=1)
        self.assertNotIn('submit',[x[0] for x in self.hardware.commands])
