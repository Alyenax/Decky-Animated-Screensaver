"""Pinned optional codec download tested entirely with tiny local fake bundles."""
import hashlib
import ssl
import errno
import io
import json
import os
import sys
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

from das.core import resources as tools
from das.core.catalog import ScreensaverError


def elf():
    value = bytearray(64)
    value[:6] = b"\x7fELF\x02\x01"
    value[18:20] = b"\x3e\x00"
    return bytes(value)


def bundle(extra=None, binary=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:xz") as archive:
        values = {"bin/ffmpeg": binary if binary is not None else elf(), "bin/ffprobe": elf(),
                  "lib/libavcodec.so.62.1": b"fixture shared library", "LICENSE.txt": b"LGPL fixture notice"}
        for name, value in values.items():
            member = tarfile.TarInfo(tools.PIN_STEM + "/" + name)
            member.size = len(value)
            archive.addfile(member, io.BytesIO(value))
        member = tarfile.TarInfo(tools.PIN_STEM + "/lib/libavcodec.so.62")
        member.type = tarfile.SYMTYPE; member.linkname = "libavcodec.so.62.1"
        archive.addfile(member)
        if extra is not None:
            archive.addfile(extra, io.BytesIO(b"x") if extra.isfile() else None)
    return output.getvalue()


class Response(io.BytesIO):
    headers = {}
    def geturl(self): return tools.PIN_URL


class ScreensaverResourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = bundle()
        self.platform = patch.object(tools.Resources, "_supported", return_value=True)
        self.platform.start(); self.addCleanup(self.platform.stop)
        for name, value in (("PIN_SIZE", len(self.data)), ("PIN_SHA256", hashlib.sha256(self.data).hexdigest())):
            p = patch.object(tools, name, value); p.start(); self.addCleanup(p.stop)
        self.requests = []
        def opener(request, timeout):
            self.requests.append((request, timeout))
            return Response(self.data)
        self.runtime = tools.Resources(self.root, opener=opener)
        self.runtime._probe = Mock()

    def install(self):
        self.runtime._install()
        self.assertTrue(self.runtime.status()["ready"], self.runtime.status())

    def test_no_network_or_execution_at_construction_and_status(self):
        self.assertEqual(self.requests, [])
        self.assertEqual(self.runtime.status()['installation_path'], str(self.root.resolve() / 'cinema-tools-v1'))
        self.assertFalse(self.runtime.status()["ready"])
        self.assertIsNone(self.runtime.executable())
        self.runtime._probe.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_certificate_recovery_uses_verified_system_ca_and_restricted_redirects(self):
        ca = self.root/'system-ca.pem'; ca.write_text('fixture')
        context = ssl.create_default_context()
        events = []
        self.runtime.event_callback = lambda event, **fields: events.append((event, fields))
        self.runtime.opener = Mock(side_effect=tools.URLError(ssl.SSLCertVerificationError('fixture secret path')))
        recovered = Mock(); recovered.open.return_value = Response(self.data)
        with patch('das.provider.SYSTEM_CA_BUNDLES', (str(ca),)), \
             patch.object(tools.ssl, 'create_default_context', return_value=context) as factory, \
             patch.object(tools, 'build_opener', return_value=recovered) as build:
            self.install()
        factory.assert_called_once_with(cafile=str(ca))
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertIsInstance(build.call_args.args[0], tools._DownloadRedirects)
        self.assertTrue(any(name == 'cinema_tools_system_ca_recovered' for name, _ in events))

    def test_persistent_tls_error_is_specific_and_diagnostics_never_contain_messages(self):
        self.runtime.opener = Mock(side_effect=tools.URLError(ssl.SSLCertVerificationError('SECRET /private/token?sig=private')))
        with patch('das.provider.SYSTEM_CA_BUNDLES', ()):
            self.runtime._install()
        state = self.runtime.status()
        self.assertEqual(state['error'], 'download_tls')
        self.assertEqual(state['last_failure']['attempt'], 1)
        self.assertNotIn('SECRET', json.dumps(state))
        self.assertNotIn('sig=private', json.dumps(state))

    def test_transient_http_retries_bounded_and_keeps_safe_error_details(self):
        failure = tools.HTTPError(tools.PIN_URL, 503, 'private message', {}, None)
        self.runtime.opener = Mock(side_effect=[failure, Response(self.data)])
        with patch.object(self.runtime.cancelled, 'wait', return_value=False): self.install()
        self.assertEqual(self.runtime.status()['attempt'], 2)
        self.assertEqual(self.runtime.status()['last_failure']['http_status'], 503)
        self.assertNotIn('private message', json.dumps(self.runtime.status()))
        self.runtime = tools.Resources(self.root/'timeouts', opener=Mock(side_effect=TimeoutError('private')))
        self.runtime._probe = Mock()
        with patch.object(self.runtime.cancelled, 'wait', return_value=False): self.runtime._install()
        self.assertEqual(self.runtime.status()['error'], 'download_timeout')
        self.assertEqual(self.runtime.status()['attempt'], 3)

    def test_permission_and_untrusted_redirect_are_not_retried(self):
        self.runtime.opener = Mock(side_effect=PermissionError(errno.EACCES, 'SECRET'))
        self.runtime._install()
        state = self.runtime.status()
        self.assertEqual((state['error'], state['last_failure']['errno']), ('download_permission', errno.EACCES))
        self.runtime.opener.assert_called_once()
        with self.assertRaises(ScreensaverError):
            tools._DownloadRedirects().redirect_request(tools.Request(tools.PIN_URL), None, 302, '', {}, 'http://github.com/unsafe')

    def test_old_owned_codec_pin_is_not_ready_but_can_be_explicitly_repaired(self):
        self.install()
        path = self.runtime.directory / tools.RECEIPT
        receipt = json.loads(path.read_text())
        receipt['archive_sha256'] = '0' * 64  # Valid owned runtime, obsolete codec pin.
        path.write_text(json.dumps(receipt))
        self.runtime._checked = False
        self.assertFalse(self.runtime.status()['ready'])
        self.assertEqual(len(self.requests), 1, 'No silent upgrade')
        self.runtime._install()
        self.assertTrue(self.runtime.status()['ready'])
        self.assertEqual(len(self.requests), 2)

    def test_explicit_start_streamed_checksum_offline_executable_and_source_receipt(self):
        self.runtime.start()
        self.runtime.thread.join(timeout=3)
        self.assertTrue(self.runtime.status()["ready"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.runtime.executable(), str(self.runtime.directory / "bin/ffmpeg"))
        self.assertEqual(self.runtime.library_path(), str(self.runtime.directory / "lib"))
        receipt = json.loads((self.runtime.directory / tools.RECEIPT).read_text())
        self.assertEqual(receipt["archive_sha256"], tools.PIN_SHA256)
        self.assertEqual(receipt["source_url"], tools.PIN_URL)
        self.assertIn("ffmpeg_source_url", receipt)
        self.assertTrue((self.runtime.directory / "lib/libavcodec.so.62").is_symlink())
        self.assertFalse(list(self.root.glob(".cinema-tools-*")))
        self.runtime.start(); self.assertEqual(len(self.requests), 1)

    def test_size_and_checksum_mismatch_preserve_unrelated_files(self):
        unrelated = self.root / "personal.txt"
        unrelated.write_text("preserve")
        with patch.object(tools, "PIN_SHA256", "0" * 64): self.runtime._install()
        self.assertEqual(self.runtime.status()["error"], "checksum_failed")
        self.assertFalse(self.runtime.directory.exists())
        self.assertEqual(unrelated.read_text(), "preserve")
        self.assertFalse(list(self.root.glob(".cinema-tools-*")))

    def test_false_content_length_and_redirect_host_refused(self):
        response = Response(self.data); response.headers = {"Content-Length": "999999"}
        self.runtime.opener = lambda *a, **k: response
        self.runtime._install(); self.assertEqual(self.runtime.status()["error"], "download_size")
        response = Response(self.data); response.geturl = lambda: "https://evil.invalid/payload"
        self.runtime.opener = lambda *a, **k: response
        self.runtime._install(); self.assertEqual(self.runtime.status()["error"], "download_host")

    def test_cancel_during_download_cleanup_and_shutdown_prevents_restart(self):
        runtime = self.runtime
        class Interrupted(Response):
            def read(self, count=-1):
                runtime.cancelled.set()
                return super().read(count)
        runtime.opener = lambda *a, **k: Interrupted(self.data)
        runtime._install()
        self.assertEqual(runtime.status()["phase"], "cancelled")
        self.assertFalse(runtime.directory.exists())
        self.assertFalse(list(self.root.glob(".cinema-tools-*")))
        runtime.shutdown()
        with self.assertRaises(ScreensaverError): runtime.start()

    def test_unsupported_platform_and_insufficient_storage_fail_before_network(self):
        with patch.object(tools.Resources, "_supported", return_value=False):
            self.assertFalse(self.runtime.status()["supported"])
            with self.assertRaises(ScreensaverError): self.runtime.start()
        with patch.object(tools.shutil, "disk_usage", return_value=Mock(free=1)):
            self.runtime._install()
        self.assertEqual(self.runtime.status()["error"], "insufficient_storage")
        self.assertEqual(self.requests, [])

    def test_tar_escape_special_link_escape_and_duplicate_entries_refused(self):
        members = []
        path = tarfile.TarInfo("../escape"); path.size = 1; members.append(path)
        path = tarfile.TarInfo(tools.PIN_STEM + "/lib/outside"); path.type = tarfile.SYMTYPE; path.linkname = "../../outside"; members.append(path)
        path = tarfile.TarInfo(tools.PIN_STEM + "/device"); path.type = tarfile.CHRTYPE; members.append(path)
        path = tarfile.TarInfo(tools.PIN_STEM + "/bin/ffmpeg"); path.size = 1; members.append(path)
        for i, member in enumerate(members):
            with self.subTest(member=member.name):
                archive = self.root / f"unsafe-{i}.tar.xz"; archive.write_bytes(bundle(member))
                stage = self.root / f"stage-{i}"; stage.mkdir()
                with self.assertRaises((ScreensaverError, OSError)): self.runtime._extract(archive, stage)
        self.assertFalse((self.root.parent / "escape").exists())

    def test_bad_elf_bounded_extraction_and_file_count(self):
        archive = self.root / "bad.tar.xz"; archive.write_bytes(bundle(binary=b"not ELF"))
        stage = self.root / "bad"; stage.mkdir()
        with self.assertRaises(ScreensaverError): self.runtime._extract(archive, stage)
        archive = self.root / "valid.tar.xz"; archive.write_bytes(self.data)
        stage = self.root / "limit"; stage.mkdir()
        with patch.object(tools, "MAX_EXTRACTED", 1), self.assertRaises(ScreensaverError): self.runtime._extract(archive, stage)
        stage = self.root / "count"; stage.mkdir()
        with patch.object(tools, "MAX_FILES", 1), self.assertRaises(ScreensaverError): self.runtime._extract(archive, stage)

    def test_foreign_existing_runtime_is_not_overwritten(self):
        self.runtime.directory.mkdir()
        (self.runtime.directory / "personal.txt").write_text("keep")
        self.runtime._install()
        self.assertEqual(self.runtime.status()["error"], "installation_conflict")
        self.assertEqual((self.runtime.directory / "personal.txt").read_text(), "keep")
        self.assertEqual(self.requests, [])

    def test_changed_verified_binary_revokes_executable_without_background_rehash(self):
        self.install()
        (self.runtime.directory / "bin/ffmpeg").write_bytes(b"changed")
        self.assertIsNone(self.runtime.executable())
        self.assertFalse(self.runtime.status()["ready"])
        self.assertIsNone(self.runtime.library_path())

    def test_explicit_verify_hashes_probes_offline_and_revokes_same_size_tampering(self):
        self.install()
        self.runtime._probe.reset_mock()
        requests = len(self.requests)
        self.assertTrue(self.runtime.verify()["ready"])
        self.runtime._probe.assert_called_once()
        self.assertEqual(len(self.requests), requests)
        path = self.runtime.directory / "lib/libavcodec.so.62.1"
        old = path.stat()
        path.write_bytes(b"x" * old.st_size)
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
        self.assertIsNotNone(self.runtime.executable())  # Cheap stat receipt cannot detect deliberate mtime preservation.
        self.assertFalse(self.runtime.verify()["ready"])
        self.assertEqual(self.runtime.status()["error"], "checksum_failed")
        self.assertIsNone(self.runtime.executable())
        self.assertFalse(tools.Resources(self.root).status()["ready"])

    def test_probe_uses_runtime_child_only_environment_and_required_codecs(self):
        stage = self.root / "probe"; stage.mkdir(); (stage / "bin").mkdir(); (stage / "lib").mkdir()
        runtime = tools.Resources(self.root)
        outputs = ["ffmpeg version fixture --enable-version3", "libvpx-vp9 png rawvideo", "scale fps gblur overlay split setpts", "webp_anim", "ffprobe version fixture"]
        with patch.object(runtime, "_probe_output", side_effect=outputs) as probe:
            runtime._probe(stage)
        self.assertEqual(probe.call_count, 5)
        self.assertNotIn('boxblur', outputs[2], 'LGPL runtime must pass without the GPL-only filter')
        with patch.object(runtime, '_probe_output', side_effect=outputs[:3] + ['webp']):
            with self.assertRaises(ScreensaverError): runtime._probe(stage)
        with patch.object(runtime, "_probe_output", return_value="ffmpeg version --enable-gpl"), self.assertRaises(ScreensaverError): runtime._probe(stage)
        environment_before = os.environ.get("LD_LIBRARY_PATH")
        class Process:
            returncode = 0
            def __init__(self, argv, **kwargs):
                self.environment = kwargs["env"]
                self.argv = argv
                kwargs["stdout"].write(b"ffmpeg version fixture")
            def poll(self): return 0
        captured = []
        def create(argv, **kwargs):
            proc = Process(argv, **kwargs); captured.append(proc); return proc
        with patch.object(tools.subprocess, "Popen", side_effect=create):
            self.assertIn("ffmpeg version", runtime._probe_output(stage / "bin/ffmpeg", ["-version"], stage))
        self.assertEqual(captured[0].environment["LD_LIBRARY_PATH"], str(stage / "lib"))
        self.assertEqual(os.environ.get("LD_LIBRARY_PATH"), environment_before)

    def test_probe_reports_missing_decoder_and_filter_without_relaxing_requirements(self):
        runtime = tools.Resources(self.root)
        stage = self.root / 'probe'
        base = ['ffmpeg version fixture', 'libvpx-vp9 png rawvideo',
                'scale fps gblur overlay split setpts', 'webp_anim', 'ffprobe version fixture']
        for index, replacement, expected, missing in (
                (3, 'webp', 'ffmpeg-decoders', ['webp_anim']),
                (3, 'webp_anim_extra', 'ffmpeg-decoders', ['webp_anim']),
                (1, 'png rawvideo', 'ffmpeg-encoders', ['libvpx-vp9']),
                (1, 'libvpx-vp9 apng rawvideo', 'ffmpeg-encoders', ['png']),
                (2, 'scale fps boxblur overlay split setpts', 'ffmpeg-filters', ['gblur']),
                (2, 'scale fps avgblur gblur_vulkan overlay split setpts', 'ffmpeg-filters', ['gblur']),
                (2, 'scale fps overlay split', 'ffmpeg-filters', ['gblur', 'setpts'])):
            outputs = base.copy(); outputs[index] = replacement
            with self.subTest(probe=expected), patch.object(runtime, '_probe_output', side_effect=outputs):
                with self.assertRaises(tools._ProbeFailure) as caught: runtime._probe(stage)
                self.assertEqual(caught.exception.probe_detail, {
                    'probe': expected, 'reason': 'missing_capability', 'missing': missing})
        for value, reason in [('not a version', 'version_output'),
                              ('ffmpeg version --enable-gpl', 'license_configuration')]:
            with patch.object(runtime, '_probe_output', return_value=value):
                with self.assertRaises(tools._ProbeFailure) as caught: runtime._probe(stage)
                self.assertEqual(caught.exception.probe_detail['reason'], reason)

    def test_real_child_exit_is_classified_and_raw_output_is_not_retained(self):
        runtime = tools.Resources(self.root)
        stage = self.root / 'real-probe'; stage.mkdir()
        events = []
        runtime.event_callback = lambda name, **fields: events.append((name, fields))
        # Executes the host Python, not a Linux FFmpeg on macOS. Tests the actual
        # subprocess/output path independently of SteamOS compatibility.
        arguments = ['-c', "import sys; print('error while loading shared libraries: SECRET /private/token?sig=hidden'); sys.exit(127)"]
        with self.assertRaises(tools._ProbeFailure) as caught:
            runtime._probe_output(Path(sys.executable), arguments, stage)
        self.assertEqual(runtime._failure(caught.exception, 'verifying'), 'probe_failed')
        failure = runtime.status()['last_failure']
        self.assertEqual((failure['probe'], failure['reason'], failure['exit_code']),
                         ('ffmpeg-unknown', 'shared_library', 127))
        self.assertGreaterEqual(failure['elapsed_ms'], 0)
        self.assertNotIn('SECRET', json.dumps(events) + json.dumps(failure))
        self.assertNotIn('/private/token', json.dumps(events) + json.dumps(failure))
        self.assertFalse((stage / '.probe-output').exists())
        self.assertIsNone(runtime.process)

    def test_probe_exit_reason_categories_are_fixed_and_safe(self):
        for output, code, reason in [
                ("version `GLIBC_99.0' not found /secret", 1, 'glibc_version'),
                ('symbol lookup error: SECRET', 127, 'symbol_lookup'),
                ('', -9, 'process_signal'), ('SECRET', 1, 'process_exit')]:
            with self.subTest(reason=reason):
                self.assertEqual(tools._probe_exit_reason(output, code), reason)

    def test_spawn_failure_has_errno_and_probe_without_leaking_oserror(self):
        runtime = tools.Resources(self.root)
        stage = self.root / 'spawn-probe'; stage.mkdir()
        with patch.object(tools.subprocess, 'Popen', side_effect=PermissionError(errno.EACCES, 'SECRET')):
            with self.assertRaises(tools._ProbeFailure) as caught:
                runtime._probe_output(stage / 'ffprobe', ['-version'], stage)
        runtime._failure(caught.exception, 'verifying')
        detail = runtime.status()['last_failure']
        self.assertEqual((detail['probe'], detail['reason'], detail['errno']),
                         ('ffprobe-version', 'spawn_failed', errno.EACCES))
        self.assertNotIn('SECRET', json.dumps(detail))

    def test_explicit_verification_preserves_probe_diagnostic_then_clears_on_success(self):
        self.install()
        self.runtime._probe.side_effect = tools._ProbeFailure('ffmpeg-version', 'process_signal', exit_code=-9)
        failed = self.runtime.verify()
        self.assertEqual(failed['last_failure']['exit_code'], -9)
        self.assertFalse(failed['ready'])
        # A repair is still required after a failed verification.
        self.runtime._probe.side_effect = None
        self.install()
        self.runtime.last_failure = {'probe': 'stale'}
        self.assertEqual(self.runtime.verify()['last_failure'], {})

    def test_failed_replacement_preserves_old_verified_runtime(self):
        self.install()
        original = (self.runtime.directory / "bin/ffmpeg").read_bytes()
        # Force an explicit repair scenario by changing a harmless recorded file.
        (self.runtime.directory / "LICENSE.txt").write_text("damaged")
        rename = Path.rename
        def fail_stage(path, target):
            if path.name == "prepared": raise OSError("injected commit failure")
            return rename(path, target)
        with patch.object(Path, "rename", fail_stage): self.runtime._install()
        self.assertEqual((self.runtime.directory / "bin/ffmpeg").read_bytes(), original)
        self.assertEqual((self.runtime.directory / "LICENSE.txt").read_text(), "damaged")
        self.assertFalse(list(self.root.glob(".cinema-tools-*")))

    def test_cancel_terminates_probe_process_group_without_affecting_host_environment(self):
        process = Mock(pid=987654321)
        process.poll.return_value = None
        self.runtime.process = process
        with patch.object(tools.os, "killpg") as kill:
            self.runtime.cancel()
        kill.assert_called_once_with(process.pid, tools.signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=.5)
        self.assertTrue(self.runtime.cancelled.is_set())

    def test_declared_download_overflow_and_probe_excess_output_rejected(self):
        with patch.object(tools, "PIN_SIZE", 1):
            self.runtime._install()
        self.assertEqual(self.runtime.status()["error"], "download_size")
        stage = self.root / "probe-limit"; stage.mkdir()
        class Process:
            returncode = 0
            def __init__(self, argv, **kwargs): kwargs["stdout"].write(b"x" * (512 * 1024 + 1))
            def poll(self): return 0
        with patch.object(tools.subprocess, "Popen", side_effect=Process), self.assertRaises(ScreensaverError):
            self.runtime._probe_output(stage / "ffmpeg", ["-version"], stage)
        self.assertFalse((stage / ".probe-output").exists())


if __name__ == "__main__": unittest.main()
