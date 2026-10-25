"""Connection failure taxonomy against real local metadata and Unix sockets.

No root repair, USB, media encoding or hardware fallback is involved.
"""
import errno
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from das.jsaux.client import BrokerClient
from das.jsaux.protocol import BrokerError
import test_jsaux as fixtures


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.endpoint = fixtures.Endpoint(self.root / 'runtime')
        self.addCleanup(self.endpoint.close)

    def client(self, **options):
        client = BrokerClient(self.endpoint.root, **options)
        self.addCleanup(client.close)
        return client

    def refused(self, client, reason, component):
        with self.assertRaises(BrokerError) as raised:
            client.discover()
        self.assertEqual(raised.exception.code, 'AUTH_DENIED')
        snapshot = client.diagnostic_snapshot()
        self.assertEqual(snapshot['reason'], reason)
        self.assertEqual(snapshot['component'], component)
        encoded = json.dumps(snapshot)
        for private in (str(self.root), self.endpoint.secret, 'boot1', 'SECRET'):
            self.assertNotIn(private, encoded)
        self.assertLess(len(encoded), 1024)
        self.assertNotIn('acquire_display', [call['op'] for call in self.endpoint.calls])
        return snapshot

    def test_real_755_directory_refused_without_repair_and_recovers_after_owner_fix(self):
        self.endpoint.root.chmod(0o755)
        now = [0.]
        client = self.client(monotonic=lambda: now[0])
        snapshot = self.refused(client, 'local-mode', 'runtime')
        self.assertEqual(snapshot['expected_mode'], '0700')
        self.assertEqual(snapshot['observed_mode'], '0755')
        self.assertEqual(snapshot['expected_uid'], os.geteuid())
        self.assertEqual(snapshot['observed_uid'], os.geteuid())
        self.assertEqual(snapshot['observed_kind'], 'directory')
        self.assertEqual(self.endpoint.root.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.endpoint.calls, [])
        # Backoff preserves the useful diagnosis, rather than masking it.
        self.endpoint.root.chmod(0o700)
        self.assertEqual(self.refused(client, 'local-mode', 'runtime'), snapshot)
        now[0] = 2.
        self.assertEqual(client.discover()['hardware'], 'available')
        self.assertEqual(client.diagnostic_snapshot(), {'state': 'connected'})

    def test_real_owner_comparison_is_reported_without_chown(self):
        snapshot = self.refused(self.client(expected_uid=os.geteuid() + 1),
                                'local-owner', 'runtime')
        self.assertEqual(snapshot['observed_uid'], os.geteuid())
        self.assertEqual(snapshot['expected_uid'], os.geteuid() + 1)

    def test_credential_permissions_symlink_and_links_are_distinct(self):
        credential = self.endpoint.root / 'credential.json'
        credential.chmod(0o644)
        self.refused(self.client(), 'local-mode', 'credential')
        credential.chmod(0o600)
        original = self.root / 'original'
        credential.rename(original)
        credential.symlink_to(original)
        self.refused(self.client(), 'local-symlink', 'credential')
        credential.unlink()
        original.rename(credential)
        os.link(credential, self.root / 'extra-link')
        self.refused(self.client(), 'local-links', 'credential')

    def test_real_symlink_ancestor_and_wrong_type_have_safe_component_labels(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        client = BrokerClient(alias / 'runtime')
        self.addCleanup(client.close)
        self.refused(client, 'local-symlink', 'connection-root')
        ordinary = self.root / 'ordinary'
        ordinary.write_text('not a directory')
        client = BrokerClient(ordinary)
        self.addCleanup(client.close)
        snapshot = self.refused(client, 'local-type', 'runtime')
        self.assertEqual(snapshot['observed_kind'], 'regular-file')

    def test_socket_metadata_and_remote_hello_auth_are_distinct(self):
        endpoint = self.endpoint.root / 'control.sock'
        endpoint.chmod(0o644)
        snapshot = self.refused(self.client(), 'local-mode', 'control-socket')
        self.assertEqual(snapshot['stage'], 'socket-metadata')
        endpoint.chmod(0o600)
        self.endpoint.hook = lambda request: BrokerError('AUTH_DENIED')
        snapshot = self.refused(self.client(), 'remote-auth-denied', 'control-socket')
        self.assertEqual(snapshot['stage'], 'hello')
        self.assertEqual([call['op'] for call in self.endpoint.calls], ['hello'])

    def test_system_permission_errors_are_not_generic_unavailability(self):
        for number in (errno.EACCES, errno.EPERM):
            with self.subTest(errno=number):
                client = self.client()
                with patch('das.jsaux.client.os.open', side_effect=PermissionError(number, 'SECRET path')):
                    snapshot = self.refused(client, 'system-permission-denied', 'credential')
                self.assertEqual(snapshot['errno'], number)
                self.assertEqual(snapshot['stage'], 'credential')
        self.assertEqual(self.endpoint.calls, [])

    def test_socket_system_permission_and_remote_request_auth_keep_their_stage(self):
        class DeniedSocket:
            def settimeout(self, timeout):
                pass
            def connect(self, endpoint):
                raise PermissionError(errno.EPERM, 'SECRET endpoint')
            def close(self):
                pass
        client = self.client(socket_factory=lambda *args: DeniedSocket())
        snapshot = self.refused(client, 'system-permission-denied', 'control-socket')
        self.assertEqual(snapshot['stage'], 'socket-connect')
        client = self.client()
        client.discover()
        self.endpoint.hook = lambda request: BrokerError('AUTH_DENIED')
        with self.assertRaises(BrokerError):
            client.status()
        snapshot = client.diagnostic_snapshot()
        self.assertEqual(snapshot['reason'], 'remote-auth-denied')
        self.assertEqual(snapshot['stage'], 'request')

    def test_missing_endpoint_is_classified_without_exposing_its_path(self):
        client = BrokerClient(self.root / 'missing')
        self.addCleanup(client.close)
        with self.assertRaises(BrokerError) as raised:
            client.discover()
        self.assertEqual(raised.exception.code, 'BROKER_UNAVAILABLE')
        snapshot = client.diagnostic_snapshot()
        self.assertEqual(snapshot['reason'], 'missing')
        self.assertEqual(snapshot['component'], 'runtime')
        self.assertEqual(snapshot['errno'], errno.ENOENT)
        self.assertNotIn(str(self.root), json.dumps(snapshot))

    def test_snapshot_is_a_copy_and_status_is_local(self):
        client = self.client()
        client.discover()
        snapshot = client.diagnostic_snapshot()
        snapshot['state'] = 'tampered'
        before = list(self.endpoint.calls)
        self.assertEqual(client.diagnostic_snapshot(), {'state': 'connected'})
        self.assertEqual(self.endpoint.calls, before)

    def test_diagnostic_does_not_wait_for_the_rpc_lock(self):
        client = self.client()
        entered, release = threading.Event(), threading.Event()
        def hold():
            with client.lock:
                entered.set()
                release.wait(2)
        worker = threading.Thread(target=hold)
        worker.start()
        self.assertTrue(entered.wait(1))
        result = []
        reader = threading.Thread(target=lambda: result.append(client.diagnostic_snapshot()))
        try:
            reader.start()
            reader.join(.2)
            self.assertFalse(reader.is_alive())
            self.assertEqual(result, [{'state': 'not-checked'}])
        finally:
            release.set()
            reader.join(1)
            worker.join(1)


class PreservedMediaTests(unittest.TestCase):
    def test_rejected_connection_keeps_prepared_tv_collection_and_export(self):
        fixture = fixtures.ManagerTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare_receipt()
        manager = fixture.manager
        before_receipt = dict(manager.receipt)
        before_export = dict(fixture.installer.jsaux_export)
        before_media = dict(fixture.service.catalog.get(620)['media'])
        with tempfile.TemporaryDirectory(dir='/private/tmp') as directory:
            root = Path(directory).resolve() / 'runtime'
            root.mkdir(mode=0o755)
            client = BrokerClient(root)
            self.addCleanup(client.close)
            manager.broker = client
            with patch.object(manager, '_prepare', side_effect=AssertionError('No conversion on refusal')):
                manager.prepare()
            status = manager.status()
            self.assertEqual(status['reason'], 'AUTH_DENIED')
            self.assertEqual(status['connection']['reason'], 'local-mode')
            self.assertEqual(status['connection']['observed_mode'], '0755')
            self.assertTrue(status['prepared']['ready'])
            self.assertTrue(status['relay_enabled'])
            self.assertEqual(manager.receipt, before_receipt)
            self.assertEqual(fixture.installer.jsaux_export, before_export)
            self.assertEqual(fixture.service.catalog.get(620)['media'], before_media)
            self.assertFalse(manager.busy())
